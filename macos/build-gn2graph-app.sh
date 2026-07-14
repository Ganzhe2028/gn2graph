#!/usr/bin/env bash
# Build a Spotlight-launchable gn2graph.app for macOS.
# The resulting app can be:
#   - launched from Spotlight (⌘Space → "gn2graph")
#   - dragged to the Dock
#   - used as a drop target for PDF files
#
# Run this after setting up the project venv:
#   ./macos/build-gn2graph-app.sh
set -euo pipefail

PROJECT_ROOT="/Users/mac/New/gn2graph"
OUTPUT_DIR="${OUTPUT_DIR:-$HOME/Applications}"
APP_NAME="gn2graph"
APP_PATH="$OUTPUT_DIR/$APP_NAME.app"

if [[ ! -f "$PROJECT_ROOT/.venv/bin/python" ]]; then
  echo "error: venv python not found at $PROJECT_ROOT/.venv/bin/python" >&2
  echo "Run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi

if [[ ! -f "$PROJECT_ROOT/gn2graph.py" ]]; then
  echo "error: gn2graph.py not found at $PROJECT_ROOT/gn2graph.py" >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "$TMP_DIR/launcher.applescript" <<'APPLESCRIPT'
property projectRoot : "/Users/mac/New/gn2graph"
property pythonPath : projectRoot & "/.venv/bin/python"
property scriptPath : projectRoot & "/gn2graph.py"

on processPdf(pdfAlias)
	set pdfPath to POSIX path of pdfAlias

	if not (pdfPath ends with ".pdf" or pdfPath ends with ".PDF") then
		display notification "gn2graph only accepts PDF files" with title "gn2graph"
		return
	end if

	set pdfDir to do shell script "dirname " & quoted form of pdfPath
	set pdfName to do shell script "basename " & quoted form of pdfPath

	if pdfName ends with ".pdf" then
		set baseName to text 1 thru -5 of pdfName
	else
		set baseName to text 1 thru -6 of pdfName
	end if

	set outputDir to pdfDir & "/" & baseName & "_tiles"
	set cmd to quoted form of pythonPath & " " & quoted form of scriptPath & " " & quoted form of pdfPath & " -o " & quoted form of outputDir

	try
		do shell script cmd
		display notification "Tiles saved to " & baseName & "_tiles" with title "gn2graph"
	on error errMsg
		display alert "gn2graph failed" message errMsg buttons {"OK"} default button "OK" as critical
	end try
end processPdf

on run
	set pdfFile to choose file with prompt "Select a GoodNotes PDF to slice:" of type {"com.adobe.pdf"}
	processPdf(pdfFile)
end run

on open droppedItems
	repeat with anItem in droppedItems
		processPdf(anItem)
	end repeat
end open
APPLESCRIPT

/usr/bin/osacompile -o "$APP_PATH" "$TMP_DIR/launcher.applescript"

if [[ ! -d "$APP_PATH" ]]; then
  echo "error: app bundle was not created" >&2
  exit 1
fi

echo "Built: $APP_PATH"
echo ""
echo "Next steps:"
echo "  1. Open Spotlight (⌘Space) and type 'gn2graph' to launch it."
echo "  2. Or drag the app to your Dock and drop PDFs onto it."
echo "  3. First launch may ask for accessibility/notification permissions; allow them."
