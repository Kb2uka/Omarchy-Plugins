#!/usr/bin/env python3
"""Install the user-owned Omarchy plugin and its local hardware service."""

import argparse
from contextlib import ExitStack
import datetime
import json
import os
import shutil
import subprocess
import tempfile
import stat
import sys
from pathlib import Path

from babyface.files import (atomic_write, check_directory, check_file, copy_tree,
                            directory, identity, read_file, require_file)

ID = "kb2uka.babyface"


def run(*args):
    subprocess.run(args, check=True)


def replace_plugin(stage, destination, backup):
    previous = stage.name + "-previous"
    with directory(destination.parent) as (parent_fd, verify):
        with directory(stage):
            pass
        try:
            original = os.stat(destination.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            original = None
        if original is not None:
            if stat.S_ISDIR(original.st_mode):
                copy_tree(destination, backup / "plugin")
            else:
                check_file(original)
                atomic_write(backup / "plugin", require_file(destination))
            verify()
            current = os.stat(destination.name, dir_fd=parent_fd, follow_symlinks=False)
            if identity(current) != identity(original):
                raise ValueError("Plugin changed during backup")
            # Reserve rollback storage exclusively rather than trusting a name.
            os.mkdir(previous, 0o700, dir_fd=parent_fd)
            os.rename(destination.name, previous + "/plugin", src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        try:
            verify()
            os.rename(stage.name, destination.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        except (OSError, ValueError):
            if original is not None:
                os.rename(previous + "/plugin", destination.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
                os.rmdir(previous, dir_fd=parent_fd)
            raise
        if original is not None:
            shutil.rmtree(previous, dir_fd=parent_fd)


def main():
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11 or newer is required")
    # Recheck the setup paths on exit; each operation also validates its own path.
    with ExitStack() as parents:
        perform_install(parents)


def perform_install(parents):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uninstall", action="store_true", help="Remove plugin/service; retain profiles and gains")
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    config = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    state = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "babyface-control"
    destination = config / "omarchy/plugins" / ID
    unit = config / "systemd/user/babyface-control.service"
    for parent in (config, destination.parent, unit.parent) + (() if args.uninstall else (state,)):
        try:
            parents.enter_context(directory(parent, create=not args.uninstall))
        except FileNotFoundError:
            if not args.uninstall:
                raise
    if args.uninstall:
        # Only the unit is an input to service management. Retained state and
        # shell settings are not read or changed by the uninstaller.
        existing_unit = read_file(unit)
        plugins = json.loads(subprocess.check_output(["omarchy-shell", "shell", "listPlugins"], text=True))
        if any(plugin.get("id") == ID and plugin.get("enabled") for plugin in plugins):
            run("omarchy", "plugin", "disable", ID)
        if existing_unit is not None:
            run("systemctl", "--user", "disable", "--now", "babyface-control.service")
        try:
            with directory(destination.parent) as (fd, verify):
                try:
                    info = os.stat(destination.name, dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    info = None
                if info is not None:
                    verify()
                    if stat.S_ISDIR(info.st_mode):
                        check_directory(info)
                        shutil.rmtree(destination.name, dir_fd=fd)
                    else:
                        # Unlinking a leaf never follows its target.
                        os.unlink(destination.name, dir_fd=fd)
        except FileNotFoundError:
            pass
        try:
            with directory(unit.parent) as (fd, verify):
                verify()
                os.unlink(unit.name, dir_fd=fd)
        except FileNotFoundError:
            pass
        run("systemctl", "--user", "daemon-reload")
        print(f"Removed Babyface panel. Settings remain in {state}")
        return
    # Validate backup inputs before any replacement or lifecycle action.
    inputs = (unit, config / "omarchy/shell.json", state / "settings.json")
    backups = {file: read_file(file) for file in inputs}
    for executable in ("python3", "omarchy", "systemctl"):
        if not shutil.which(executable):
            raise SystemExit(f"Missing required command: {executable}")
    import ctypes
    ctypes.CDLL("libasound.so.2")
    run("omarchy", "plugin", "validate", str(source))
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = state / "backups" / stamp
    with directory(backup, create=True):
        pass
    for file, content in backups.items():
        if content is not None:
            atomic_write(backup / file.name, content)
    stage = Path(tempfile.mkdtemp(prefix=".babyface-", dir=destination.parent))
    try:
        for pattern in ("*.qml", "Palette.js", "manifest.json", "babyface.py", "LICENSE", "README.md"):
            for file in source.glob(pattern):
                atomic_write(stage / file.name, require_file(file))
        copy_tree(source / "babyface", stage / "babyface")
        copy_tree(source / "docs", stage / "docs")
        replace_plugin(stage, destination, backup)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    executable = str(destination / "babyface.py").replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    atomic_write(unit, (
        "[Unit]\nDescription=Babyface Pro gain control and hardware feedback\n"
        "PartOf=graphical-session.target\n\n[Service]\nType=simple\n"
        f'ExecStart=/usr/bin/python3 "{executable}" serve\n'
        "Restart=on-failure\nRestartSec=2\nNoNewPrivileges=true\nUMask=0077\n\n"
        "[Install]\nWantedBy=graphical-session.target\n"
    ).encode("utf-8"))
    run("systemctl", "--user", "daemon-reload")
    run("systemctl", "--user", "enable", "babyface-control.service")
    run("systemctl", "--user", "restart", "babyface-control.service")
    run("omarchy-shell", "shell", "rescanPlugins")
    run("omarchy", "plugin", "enable", ID)
    print(f"Installed {destination}\nBackups: {backup}\nOpen: omarchy-shell {ID} open")


if __name__ == "__main__":
    main()
