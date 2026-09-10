import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from babyface import files


class FilesTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.path = self.root / 'settings.json'

    def test_special_files_are_rejected_without_blocking(self):
        os.mkfifo(self.path)
        with self.assertRaises(ValueError):
            files.read_file(self.path)
        with self.assertRaises(ValueError):
            files.atomic_write(self.path, b'new')

    def test_owner_and_link_checks_on_open_descriptor(self):
        self.path.write_bytes(b'old')
        fstat = os.fstat
        for field, value in ((4, os.getuid() + 1), (3, 2)):
            def changed(fd):
                info = fstat(fd)
                if stat.S_ISREG(info.st_mode):
                    values = list(info)
                    values[field] = value
                    return os.stat_result(values)
                return info
            with self.subTest(field=field), patch.object(files.os, 'fstat', changed):
                with self.assertRaises(ValueError):
                    files.read_file(self.path)

    def test_foreign_owned_directory_is_rejected(self):
        fstat = os.fstat
        target = self.root.stat().st_ino
        def changed(fd):
            info = fstat(fd)
            if info.st_ino == target:
                values = list(info)
                values[4] = os.getuid() + 1
                return os.stat_result(values)
            return info
        with patch.object(files.os, 'fstat', changed), self.assertRaises(ValueError):
            files.atomic_write(self.path, b'new')

    def test_shared_writable_directory_is_rejected(self):
        self.root.chmod(0o777)
        with self.assertRaises(ValueError):
            files.atomic_write(self.path, b'new')
        self.assertFalse(self.path.exists())

    def test_size_boundaries_for_reads_and_writes(self):
        files.atomic_write(self.path, b'x' * 32, limit=32)
        self.assertEqual(files.read_file(self.path, limit=32), b'x' * 32)
        with self.assertRaises(ValueError):
            files.read_file(self.path, limit=31)
        with self.assertRaises(ValueError):
            files.atomic_write(self.path, b'y' * 33, limit=32)
        self.assertEqual(self.path.read_bytes(), b'x' * 32)

    def test_growth_during_read_is_bounded_and_rejected(self):
        self.path.write_bytes(b'x' * 16)
        read = os.read
        requested = []
        def growing(fd, size):
            requested.append(size)
            with self.path.open('ab') as output:
                output.write(b'x' * 32)
            return read(fd, size)
        with patch.object(files.os, 'read', growing), self.assertRaises(ValueError):
            files.read_file(self.path, limit=32)
        self.assertLessEqual(sum(requested), 33)

    def test_link_swap_before_open_is_not_followed(self):
        self.path.write_bytes(b'old')
        victim = self.root / 'victim'
        victim.write_bytes(b'private')
        open_file = os.open
        def swap(name, flags, *args, **kwargs):
            if name == self.path.name:
                self.path.unlink()
                self.path.symlink_to(victim)
            return open_file(name, flags, *args, **kwargs)
        with patch.object(files.os, 'open', swap), self.assertRaises(OSError):
            files.read_file(self.path)
        self.assertEqual(victim.read_bytes(), b'private')

    def test_parent_swap_before_rename_cannot_redirect_write(self):
        parent = self.root / 'state'
        parent.mkdir()
        self.path = parent / 'settings.json'
        self.path.write_bytes(b'old')
        target = self.root / 'target'
        target.mkdir()
        (target / 'settings.json').write_bytes(b'private')
        fsync = os.fsync
        swapped = False
        def swap(fd):
            nonlocal swapped
            if not swapped:
                swapped = True
                parent.rename(self.root / 'previous')
                parent.symlink_to(target, target_is_directory=True)
            return fsync(fd)
        with patch.object(files.os, 'fsync', swap), self.assertRaises(ValueError):
            files.atomic_write(self.path, b'new')
        self.assertEqual((target / 'settings.json').read_bytes(), b'private')
        self.assertEqual((self.root / 'previous/settings.json').read_bytes(), b'old')
        self.assertEqual(list((self.root / 'previous').glob('.babyface-*')), [])

    def test_destination_swap_before_rename_is_rejected(self):
        self.path.write_bytes(b'old')
        victim = self.root / 'victim'
        victim.write_bytes(b'private')
        fsync = os.fsync
        def swap(fd):
            self.path.unlink()
            self.path.symlink_to(victim)
            return fsync(fd)
        with patch.object(files.os, 'fsync', swap), self.assertRaises(ValueError):
            files.atomic_write(self.path, b'new')
        self.assertEqual(victim.read_bytes(), b'private')
        self.assertEqual(list(self.root.glob('.babyface-*')), [])

    def test_rename_failure_keeps_original_and_cleans_temporary(self):
        self.path.write_bytes(b'old')
        with patch.object(files.os, 'replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                files.atomic_write(self.path, b'new')
        self.assertEqual(self.path.read_bytes(), b'old')
        self.assertEqual(list(self.root.glob('.babyface-*')), [])

    def test_backup_rejects_nested_symlink(self):
        source = self.root / 'plugin'
        source.mkdir()
        (source / 'link').symlink_to('/etc/passwd')
        with self.assertRaises(OSError):
            files.copy_tree(source, self.root / 'backup')
        self.assertFalse((self.root / 'backup/link').exists())

    def test_relative_and_parent_traversal_paths_rejected(self):
        for path in (Path('relative/settings.json'), self.root / '../settings.json'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                files.atomic_write(path, b'new')
