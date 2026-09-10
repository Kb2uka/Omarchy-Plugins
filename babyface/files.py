"""Checked, descriptor-relative filesystem operations for user data on Linux."""

from contextlib import contextmanager, ExitStack
import os
from pathlib import Path
import secrets
import stat

MAX_FILE_SIZE = 1024 * 1024
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


def identity(info):
    return info.st_dev, info.st_ino


def check_directory(info, *, ancestor=False):
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError('Expected a directory')
    if info.st_uid == os.getuid():
        if info.st_mode & 0o022:
            raise ValueError('User directories must not be writable by other users')
    elif not (ancestor and info.st_uid == 0 and
              (not info.st_mode & 0o022 or info.st_mode & stat.S_ISVTX)):
        raise ValueError('Directory is not user-owned')


@contextmanager
def directory(path, *, create=False):
    """Walk without following links; pin each component until the operation ends.

    Root-owned system ancestors (including sticky /tmp) may precede the first
    user-owned component. Every component from there, and the final directory,
    must belong to this user and forbid writes by other users.
    """
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('Expected an absolute path without parent traversal')
    handles = [os.open('/', DIRECTORY_FLAGS)]
    edges = []
    owned = False
    try:
        for name in path.parts[1:]:
            parent = handles[-1]
            try:
                fd = os.open(name, DIRECTORY_FLAGS, dir_fd=parent)
            except FileNotFoundError:
                if not create:
                    raise
                # Never create directly in a system-owned ancestor.
                check_directory(os.fstat(parent))
                try:
                    os.mkdir(name, 0o700, dir_fd=parent)
                except FileExistsError:
                    pass
                fd = os.open(name, DIRECTORY_FLAGS, dir_fd=parent)
            handles.append(fd)
            info = os.fstat(fd)
            check_directory(info, ancestor=not owned)
            owned = owned or info.st_uid == os.getuid()
            edges.append((parent, name, fd))
        check_directory(os.fstat(handles[-1]))

        def verify():
            for parent, name, fd in edges:
                current = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if identity(current) != identity(os.fstat(fd)) or not stat.S_ISDIR(current.st_mode):
                    raise ValueError('Directory changed during filesystem operation')
            check_directory(os.fstat(handles[-1]))

        verify()
        yield handles[-1], verify
        verify()
    finally:
        for fd in reversed(handles):
            os.close(fd)


def check_file(info, limit=MAX_FILE_SIZE):
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_nlink != 1 or info.st_mode & 0o022):
        raise ValueError('Expected a user-owned, single-link regular file without shared writes')
    if info.st_size > limit:
        raise ValueError('File is too large')


def file_state(fd, name, limit=MAX_FILE_SIZE):
    try:
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    check_file(info, limit)
    return info


def read_at(fd, name, limit=MAX_FILE_SIZE):
    """Bounded read from the same no-follow descriptor that is validated."""
    try:
        stream = os.open(name, FILE_FLAGS, dir_fd=fd)
    except FileNotFoundError:
        return None
    try:
        before = os.fstat(stream)
        check_file(before, limit)
        chunks = []
        count = 0
        while count <= limit:
            chunk = os.read(stream, min(65536, limit + 1 - count))
            if not chunk:
                break
            chunks.append(chunk)
            count += len(chunk)
        after = os.fstat(stream)
        check_file(after, limit)
        current = file_state(fd, name, limit)
        if (count > limit or current is None or identity(current) != identity(before)
                or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise ValueError('File changed during read or exceeded its size limit')
        return b''.join(chunks)
    finally:
        os.close(stream)


def read_file(path, limit=MAX_FILE_SIZE):
    path = Path(path)
    with ExitStack() as stack:
        try:
            fd, verify = stack.enter_context(directory(path.parent))
        except FileNotFoundError:
            return None
        data = read_at(fd, path.name, limit)
        verify()
        return data


def require_file(path):
    data = read_file(path)
    if data is None:
        raise ValueError('Input file disappeared')
    return data


def atomic_write(path, data, *, limit=MAX_FILE_SIZE):
    """Publish a private exclusive temporary file inside a checked parent."""
    path = Path(path)
    if len(data) > limit:
        raise ValueError('File is too large')
    with directory(path.parent, create=True) as (fd, verify):
        before = file_state(fd, path.name, limit)
        name = '.babyface-' + secrets.token_hex(16)
        stream = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o600, dir_fd=fd)
        try:
            info = os.fstat(stream)
            check_file(info, limit)
            with os.fdopen(stream, 'wb', closefd=False) as output:
                output.write(data)
                output.flush()
                os.fsync(stream)
            verify()
            current = file_state(fd, path.name, limit)
            if ((before is None) != (current is None) or
                    before is not None and identity(before) != identity(current)):
                raise ValueError('Destination changed during write')
            temporary = file_state(fd, name, limit)
            if temporary is None or identity(temporary) != identity(info):
                raise ValueError('Temporary file changed during write')
            # rename never follows a destination symlink, including one raced in
            # after the check. Both names stay relative to the pinned directory.
            os.replace(name, path.name, src_dir_fd=fd, dst_dir_fd=fd)
            published = file_state(fd, path.name, limit)
            if published is None or identity(published) != identity(info):
                raise ValueError('Published file changed during write')
            os.fsync(fd)
        finally:
            os.close(stream)
            try:
                os.unlink(name, dir_fd=fd)
            except FileNotFoundError:
                pass


def copy_tree(source, destination):
    """Back up checked regular files; reject links and special files recursively."""
    with directory(source) as (source_fd, verify):
        with directory(destination, create=True):
            pass
        for name in os.listdir(source_fd):
            if name == "__pycache__" or name.endswith(".pyc"):
                continue
            info = os.stat(name, dir_fd=source_fd, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                copy_tree(Path(source) / name, Path(destination) / name)
            else:
                data = read_at(source_fd, name)
                if data is None:
                    raise ValueError('Backup input disappeared')
                atomic_write(Path(destination) / name, data)
        verify()
