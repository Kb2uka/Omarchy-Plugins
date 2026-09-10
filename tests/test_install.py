import errno
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import install


class InstallTests(unittest.TestCase):
    def setUp(self):
        def registered_plugins(*args, **kwargs):
            manifest = Path(os.environ['XDG_CONFIG_HOME']) / 'omarchy/plugins' / install.ID / 'manifest.json'
            return json.dumps([{'id': install.ID, 'enabled': True}] if manifest.is_file() else [])
        shell_patch = patch.object(install.subprocess, 'check_output', side_effect=registered_plugins)
        self.shell_list = shell_patch.start()
        self.addCleanup(shell_patch.stop)

    def test_uninstall_twice_retains_profiles_and_handles_partial_install(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config, state = root / 'config', root / 'state'
            plugin = config / 'omarchy/plugins' / install.ID
            plugin.mkdir(parents=True)
            (plugin / 'manifest.json').write_text('{}')
            settings = state / 'babyface-control/settings.json'
            settings.parent.mkdir(parents=True)
            settings.write_text('saved profiles')
            calls = []
            def run(*args):
                calls.append(args)
                if args[:3] == ('systemctl', '--user', 'disable'):
                    raise AssertionError('Must not disable a missing unit')
                if args[:3] == ('omarchy', 'plugin', 'disable'):
                    self.assertTrue(plugin.exists())
            with patch.dict(os.environ, XDG_CONFIG_HOME=str(config), XDG_STATE_HOME=str(state)), \
                 patch('sys.argv', ['install.py', '--uninstall']), patch.object(install, 'run', run):
                install.main()
                install.main()
            self.assertFalse(plugin.exists())
            self.assertEqual(settings.read_text(), 'saved profiles')
            self.assertEqual(calls.count(('omarchy', 'plugin', 'disable', install.ID)), 1)

    def test_upgrade_backup_supports_separate_filesystems(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            destination, stage, backup = root / 'config/plugin', root / 'config/stage', root / 'state/backup'
            destination.mkdir(parents=True)
            stage.mkdir()
            backup.mkdir(parents=True)
            (destination / 'value').write_text('old')
            (stage / 'value').write_text('new')
            rename = os.rename
            def same_mount(path, target, **kwargs):
                original_target = target
                target_parent = kwargs.get('dst_dir_fd')
                if target_parent is not None:
                    target = Path(os.readlink(f'/proc/self/fd/{target_parent}')) / target
                if 'state' in Path(target).parts:
                    raise OSError(errno.EXDEV, 'Cross-device link')
                return rename(path, original_target, **kwargs)
            # Prove the guard rejects a cross-filesystem move before checking
            # that replacement succeeds without attempting one.
            with self.assertRaises(OSError) as error:
                same_mount(stage, backup / 'probe')
            self.assertEqual(error.exception.errno, errno.EXDEV)
            with patch.object(os, 'rename', same_mount):
                install.replace_plugin(stage, destination, backup)
            self.assertEqual((destination / 'value').read_text(), 'new')
            self.assertEqual((backup / 'plugin/value').read_text(), 'old')
            self.assertFalse(stage.exists())

    def test_failed_replacement_restores_old_installation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            destination, stage, backup = root / 'plugin', root / 'stage', root / 'backup'
            for path in (destination, stage, backup):
                path.mkdir()
            (destination / 'value').write_text('old')
            rename = os.rename
            def fail_stage(path, target, **kwargs):
                if path == stage.name:
                    raise OSError('Replacement failed')
                return rename(path, target, **kwargs)
            with patch.object(os, 'rename', fail_stage), self.assertRaises(OSError):
                install.replace_plugin(stage, destination, backup)
            self.assertEqual((destination / 'value').read_text(), 'old')
            self.assertEqual((backup / 'plugin/value').read_text(), 'old')

    def test_dangling_symlink_is_rejected_without_replacement(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            destination = root / 'plugin'
            stage = root / 'stage'
            backup = root / 'backup'
            stage.mkdir()
            backup.mkdir()
            (stage / 'value').write_text('new')
            destination.symlink_to(root / 'missing')
            with self.assertRaises(ValueError):
                install.replace_plugin(stage, destination, backup)
            self.assertTrue(destination.is_symlink())
            self.assertEqual(destination.readlink(), root / 'missing')
            self.assertFalse((backup / 'plugin').exists())

    def test_plain_file_is_backed_up_and_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            destination = root / 'plugin'
            stage = root / 'stage'
            backup = root / 'backup'
            stage.mkdir()
            backup.mkdir()
            (stage / 'value').write_text('new')
            destination.write_text('stray file')
            install.replace_plugin(stage, destination, backup)
            self.assertEqual((destination / 'value').read_text(), 'new')
            self.assertEqual((backup / 'plugin').read_text(), 'stray file')

    def test_uninstall_stray_file_without_registered_plugin(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / 'config'
            state = root / 'state'
            destination = config / 'omarchy/plugins' / install.ID
            destination.parent.mkdir(parents=True)
            destination.write_text('stray file')

            def run(*args):
                if args[0] == 'omarchy':
                    raise AssertionError('No manifest means no registered plugin to disable')

            with patch.dict(os.environ, XDG_CONFIG_HOME=str(config), XDG_STATE_HOME=str(state)), \
                 patch('sys.argv', ['install.py', '--uninstall']), patch.object(install, 'run', run):
                install.main()
            self.assertFalse(destination.exists())

    def test_uninstall_registered_plugin_without_manifest_stops_unit_and_reloads(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'config'
            state = Path(folder) / 'state'
            destination = config / 'omarchy/plugins' / install.ID
            destination.mkdir(parents=True)
            unit = config / 'systemd/user/babyface-control.service'
            unit.parent.mkdir(parents=True)
            unit.write_text('[Service]')
            self.shell_list.side_effect = None
            self.shell_list.return_value = json.dumps([{'id': install.ID, 'enabled': True}])
            with patch.dict(os.environ, XDG_CONFIG_HOME=str(config), XDG_STATE_HOME=str(state)), \
                 patch('sys.argv', ['install.py', '--uninstall']), patch.object(install, 'run') as run:
                install.main()
            self.assertEqual([call.args for call in run.call_args_list], [
                ('omarchy', 'plugin', 'disable', install.ID),
                ('systemctl', '--user', 'disable', '--now', 'babyface-control.service'),
                ('systemctl', '--user', 'daemon-reload'),
            ])
            self.assertFalse(destination.exists())
            self.assertFalse(unit.exists())
