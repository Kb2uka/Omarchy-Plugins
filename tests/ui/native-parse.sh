#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
artifact_dir=".artifacts/feat_babyface_panel"
harness="$(mktemp -d "${TMPDIR:-/tmp}/babyface-qml-XXXXXX")"
trap 'rm -rf "$harness"' EXIT
mkdir -p "$artifact_dir" "$harness/babyface"
cp ./*.qml ./*.js "$harness/babyface/"
cp -r /usr/share/omarchy/shell/Ui /usr/share/omarchy/shell/Commons "$harness/"
cat > "$harness/babyface/babyface.py" <<'PY'
import json
import sys
print(json.dumps({'connected': False, 'channels': [], 'profiles': []}), flush=True)
for line in sys.stdin:
    pass
PY
cat > "$harness/shell.qml" <<'QML'
import QtQuick
import Quickshell
import "babyface" as Babyface
ShellRoot {
  Babyface.Panel {}
  Timer { interval: 500; running: true; onTriggered: Qt.quit() }
}
QML
QT_QPA_PLATFORM=wayland quickshell -p "$harness" --no-color > "$artifact_dir/native-parse.log" 2>&1
cat "$artifact_dir/native-parse.log"
if ! rg -q 'Configuration Loaded' "$artifact_dir/native-parse.log"; then exit 1; fi
if rg -q 'ERROR|ReferenceError|TypeError' "$artifact_dir/native-parse.log"; then exit 1; fi
