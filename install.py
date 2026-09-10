#!/usr/bin/env python3
"""Install the user-owned Omarchy plugin and its local hardware service."""

import argparse
import datetime
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ID = "kb2uka.babyface"


def run(*args):
    subprocess.run(args, check=True)


def replace_plugin(stage, destination, backup):
    previous = stage.with_name(stage.name + "-previous")
    existed = destination.exists() or destination.is_symlink()
    if existed:
        if destination.is_symlink() or destination.is_file():
            shutil.copy2(destination, backup / "plugin", follow_symlinks=False)
        else:
            shutil.copytree(destination, backup / "plugin", symlinks=True)
        destination.rename(previous)
    try:
        stage.rename(destination)
    except OSError:
        if existed:
            previous.rename(destination)
        raise
    if existed:
        if previous.is_symlink() or previous.is_file():
            previous.unlink()
        else:
            shutil.rmtree(previous)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uninstall", action="store_true", help="Remove plugin/service; retain profiles and gains")
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    config = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    state = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "babyface-control"
    destination = config / "omarchy/plugins" / ID
    unit = config / "systemd/user/babyface-control.service"
    if args.uninstall:
        plugins = json.loads(subprocess.check_output(["omarchy-shell", "shell", "listPlugins"], text=True))
        if any(plugin.get("id") == ID and plugin.get("enabled") for plugin in plugins):
            run("omarchy", "plugin", "disable", ID)
        if unit.exists() or unit.is_symlink():
            run("systemctl", "--user", "disable", "--now", "babyface-control.service")
        if destination.is_symlink() or destination.is_file():
            destination.unlink()
        elif destination.exists():
            shutil.rmtree(destination)
        unit.unlink(missing_ok=True)
        run("systemctl", "--user", "daemon-reload")
        print(f"Removed Babyface panel. Settings remain in {state}")
        return
    for executable in ("python3", "omarchy", "systemctl"):
        if not shutil.which(executable):
            raise SystemExit(f"Missing required command: {executable}")
    import ctypes
    ctypes.CDLL("libasound.so.2")
    run("omarchy", "plugin", "validate", str(source))
    destination.parent.mkdir(parents=True, exist_ok=True)
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = state / "backups" / stamp
    backup.mkdir(parents=True)
    for file in (unit, config / "omarchy/shell.json", state / "settings.json"):
        if file.exists():
            shutil.copy2(file, backup / file.name)
    stage = Path(tempfile.mkdtemp(prefix=".babyface-", dir=destination.parent))
    try:
        for pattern in ("*.qml", "Palette.js", "manifest.json", "babyface.py", "LICENSE", "README.md"):
            for file in source.glob(pattern):
                shutil.copy2(file, stage / file.name)
        shutil.copytree(source / "babyface", stage / "babyface", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copytree(source / "docs", stage / "docs")
        replace_plugin(stage, destination, backup)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    unit.parent.mkdir(parents=True, exist_ok=True)
    executable = str(destination / "babyface.py").replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    unit.write_text(
        "[Unit]\nDescription=Babyface Pro gain control and hardware feedback\n"
        "PartOf=graphical-session.target\n\n[Service]\nType=simple\n"
        f'ExecStart=/usr/bin/python3 "{executable}" serve\n'
        "Restart=on-failure\nRestartSec=2\nNoNewPrivileges=true\nUMask=0077\n\n"
        "[Install]\nWantedBy=graphical-session.target\n"
    )
    run("systemctl", "--user", "daemon-reload")
    run("systemctl", "--user", "enable", "babyface-control.service")
    run("systemctl", "--user", "restart", "babyface-control.service")
    run("omarchy-shell", "shell", "rescanPlugins")
    run("omarchy", "plugin", "enable", ID)
    print(f"Installed {destination}\nBackups: {backup}\nOpen: omarchy-shell {ID} open")


if __name__ == "__main__":
    main()
