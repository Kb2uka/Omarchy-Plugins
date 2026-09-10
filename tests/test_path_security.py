"""Filesystem regressions for marketplace issue 6029; no hardware or services."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import install
from babyface.storage import Store


class PathSecurityTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.config = self.root / 'config'
        self.state = self.root / 'state/babyface-control'
        self.state.mkdir(parents=True)
        self.unit = self.config / 'systemd/user/babyface-control.service'
        self.unit.parent.mkdir(parents=True)
        self.settings = self.state / 'settings.json'
        self.victim = self.root / 'victim'
        self.victim.write_text('{"version": 1, "devices": {}}')

    def install(self):
        with patch.dict(os.environ, XDG_CONFIG_HOME=str(self.config),
                        XDG_STATE_HOME=str(self.state.parent)), \
             patch('sys.argv', ['install.py']), patch.object(install, 'run'), \
             patch.object(install.shutil, 'which', return_value='/unused'), \
             patch('ctypes.CDLL'):
            install.main()

    def test_unit_symlink_cannot_overwrite_unrelated_file(self):
        before = self.victim.read_bytes()
        self.unit.symlink_to(self.victim)
        with self.assertRaises((OSError, ValueError)):
            self.install()
        self.assertEqual(self.victim.read_bytes(), before)

    def test_backup_refuses_symlink_input(self):
        shell = self.config / 'omarchy/shell.json'
        shell.parent.mkdir()
        shell.symlink_to(self.victim)
        with self.assertRaises((OSError, ValueError)):
            self.install()
        self.assertFalse(self.unit.exists())

    def test_settings_refuses_symlinks_and_hardlinks(self):
        for kind in ('symlink', 'hardlink'):
            with self.subTest(kind=kind):
                if kind == 'symlink':
                    self.settings.symlink_to(self.victim)
                else:
                    os.link(self.victim, self.settings)
                try:
                    with self.assertRaises((OSError, ValueError)):
                        Store(self.settings)
                finally:
                    self.settings.unlink()

    def test_settings_refuses_symlink_parent(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.state, target_is_directory=True)
        with self.assertRaises((OSError, ValueError)):
            Store(alias / 'settings.json').save('one', 'Desk', {'mic1': 40})
        self.assertFalse(self.settings.exists())

    def test_commit_refuses_destination_replaced_by_link(self):
        store = Store(self.settings)
        self.settings.symlink_to(self.victim)
        with self.assertRaises((OSError, ValueError)):
            store.save('one', 'Desk', {'mic1': 40})
        self.assertEqual(store.device('one')['profiles'], {})

    def test_installer_refuses_symlink_parent(self):
        external = self.root / 'external'
        external.mkdir()
        (self.config / 'omarchy').symlink_to(external, target_is_directory=True)
        with self.assertRaises((OSError, ValueError)):
            self.install()
        self.assertEqual(list(external.iterdir()), [])

    def test_settings_roundtrip_uses_private_regular_file(self):
        store = Store(self.settings)
        store.save('one', 'Desk', {'mic1': 40})
        self.assertEqual(Store(self.settings).load('one', 'Desk'), {'mic1': 40})
        self.assertEqual(self.settings.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(self.settings.read_text())['version'], 1)

    def test_install_and_upgrade_preserve_backups_and_create_private_unit(self):
        self.settings.write_text('{"version": 1, "devices": {}}')
        self.install()
        first_unit = self.unit.read_bytes()
        self.assertIn(b'ExecStart=/usr/bin/python3', first_unit)
        self.assertEqual(self.unit.stat().st_mode & 0o777, 0o600)
        plugin = self.config / 'omarchy/plugins' / install.ID
        (plugin / 'retained.txt').write_text('old plugin')
        self.install()
        self.assertEqual(self.unit.read_bytes(), first_unit)
        self.assertFalse((plugin / 'retained.txt').exists())
        backups = sorted((self.state / 'backups').iterdir())
        self.assertEqual(len(backups), 2)
        self.assertEqual((backups[-1] / 'plugin/retained.txt').read_text(), 'old plugin')
        self.assertEqual((backups[-1] / self.unit.name).read_bytes(), first_unit)
        self.assertEqual((backups[-1] / 'settings.json').read_bytes(), self.settings.read_bytes())

    def test_unit_hardlink_is_rejected_without_changing_victim(self):
        before = self.victim.read_bytes()
        os.link(self.victim, self.unit)
        with self.assertRaises(ValueError):
            self.install()
        self.assertEqual(self.victim.read_bytes(), before)
