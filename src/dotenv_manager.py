#!/usr/bin/env python3
"""dotenv Manager (v0.1).

Compare two dotenv files, emit a typed list of changes, optionally validate the
new values against a JSON schema, and classify changes as breaking or not.

The implementation intentionally uses only the Python standard library.
"""

import json
import re
import sys

VERSION = "0.1.0"

EXIT_OK = 0
EXIT_CHANGED = 1
EXIT_ERROR = 2
EXIT_BREAKING = 3

MASK = "[redacted]"

KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
INTERPOLATION_RE = re.compile(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?")

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_LINE_CHARS = 1_000_000
MAX_KEYS = 10_000

TYPE_NAMES = ("string", "number", "boolean", "enum")

HELP_TEXT = """dotenv Manager 0.1.0

Compare two .env files and report typed changes.

Usage:
  ./app diff ANTIGO.env NOVO.env [--show-values] [--schema schema.json] [--json]
  ./app --version
  ./app --help

Options:
  --show-values        show real values (default: mask them as [redacted])
  --schema PATH        validate values from NOVO.env against a JSON schema
  --json               emit only JSON on stdout
  -h, --help           show this help message
  -V, --version        show the version number

Exit codes:
  0  files are equivalent; no changes
  1  changes exist, none of them are breaking
  3  at least one breaking change exists
  2  error (I/O, parse, arguments, schema)
"""


class DotenvError(Exception):
    """A controlled error that maps to exit code 2."""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_env_file(path, show_values=False):
    """Parse a dotenv file into an ordered dict of ``key -> value``.

    Raises ``DotenvError`` on any construction outside the supported subset.
    Error messages never echo raw values unless ``show_values`` is true.
    """
    try:
        with open(path, "rb") as handle:
            raw = handle.read(MAX_FILE_BYTES + 1)
    except OSError as exc:
        reason = exc.strerror or str(exc)
        raise DotenvError("cannot read file '{0}': {1}".format(path, reason))

    if len(raw) > MAX_FILE_BYTES:
        raise DotenvError(
            "file '{0}' exceeds the maximum size of {1} bytes".format(
                path, MAX_FILE_BYTES
            )
        )

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DotenvError(
            "file '{0}' is not valid UTF-8 (byte offset {1})".format(
                path, exc.start
            )
        )

    values = {}
    first_line = {}

    for lineno, line in enumerate(text.split("\n"), start=1):
        if line.endswith("\r"):
            line = line[:-1]

        if len(line) > MAX_LINE_CHARS:
            raise DotenvError(
                "file '{0}', line {1}: line exceeds the maximum length of "
                "{2} characters".format(path, lineno, MAX_LINE_CHARS)
            )

        stripped = line.lstrip()

        if not stripped:
            continue
        if stripped.startswith("#"):
            continue

        if stripped == "export" or stripped.startswith("export "):
            raise DotenvError(
                "file '{0}', line {1}: 'export' prefix is not supported".format(
                    path, lineno
                )
            )

        if "=" not in stripped:
            raise DotenvError(
                "file '{0}', line {1}: expected KEY=value".format(path, lineno)
            )

        key_part, value = stripped.split("=", 1)
        # Only whitespace before the key (on the line) is ignored; any
        # whitespace between the key and '=' makes the key invalid.
        key = key_part

        if not KEY_RE.match(key):
            raise DotenvError(
                "file '{0}', line {1}: invalid key '{2}'".format(
                    path, lineno, key
                )
            )

        match = INTERPOLATION_RE.search(value)
        if match:
            if show_values:
                raise DotenvError(
                    "file '{0}', line {1}: variable interpolation is not "
                    "supported ('{2}')".format(path, lineno, match.group(0))
                )
            raise DotenvError(
                "file '{0}', line {1}: variable interpolation is not "
                "supported".format(path, lineno)
            )

        if key in values:
            raise DotenvError(
                "file '{0}', line {1}: duplicate key '{2}' (first defined at "
                "line {3})".format(path, lineno, key, first_line[key])
            )

        if len(values) >= MAX_KEYS:
            raise DotenvError(
                "file '{0}' exceeds the maximum number of keys ({1})".format(
                    path, MAX_KEYS
                )
            )

        values[key] = value
        first_line[key] = lineno

    return values


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def load_schema(path):
    """Load and structurally validate a schema file."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read(MAX_FILE_BYTES + 1)
    except OSError as exc:
        reason = exc.strerror or str(exc)
        raise DotenvError(
            "cannot read schema '{0}': {1}".format(path, reason)
        )

    if len(raw) > MAX_FILE_BYTES:
        raise DotenvError(
            "schema '{0}' exceeds the maximum size of {1} bytes".format(
                path, MAX_FILE_BYTES
            )
        )

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise DotenvError("schema '{0}' is not valid UTF-8".format(path))

    try:
        schema = json.loads(text)
    except ValueError as exc:
        raise DotenvError(
            "invalid JSON syntax in schema '{0}': {1}".format(path, exc)
        )

    if not isinstance(schema, dict):
        raise DotenvError(
            "invalid schema '{0}': root must be a JSON object".format(path)
        )

    for key, rule in schema.items():
        if not isinstance(rule, dict):
            raise DotenvError(
                "invalid schema '{0}': entry '{1}' must be an object".format(
                    path, key
                )
            )
        kind = rule.get("type")
        if kind not in TYPE_NAMES:
            raise DotenvError(
                "invalid schema '{0}': entry '{1}' has invalid type".format(
                    path, key
                )
            )
        if kind == "enum":
            allowed = rule.get("enum")
            if not isinstance(allowed, list) or not allowed:
                raise DotenvError(
                    "invalid schema '{0}': enum entry '{1}' requires a "
                    "non-empty 'enum' list".format(path, key)
                )
        for bound in ("min", "max"):
            if bound in rule and not _is_number(rule[bound]):
                raise DotenvError(
                    "invalid schema '{0}': entry '{1}' has a non-numeric "
                    "'{2}'".format(path, key, bound)
                )

    return schema


def validate_value(rule, value, show_values):
    """Return an error string for ``value``, or ``None`` when it conforms."""
    kind = rule.get("type")

    if kind == "string":
        return None

    if kind == "number":
        if not NUMBER_RE.match(value):
            return "expected a number"
        number = float(value)
        minimum = rule.get("min")
        maximum = rule.get("max")
        if _is_number(minimum) and number < minimum:
            return "number is below the minimum of {0}".format(minimum)
        if _is_number(maximum) and number > maximum:
            return "number is above the maximum of {0}".format(maximum)
        return None

    if kind == "boolean":
        if value not in ("true", "false"):
            return "expected a boolean ('true' or 'false')"
        return None

    if kind == "enum":
        allowed = rule.get("enum") or []
        if value not in allowed:
            return "expected one of the allowed enum values"
        return None

    return "unknown schema type"


def validate_new_state(schema, new_values, show_values):
    """Validate every key present in NOVO.env. Returns (errors, warnings)."""
    errors = []
    warnings = []
    for key in sorted(new_values):
        rule = schema.get(key)
        if rule is None:
            continue
        problem = validate_value(rule, new_values[key], show_values)
        if problem is not None:
            errors.append({"key": key, "error": problem})
            warnings.append("validation failed for '{0}': {1}".format(key, problem))
    return errors, warnings


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def compare(old_values, new_values):
    """Return a deterministic list of change dictionaries."""
    changes = []
    for key in sorted(old_values):
        if key not in new_values:
            changes.append(
                {
                    "kind": "key.removed",
                    "key": key,
                    "breaking": True,
                    "before": old_values[key],
                    "after": None,
                }
            )
        elif old_values[key] != new_values[key]:
            changes.append(
                {
                    "kind": "key.changed",
                    "key": key,
                    "breaking": False,
                    "before": old_values[key],
                    "after": new_values[key],
                }
            )

    for key in sorted(new_values):
        if key not in old_values:
            changes.append(
                {
                    "kind": "key.added",
                    "key": key,
                    "breaking": False,
                    "before": None,
                    "after": new_values[key],
                }
            )

    kind_rank = {"key.added": 0, "key.removed": 1, "key.changed": 2}
    changes.sort(key=lambda change: (change["key"], kind_rank[change["kind"]]))
    return changes


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def build_payload(changes, validation_errors, warnings, show_values):
    """Build the JSON payload, masking values unless asked to show them."""

    def display(value):
        if value is None:
            return None
        return value if show_values else MASK

    summary = {"added": 0, "removed": 0, "changed": 0}
    entries = []
    for change in changes:
        kind = change["kind"]
        summary[kind.split(".", 1)[1]] += 1
        entries.append(
            {
                "kind": kind,
                "key": change["key"],
                "breaking": change["breaking"],
                "before": display(change["before"]),
                "after": display(change["after"]),
            }
        )

    return {
        "version": VERSION,
        "breaking": any(change["breaking"] for change in changes),
        "summary": summary,
        "changes": entries,
        "validation_errors": validation_errors,
        "warnings": warnings,
    }


def render_text(changes, show_values):
    """Render the human-readable change block."""
    lines = []
    for change in changes:
        kind = change["kind"]
        key = change["key"]
        if kind == "key.added":
            if show_values:
                lines.append("+ {0} {1} : -> {2}".format(kind, key, change["after"]))
            else:
                lines.append("+ {0} {1}".format(kind, key))
        elif kind == "key.removed":
            if show_values:
                lines.append("- {0} {1} : {2} -> [removed]".format(
                    kind, key, change["before"]
                ))
            else:
                lines.append("- {0} {1}".format(kind, key))
        else:
            before = change["before"] if show_values else MASK
            after = change["after"] if show_values else MASK
            lines.append("~ {0} {1} : {2} -> {3}".format(kind, key, before, after))

    breaking_count = sum(1 for change in changes if change["breaking"])
    if breaking_count:
        lines.append("breaking: {0} change(s)".format(breaking_count))

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class UsageError(Exception):
    pass


def parse_command_line(argv):
    """Parse argv (without the program name) into an options dictionary."""
    if not argv:
        raise UsageError("missing subcommand (expected 'diff')")

    first = argv[0]
    if first in ("--version", "-V"):
        return {"action": "version"}
    if first in ("--help", "-h"):
        return {"action": "help"}
    if first != "diff":
        raise UsageError("unknown subcommand '{0}'".format(first))

    positional = []
    show_values = False
    json_mode = False
    schema = None
    index = 1

    while index < len(argv):
        arg = argv[index]
        if arg == "--show-values":
            show_values = True
        elif arg == "--json":
            json_mode = True
        elif arg == "--schema":
            index += 1
            if index >= len(argv):
                raise UsageError("option '--schema' requires an argument")
            schema = argv[index]
        elif arg.startswith("--schema="):
            schema = arg.split("=", 1)[1]
            if not schema:
                raise UsageError("option '--schema' requires an argument")
        elif arg in ("--help", "-h"):
            return {"action": "help"}
        elif arg == "--":
            positional.extend(argv[index + 1:])
            break
        elif arg.startswith("-") and arg != "-":
            raise UsageError("unknown option '{0}'".format(arg))
        else:
            positional.append(arg)
        index += 1

    if len(positional) < 2:
        raise UsageError("expected two .env files: ANTIGO.env NOVO.env")
    if len(positional) > 2:
        raise UsageError("unexpected extra argument '{0}'".format(positional[2]))

    return {
        "action": "diff",
        "old": positional[0],
        "new": positional[1],
        "show_values": show_values,
        "json": json_mode,
        "schema": schema,
    }


def run_diff(options):
    old_values = parse_env_file(options["old"], options["show_values"])
    new_values = parse_env_file(options["new"], options["show_values"])

    schema = None
    if options["schema"] is not None:
        schema = load_schema(options["schema"])

    changes = compare(old_values, new_values)

    validation_errors = []
    warnings = []
    if schema is not None:
        validation_errors, warnings = validate_new_state(
            schema, new_values, options["show_values"]
        )

    if options["json"]:
        payload = build_payload(
            changes, validation_errors, warnings, options["show_values"]
        )
        output = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    elif not changes:
        output = "no differences\n"
    else:
        output = render_text(changes, options["show_values"])

    for warning in warnings:
        sys.stderr.write("warning: {0}\n".format(warning))

    sys.stdout.write(output)

    if any(change["breaking"] for change in changes):
        return EXIT_BREAKING
    if changes or validation_errors:
        return EXIT_CHANGED
    return EXIT_OK


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    try:
        options = parse_command_line(argv)
    except UsageError as exc:
        sys.stderr.write("error: {0}\n".format(exc))
        return EXIT_ERROR

    action = options["action"]
    if action == "version":
        sys.stdout.write("dotenv Manager {0}\n".format(VERSION))
        return EXIT_OK
    if action == "help":
        sys.stdout.write(HELP_TEXT)
        return EXIT_OK

    try:
        return run_diff(options)
    except DotenvError as exc:
        sys.stderr.write("error: {0}\n".format(exc))
        return EXIT_ERROR
    except Exception as exc:  # defensive: never leak a traceback as undefined
        sys.stderr.write("error: unexpected failure: {0}\n".format(exc))
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
