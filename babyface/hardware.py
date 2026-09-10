"""Nonblocking ALSA MIDI transport; audio and its routing stay attached."""

import ctypes as C
import errno
import time
from collections import deque
from pathlib import Path

from .protocol import REQUEST_STATE


def discover():
    found = []
    for entry in sorted(Path("/sys/class/sound").glob("card[0-9]*")):
        try:
            card_id = (entry / "id").read_text().strip()
            device = (entry / "device").resolve()
            while device != device.parent and not (device / "idVendor").exists():
                device = device.parent
            if (device / "idVendor").read_text().strip() != "2a39":
                continue
            if (device / "idProduct").read_text().strip() != "3fb0":
                continue
            if not card_id.startswith("Pro"):
                continue
            serial = card_id[3:]
            found.append(dict(card=card_id, serial=serial, device="Babyface Pro",
                              midi=f"hw:{card_id},0,1", usb_path=str(device)))
        except (OSError, ValueError):
            continue
    if len(found) > 1:
        raise OSError("More than one Babyface is connected; connect one device to configure it")
    return found[0] if found else None


class Midi:
    def __init__(self, name):
        self.lib = C.CDLL("libasound.so.2")
        self.lib.snd_strerror.argtypes = [C.c_int]
        self.lib.snd_strerror.restype = C.c_char_p
        self.lib.snd_rawmidi_open.argtypes = [C.POINTER(C.c_void_p), C.POINTER(C.c_void_p), C.c_char_p, C.c_int]
        for method in (self.lib.snd_rawmidi_read, self.lib.snd_rawmidi_write):
            method.argtypes = [C.c_void_p, C.c_void_p, C.c_size_t]
            method.restype = C.c_ssize_t
        self.lib.snd_rawmidi_close.argtypes = [C.c_void_p]
        self.input, self.output = C.c_void_p(), C.c_void_p()
        result = self.lib.snd_rawmidi_open(C.byref(self.input), C.byref(self.output), name.encode(), 2)
        self.check(result)
        self.buffer = C.create_string_buffer(8192)
        self.pending = deque()
        self.last_send = -1.0
        self.poll_requested = False
        self.partial = False

    def check(self, result):
        if result < 0:
            raise OSError(-result, self.lib.snd_strerror(result).decode())

    def write(self, data):
        if data != REQUEST_STATE:
            raise ValueError("Use a channel transaction for hardware writes")
        self.poll_requested = True
        self.flush()

    def set_gain(self, key, packets):
        # Keep an already-started MIDI message intact; replace all other stale
        # commands for this channel before accepting the complete new pair.
        retained = deque((k, data) for index, (k, data) in enumerate(self.pending)
                         if k != key or (index == 0 and self.partial))
        if len(retained) + len(packets) > 64:
            raise OSError("MIDI output is not draining")
        retained.extend((key, bytearray(data)) for data in packets)
        self.pending = retained

    def is_pending(self, key):
        return any(k == key for k, _ in self.pending)

    def flush(self):
        if time.monotonic() - self.last_send < 0.025:
            return
        if self.poll_requested and not self.partial and not any(key is None for key, _ in self.pending):
            self.pending.appendleft((None, bytearray(REQUEST_STATE)))
            self.poll_requested = False
        if self.pending:
            _, data = self.pending[0]
            count = self.lib.snd_rawmidi_write(self.output, bytes(data), len(data))
            if count == -errno.EAGAIN or count == 0:
                return
            self.check(count)
            del data[:count]
            self.partial = bool(data)
            if not data:
                self.pending.popleft()
                self.last_send = time.monotonic()

    def read(self):
        self.flush()
        count = self.lib.snd_rawmidi_read(self.input, self.buffer, len(self.buffer))
        if count == -errno.EAGAIN:
            return b""
        self.check(count)
        return self.buffer.raw[:count]

    def close(self):
        for handle in (self.input, self.output):
            if handle.value:
                self.lib.snd_rawmidi_close(handle)
                handle.value = None
