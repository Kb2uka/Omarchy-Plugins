"""Nonblocking ALSA sequencer transport; audio and its routing stay attached.

The sequencer lets several applications share the Babyface control port. A
raw MIDI open is exclusive, so any other MIDI application (Zeus, a DAW) that
listens to every port would lock this service out with EBUSY.
"""

import ctypes as C
import errno
import time
from collections import deque
from pathlib import Path

from .protocol import REQUEST_STATE

SYSEX = 130
LENGTH_VARIABLE = 1 << 2
QUEUE_DIRECT = 253
ADDRESS_UNKNOWN = 253
ADDRESS_SUBSCRIBERS = 254
NONBLOCK = 1
OPEN_DUPLEX = 3
CONTROL_PORT = 1  # Port 2: the sequencer numbers ports from zero
PORT_CAPS = (1 << 0) | (1 << 1) | (1 << 7)  # read, write, no export
PORT_TYPE = (1 << 1) | (1 << 20)  # generic MIDI, application
MAX_EVENTS_PER_READ = 256


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
            found.append(dict(card=card_id, card_number=int(entry.name[4:]), serial=serial,
                              device="Babyface Pro", usb_path=str(device)))
        except (OSError, ValueError):
            continue
    if len(found) > 1:
        raise OSError("More than one Babyface is connected; connect one device to configure it")
    return found[0] if found else None


class Address(C.Structure):
    _fields_ = [("client", C.c_ubyte), ("port", C.c_ubyte)]


class External(C.Structure):
    _pack_ = 1
    _fields_ = [("len", C.c_uint), ("ptr", C.c_void_p)]


class EventData(C.Union):
    _fields_ = [("ext", External), ("raw32", C.c_uint * 3)]


class Event(C.Structure):
    """snd_seq_event_t: 28 bytes on every Linux ABI the plugin supports."""
    _fields_ = [("type", C.c_ubyte), ("flags", C.c_ubyte), ("tag", C.c_ubyte), ("queue", C.c_ubyte),
                ("time", C.c_uint * 2), ("source", Address), ("dest", Address), ("data", EventData)]


class Midi:
    def __init__(self, card_number):
        self.lib = C.CDLL("libasound.so.2")
        self.declare()
        self.seq = C.c_void_p()
        self.pending = deque()
        self.last_send = -1.0
        self.poll_requested = False
        self.partial = False
        self.check(self.lib.snd_seq_open(C.byref(self.seq), b"default", OPEN_DUPLEX, NONBLOCK))
        try:
            self.lib.snd_seq_set_client_name(self.seq, b"Babyface Control")
            self.device = Address(self.find_client(card_number), CONTROL_PORT)
            port = self.lib.snd_seq_create_simple_port(self.seq, b"Babyface Control", PORT_CAPS, PORT_TYPE)
            self.check(port)
            self.port = port
            self.check(self.lib.snd_seq_connect_from(self.seq, port, self.device.client, self.device.port))
            self.check(self.lib.snd_seq_connect_to(self.seq, port, self.device.client, self.device.port))
        except BaseException:
            self.close()
            raise

    def declare(self):
        lib = self.lib
        lib.snd_strerror.argtypes = [C.c_int]
        lib.snd_strerror.restype = C.c_char_p
        lib.snd_seq_open.argtypes = [C.POINTER(C.c_void_p), C.c_char_p, C.c_int, C.c_int]
        lib.snd_seq_close.argtypes = [C.c_void_p]
        lib.snd_seq_set_client_name.argtypes = [C.c_void_p, C.c_char_p]
        lib.snd_seq_create_simple_port.argtypes = [C.c_void_p, C.c_char_p, C.c_uint, C.c_uint]
        for method in (lib.snd_seq_connect_from, lib.snd_seq_connect_to):
            method.argtypes = [C.c_void_p, C.c_int, C.c_int, C.c_int]
        lib.snd_seq_client_info_malloc.argtypes = [C.POINTER(C.c_void_p)]
        lib.snd_seq_client_info_free.argtypes = [C.c_void_p]
        lib.snd_seq_client_info_set_client.argtypes = [C.c_void_p, C.c_int]
        lib.snd_seq_client_info_get_client.argtypes = [C.c_void_p]
        lib.snd_seq_client_info_get_card.argtypes = [C.c_void_p]
        lib.snd_seq_query_next_client.argtypes = [C.c_void_p, C.c_void_p]
        lib.snd_seq_event_output_direct.argtypes = [C.c_void_p, C.POINTER(Event)]
        lib.snd_seq_event_input.argtypes = [C.c_void_p, C.POINTER(C.POINTER(Event))]

    def find_client(self, card_number):
        info = C.c_void_p()
        self.check(self.lib.snd_seq_client_info_malloc(C.byref(info)))
        try:
            self.lib.snd_seq_client_info_set_client(info, -1)
            while self.lib.snd_seq_query_next_client(self.seq, info) >= 0:
                if self.lib.snd_seq_client_info_get_card(info) == card_number:
                    return self.lib.snd_seq_client_info_get_client(info)
        finally:
            self.lib.snd_seq_client_info_free(info)
        raise OSError(errno.ENODEV, "Babyface MIDI is not registered with the ALSA sequencer")

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
            count = self.send(bytes(data))
            if count == -errno.EAGAIN or count == 0:
                return
            self.check(count)
            del data[:count]
            self.partial = bool(data)
            if not data:
                self.pending.popleft()
                self.last_send = time.monotonic()

    def send(self, data):
        # One complete SysEx message per event, so another sequencer client's
        # traffic can never land inside it.
        if not data.startswith(b"\xf0") or not data.endswith(b"\xf7"):
            raise ValueError("Only complete SysEx messages are sent")
        buffer = C.create_string_buffer(data, len(data))
        event = Event(type=SYSEX, flags=LENGTH_VARIABLE, queue=QUEUE_DIRECT,
                      source=Address(0, self.port), dest=Address(ADDRESS_SUBSCRIBERS, ADDRESS_UNKNOWN))
        event.data.ext.len, event.data.ext.ptr = len(data), C.cast(buffer, C.c_void_p)
        result = self.lib.snd_seq_event_output_direct(self.seq, C.byref(event))
        return result if result < 0 else len(data)

    def read(self):
        self.flush()
        chunks = []
        event = C.POINTER(Event)()
        for _ in range(MAX_EVENTS_PER_READ):
            result = self.lib.snd_seq_event_input(self.seq, C.byref(event))
            if result == -errno.EAGAIN:
                break
            if result == -errno.ENOSPC:
                continue  # Input overran; the decoder resynchronises on the next F0.
            self.check(result)
            item = event.contents
            # Accept SysEx only from the Babyface port; other clients can address this port directly.
            if (item.type != SYSEX or item.source.client != self.device.client
                    or item.source.port != self.device.port):
                continue
            chunks.append(C.string_at(item.data.ext.ptr, min(item.data.ext.len, 65536)))
        return b"".join(chunks)

    def close(self):
        if self.seq.value:
            self.lib.snd_seq_close(self.seq)
            self.seq.value = None
