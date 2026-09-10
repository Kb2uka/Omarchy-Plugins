#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
artifact_dir=".artifacts/feat_babyface_panel"
mkdir -p "$artifact_dir"
runner="${QML_TEST_RUNNER:-/usr/lib/qt6/bin/qmltestrunner}"
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software "$runner" -input tests/ui -o "$artifact_dir/qml-tests.txt",txt
cat "$artifact_dir/qml-tests.txt"
test -s "$artifact_dir/panel-fixture.png"
test -s "$artifact_dir/panel-narrow-fixture.png"
