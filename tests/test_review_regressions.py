from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import install
from babyface.files import directory


class ReviewRegressionTests(unittest.TestCase):
    def test_validation_failure_after_move_restores_original_plugin(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stage, destination, backup = root / 'stage', root / 'plugin', root / 'backup'
            for path in (stage, destination, backup):
                path.mkdir()
            (destination / 'value').write_text('old')
            calls = 0

            @contextmanager
            def fail_second_verify(path, **kwargs):
                nonlocal calls
                with directory(path, **kwargs) as (fd, verify):
                    def checked():
                        nonlocal calls
                        verify()
                        if path == root:
                            calls += 1
                            if calls == 2:
                                raise ValueError('Parent changed')
                    yield fd, checked

            with patch.object(install, 'directory', fail_second_verify):
                with self.assertRaises(ValueError):
                    install.replace_plugin(stage, destination, backup)
            self.assertEqual((destination / 'value').read_text(), 'old')
            self.assertFalse((root / 'stage-previous').exists())

    def test_uninstall_does_not_read_retained_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / 'config'
            state = root / 'state'
            config.mkdir()
            settings = state / 'babyface-control/settings.json'
            settings.parent.mkdir(parents=True)
            settings.symlink_to(root / 'missing')
            with patch.dict(os.environ, XDG_CONFIG_HOME=str(config), XDG_STATE_HOME=str(state)), \
                 patch('sys.argv', ['install.py', '--uninstall']), \
                 patch.object(install.subprocess, 'check_output', return_value='[]'), \
                 patch.object(install, 'run'):
                install.main()
            self.assertTrue(settings.is_symlink())

    def test_old_python_reports_requirement_before_mutation(self):
        with patch('sys.version_info', (3, 10)), patch.object(install, 'perform_install') as run:
            with self.assertRaisesRegex(SystemExit, 'Python 3.11'):
                install.main()
            run.assert_not_called()

    def test_missing_source_has_clear_error(self):
        from babyface.files import require_file
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'Input file disappeared'):
                require_file(Path(folder) / 'missing')

    def test_uninstall_unlinks_plugin_alias_without_touching_target(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config, state = root / 'config', root / 'state'
            target = root / 'target'
            target.mkdir()
            (target / 'keep').write_text('keep')
            plugin = config / 'omarchy/plugins' / install.ID
            plugin.parent.mkdir(parents=True)
            plugin.symlink_to(target, target_is_directory=True)
            with patch.dict(os.environ, XDG_CONFIG_HOME=str(config), XDG_STATE_HOME=str(state)), \
                 patch('sys.argv', ['install.py', '--uninstall']), \
                 patch.object(install.subprocess, 'check_output', return_value='[]'), \
                 patch.object(install, 'run'):
                install.main()
            self.assertFalse(plugin.is_symlink())
            self.assertEqual((target / 'keep').read_text(), 'keep')

    def test_uninstall_rejects_unsafe_unit_before_service_commands(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / 'config'
            unit = config / 'systemd/user/babyface-control.service'
            unit.parent.mkdir(parents=True)
            target = root / 'unit'
            target.write_text('[Service]')
            unit.symlink_to(target)
            with patch.dict(os.environ, XDG_CONFIG_HOME=str(config), XDG_STATE_HOME=str(root / 'state')), \
                 patch('sys.argv', ['install.py', '--uninstall']), \
                 patch.object(install, 'run') as run, \
                 patch.object(install.subprocess, 'check_output') as read:
                with self.assertRaises(OSError):
                    install.main()
                run.assert_not_called()
                read.assert_not_called()
            self.assertEqual(target.read_text(), '[Service]')
