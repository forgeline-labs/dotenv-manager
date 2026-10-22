# Demo recording for dotenv Manager (v0.1).
# Requires vhs: https://github.com/charmbracelet/vhs
# Render with: vhs demo.tape

Output docs/demo.gif

Set Shell "bash"
Set FontSize 18
Set Width 1100
Set Height 700
Set Padding 20
Set TypingSpeed 60ms

Type "./app --version"
Enter
Sleep 500ms

Type "printf 'PORT=8080\nDEBUG=false\n' > /tmp/old.env"
Enter
Type "printf 'PORT=9090\nDEBUG=true\n' > /tmp/new.env"
Enter
Sleep 300ms

Type "./app diff /tmp/old.env /tmp/new.env"
Enter
Sleep 1s

Type "./app diff /tmp/old.env /tmp/new.env --show-values"
Enter
Sleep 1s

Type "printf '{\"PORT\": {\"type\": \"number\"}, \"DEBUG\": {\"type\": \"boolean\"}}' > /tmp/schema.json"
Enter
Type "./app diff /tmp/old.env /tmp/new.env --schema /tmp/schema.json --json"
Enter
Sleep 1.5s
