"""Black-box acceptance tests for dotenv Manager v0.1.

Every test invokes ``./app`` as an external process. No module from ``src`` is
imported. Test names carry the spec's AC/EC identifiers.

Run with::

    python3 -m unittest discover -s tests -v
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO_ROOT, "app")
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fx(name):
    return os.path.join(FIXTURES, name)


def run(*args):
    return subprocess.run(
        [sys.executable, APP, *args], capture_output=True, text=True, encoding="utf-8", timeout=60
    )


def payload(proc):
    return json.loads(proc.stdout)


def change_set(data):
    return {(change["kind"], change["key"]) for change in data["changes"]}


class IdenticalFilesAC1(unittest.TestCase):
    def test_ac_01_identical_files(self):
        proc = run("diff", fx("identical_old.env"), fx("identical_new.env"))
        self.assertEqual(proc.returncode, 0)
        self.assertIn("no differences", proc.stdout)
        self.assertEqual(proc.stderr, "")

    def test_ac_02_comments_and_order(self):
        proc = run("diff", fx("comments_old.env"), fx("comments_new.env"))
        self.assertEqual(proc.returncode, 0)
        self.assertIn("no differences", proc.stdout)
        self.assertEqual(proc.stderr, "")


class ChangeKindsAC3ToAC5(unittest.TestCase):
    def test_ac_03_key_added(self):
        proc = run("diff", fx("added_old.env"), fx("added_new.env"), "--json")
        self.assertEqual(proc.returncode, 1)
        data = payload(proc)
        self.assertFalse(data["breaking"])
        self.assertIn(("key.added", "DEBUG"), change_set(data))
        self.assertEqual(data["summary"], {"added": 1, "removed": 0, "changed": 0})

    def test_ac_04_key_removed_is_breaking(self):
        proc = run("diff", fx("removed_old.env"), fx("removed_new.env"), "--json")
        self.assertEqual(proc.returncode, 3)
        data = payload(proc)
        self.assertTrue(data["breaking"])
        self.assertIn(("key.removed", "DEBUG"), change_set(data))
        change = next(c for c in data["changes"] if c["key"] == "DEBUG")
        self.assertTrue(change["breaking"])

    def test_ac_05_value_changed(self):
        proc = run("diff", fx("changed_old.env"), fx("changed_new.env"), "--json")
        self.assertEqual(proc.returncode, 1)
        data = payload(proc)
        self.assertFalse(data["breaking"])
        self.assertIn(("key.changed", "PORT"), change_set(data))
        self.assertIn("[redacted]", proc.stdout)


class MaskingAC6AndAC7(unittest.TestCase):
    def test_ac_06_values_masked_by_default(self):
        proc = run("diff", fx("secret_old.env"), fx("secret_new.env"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("[redacted]", proc.stdout)
        self.assertNotIn("secret123", proc.stdout)
        self.assertNotIn("secret456", proc.stdout)

        proc = run("diff", fx("secret_old.env"), fx("secret_new.env"), "--json")
        data = payload(proc)
        self.assertEqual(data["changes"][0]["before"], "[redacted]")
        self.assertEqual(data["changes"][0]["after"], "[redacted]")

    def test_ac_07_show_values(self):
        proc = run("diff", fx("secret_old.env"), fx("secret_new.env"), "--show-values")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("secret123", proc.stdout)
        self.assertIn("secret456", proc.stdout)

        proc = run(
            "diff", fx("secret_old.env"), fx("secret_new.env"),
            "--show-values", "--json",
        )
        data = payload(proc)
        self.assertEqual(data["changes"][0]["before"], "secret123")
        self.assertEqual(data["changes"][0]["after"], "secret456")


class SchemaValidationAC8AndAC9(unittest.TestCase):
    def test_ac_08_schema_validation_success(self):
        proc = run(
            "diff", fx("schema_old.env"), fx("schema_new.env"),
            "--schema", fx("schema.json"), "--json",
        )
        self.assertEqual(proc.returncode, 1)
        data = payload(proc)
        self.assertEqual(data["validation_errors"], [])
        self.assertEqual(data["warnings"], [])
        self.assertEqual(data["summary"]["changed"], 2)

    def test_ac_09_schema_validation_failure(self):
        proc = run(
            "diff", fx("bad_number_old.env"), fx("bad_number_new.env"),
            "--schema", fx("bad_schema.json"), "--json",
        )
        self.assertEqual(proc.returncode, 1)
        data = payload(proc)
        self.assertTrue(data["validation_errors"])
        self.assertIn("PORT", [e["key"] for e in data["validation_errors"]])
        self.assertTrue(data["warnings"])
        self.assertIn("warning", proc.stderr.lower())


class ValueEdgeCasesAC10AndAC11(unittest.TestCase):
    def test_ac_10_spaces_preserved(self):
        proc = run(
            "diff", fx("spaces_old.env"), fx("spaces_new.env"),
            "--show-values", "--json",
        )
        self.assertEqual(proc.returncode, 1)
        change = payload(proc)["changes"][0]
        self.assertEqual(change["before"], "hello world")
        self.assertEqual(change["after"], " hello world ")

    def test_ac_11_empty_value(self):
        proc = run(
            "diff", fx("empty_value_old.env"), fx("empty_value_new.env"),
            "--show-values", "--json",
        )
        self.assertEqual(proc.returncode, 1)
        change = payload(proc)["changes"][0]
        self.assertEqual(change["key"], "EMPTY_VAR")
        self.assertEqual(change["kind"], "key.changed")
        self.assertEqual(change["before"], "value")
        self.assertEqual(change["after"], "")


class ErrorsAC12ToAC15(unittest.TestCase):
    def test_ac_12_duplicate_key(self):
        proc = run("diff", fx("duplicate.env"), fx("identical_new.env"))
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("error:", proc.stderr)
        self.assertIn("duplicate", proc.stderr.lower())

    def test_ac_13_missing_env_file(self):
        proc = run("diff", "/nonexistent/old.env", "/nonexistent/new.env")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertTrue(proc.stderr.startswith("error:"))

    def test_ac_14_missing_schema(self):
        proc = run(
            "diff", fx("changed_old.env"), fx("changed_new.env"),
            "--schema", "/nonexistent/schema.json",
        )
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("error:", proc.stderr)

    def test_ac_15_malformed_schema(self):
        proc = run(
            "diff", fx("changed_old.env"), fx("changed_new.env"),
            "--schema", fx("malformed_schema.json"),
        )
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("error:", proc.stderr)


class JSONOutputAC16(unittest.TestCase):
    def test_ac_16_json_is_pure_and_valid(self):
        proc = run("diff", fx("changed_old.env"), fx("changed_new.env"), "--json")
        self.assertEqual(proc.returncode, 1)
        data = json.loads(proc.stdout)
        for field in (
            "version", "breaking", "summary", "changes",
            "validation_errors", "warnings",
        ):
            self.assertIn(field, data)
        self.assertEqual(data["version"], "0.1.0")
        self.assertEqual(data["changes"][0]["kind"], "key.changed")
        self.assertFalse(data["changes"][0]["breaking"])


class KeysAC17(unittest.TestCase):
    def test_ac_17_underscore_and_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.path.join(tmp, "old.env")
            new = os.path.join(tmp, "new.env")
            with open(old, "w", encoding="utf-8") as fh:
                fh.write("MY_API_KEY_PROD=secret1\n")
            with open(new, "w", encoding="utf-8") as fh:
                fh.write("MY_API_KEY_PROD=secret2\n")
            proc = run("diff", old, new, "--json")
        self.assertEqual(proc.returncode, 1)
        self.assertIn(("key.changed", "MY_API_KEY_PROD"), change_set(payload(proc)))


class ParsingAC18AndAC19(unittest.TestCase):
    def test_ac_18_hash_in_value(self):
        proc = run("diff", fx("hash_old.env"), fx("hash_new.env"))
        self.assertEqual(proc.returncode, 0)
        self.assertIn("no differences", proc.stdout)

    def test_ac_19_only_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.path.join(tmp, "old.env")
            new = os.path.join(tmp, "new.env")
            with open(old, "w", encoding="utf-8") as fh:
                fh.write("# config file\n# nothing here\n")
            with open(new, "w", encoding="utf-8") as fh:
                fh.write("# config file v2\n")
            proc = run("diff", old, new)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("no differences", proc.stdout)


class MultipleChangesAC20(unittest.TestCase):
    def test_ac_20_multiple_changes_with_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.path.join(tmp, "old.env")
            new = os.path.join(tmp, "new.env")
            schema = os.path.join(tmp, "schema.json")
            with open(old, "w", encoding="utf-8") as fh:
                fh.write("PORT=8080\nDEBUG=false\n")
            with open(new, "w", encoding="utf-8") as fh:
                fh.write("PORT=8080\nDEBUG=true\nEXTRA=newkey\n")
            with open(schema, "w", encoding="utf-8") as fh:
                fh.write(
                    '{"PORT": {"type": "number"}, '
                    '"DEBUG": {"type": "boolean"}, '
                    '"EXTRA": {"type": "string"}}'
                )
            proc = run("diff", old, new, "--schema", schema, "--json")
        self.assertEqual(proc.returncode, 1)
        data = payload(proc)
        self.assertIn(("key.added", "EXTRA"), change_set(data))
        self.assertIn(("key.changed", "DEBUG"), change_set(data))
        self.assertEqual(data["summary"], {"added": 1, "removed": 0, "changed": 1})
        self.assertFalse(data["breaking"])
        self.assertEqual(data["validation_errors"], [])


class VersionHelpAC21(unittest.TestCase):
    def test_ac_21_version(self):
        proc = run("--version")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("0.1.0", proc.stdout)
        self.assertEqual(proc.stderr, "")

    def test_ac_21_help(self):
        proc = run("--help")
        self.assertEqual(proc.returncode, 0)
        for token in ("diff", "--show-values", "--schema", "--json"):
            self.assertIn(token, proc.stdout)
        self.assertEqual(proc.stderr, "")


class DeterminismAC22(unittest.TestCase):
    def test_ac_22_determinism(self):
        args = ("diff", fx("added_old.env"), fx("added_new.env"), "--json")
        first = run(*args)
        second = run(*args)
        self.assertEqual(first.returncode, second.returncode)
        self.assertEqual(first.stdout, second.stdout)


class EdgeCases(unittest.TestCase):
    def test_ec_01_empty_files(self):
        proc = run("diff", fx("empty.env"), fx("empty.env"))
        self.assertEqual(proc.returncode, 0)
        self.assertIn("no differences", proc.stdout)

    def test_ec_05_indentation_ignored(self):
        proc = run("diff", fx("indent_old.env"), fx("indent_new.env"))
        self.assertEqual(proc.returncode, 0)

    def test_ec_06_space_after_equals_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.path.join(tmp, "old.env")
            new = os.path.join(tmp, "new.env")
            with open(old, "w", encoding="utf-8") as fh:
                fh.write("VAL=hello\n")
            with open(new, "w", encoding="utf-8") as fh:
                fh.write("VAL= hello\n")
            proc = run("diff", old, new, "--show-values", "--json")
        change = payload(proc)["changes"][0]
        self.assertEqual(change["before"], "hello")
        self.assertEqual(change["after"], " hello")

    def test_ec_08_multiline_rejected(self):
        proc = run("diff", fx("multiline.env"), fx("identical_old.env"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error:", proc.stderr)
        self.assertEqual(proc.stdout, "")

    def test_ec_09_utf8_accepted(self):
        proc = run("diff", fx("utf8_old.env"), fx("utf8_new.env"))
        self.assertEqual(proc.returncode, 0)
        self.assertIn("no differences", proc.stdout)

    def test_ec_10_schema_omitted_no_validation(self):
        proc = run("diff", fx("changed_old.env"), fx("changed_new.env"))
        self.assertEqual(proc.returncode, 1)
        self.assertNotIn("validation", proc.stderr.lower())

    def test_ec_15_permission_denied(self):
        if os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0):
            self.skipTest("POSIX read mode bits unavailable or not enforced for this user")
        with tempfile.TemporaryDirectory() as tmp:
            noaccess = os.path.join(tmp, "noaccess.env")
            accessible = os.path.join(tmp, "accessible.env")
            with open(noaccess, "w", encoding="utf-8") as fh:
                fh.write("PORT=8080\n")
            with open(accessible, "w", encoding="utf-8") as fh:
                fh.write("PORT=8080\n")
            os.chmod(noaccess, 0o000)
            try:
                proc = run("diff", noaccess, accessible)
            finally:
                os.chmod(noaccess, 0o644)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error:", proc.stderr)

    def test_ec_multiple_equals_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.path.join(tmp, "old.env")
            new = os.path.join(tmp, "new.env")
            with open(old, "w", encoding="utf-8") as fh:
                fh.write("KEY=a=b\n")
            with open(new, "w", encoding="utf-8") as fh:
                fh.write("KEY=a=c\n")
            proc = run("diff", old, new, "--show-values", "--json")
        self.assertEqual(proc.returncode, 1)
        change = payload(proc)["changes"][0]
        self.assertEqual(change["before"], "a=b")
        self.assertEqual(change["after"], "a=c")

    def test_ec_export_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "bad.env")
            with open(bad, "w", encoding="utf-8") as fh:
                fh.write("export PORT=8080\n")
            proc = run("diff", bad, fx("empty.env"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error:", proc.stderr)


if __name__ == "__main__":
    sys.exit(unittest.main())
