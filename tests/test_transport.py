import ctypes
import errno
import unittest
from collections import deque
from unittest.mock import patch

from babyface.hardware import SYSEX, Address, Event, Midi
from babyface.protocol import REQUEST_STATE, channels, gain_packets, packet


class FakeLibrary:
    def __init__(self):
        self.sent = []
        self.limit = 10000

    def send(self, data):
        if self.limit == 0:
            return -errno.EAGAIN
        count = min(len(data), self.limit)
        self.sent.append(data[:count])
        return count


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.midi = object.__new__(Midi)
        self.midi.lib = FakeLibrary()
        self.midi.send = self.midi.lib.send
        self.midi.pending = deque()
        self.midi.last_send = -1
        self.midi.partial = False
        self.midi.poll_requested = False
        self.now = 1.0
        mock = patch("babyface.hardware.time.monotonic", lambda: self.now)
        mock.start()
        self.addCleanup(mock.stop)
        self.ch = {c["id"]: c for c in channels()}

    def test_hundreds_of_slider_moves_coalesce_to_latest_target(self):
        for n in range(500):
            self.midi.set_gain("out3", gain_packets(self.ch["out3"], (n % 10) / 2))
        expected = gain_packets(self.ch["out3"], 4.5)
        self.assertEqual([bytes(data) for _, data in self.midi.pending], expected)
        self.midi.flush()
        self.now += .03
        self.midi.flush()
        self.assertEqual(self.midi.lib.sent, expected)

    def test_polls_take_priority_during_profile_writes(self):
        for n in range(1, 13):
            self.midi.set_gain(f"out{n}", gain_packets(self.ch[f"out{n}"], -10))
        self.midi.write(REQUEST_STATE)
        self.assertEqual(self.midi.lib.sent, [REQUEST_STATE])
        self.assertTrue(self.midi.is_pending("out12"))

    def test_repeated_full_profiles_cannot_exhaust_queue_capacity(self):
        self.midi.set_gain("out3", gain_packets(self.ch["out3"], 5))
        self.midi.lib.limit = 3
        self.midi.flush()
        self.midi.lib.limit = 0
        for n in range(100):
            for key, channel in self.ch.items():
                if channel["adjustable"]:
                    self.midi.set_gain(key, gain_packets(channel, n % 2))
            self.midi.write(REQUEST_STATE)
            self.assertLessEqual(len(self.midi.pending), 24)

    def test_spacing_is_enforced(self):
        self.midi.set_gain("out3", gain_packets(self.ch["out3"], 5))
        self.midi.flush()
        self.now += .01
        self.midi.flush()
        self.assertEqual(len(self.midi.lib.sent), 1)
        self.now += .02
        self.midi.flush()
        self.assertEqual(len(self.midi.lib.sent), 2)

    def test_full_message_pair_is_rejected_atomically(self):
        self.midi.pending.extend((f"key{i}", bytearray(b"data")) for i in range(64))
        before = list(self.midi.pending)
        with self.assertRaises(OSError):
            self.midi.set_gain("out3", gain_packets(self.ch["out3"], 0))
        self.assertEqual(list(self.midi.pending), before)

    def test_partial_message_finishes_before_replacement_and_poll(self):
        first = gain_packets(self.ch["out3"], 4.5)
        final = gain_packets(self.ch["out3"], 5)
        self.midi.set_gain("out3", first)
        self.midi.lib.limit = 3
        self.midi.flush()
        self.midi.set_gain("out3", final)
        self.midi.write(REQUEST_STATE)
        self.midi.lib.limit = 10000
        for _ in range(8):
            self.now += .03
            self.midi.flush()
        self.assertEqual(b"".join(self.midi.lib.sent), first[0] + REQUEST_STATE + b"".join(final))

    def test_backpressure_does_not_accumulate_poll_requests(self):
        self.midi.lib.limit = 0
        for _ in range(100):
            self.now += .1
            self.midi.write(REQUEST_STATE)
        self.assertEqual(len(self.midi.pending), 1)


class SequencerTests(unittest.TestCase):
    """The sequencer path, with libasound replaced by an in-memory queue."""

    def setUp(self):
        self.midi = object.__new__(Midi)
        self.midi.seq = ctypes.c_void_p(1)
        self.midi.port = 0
        self.midi.device = Address(32, 1)
        self.midi.pending = deque()
        self.midi.last_send = -1
        self.midi.partial = False
        self.midi.poll_requested = False
        self.midi.lib = SequencerLibrary()

    def test_reads_sysex_only_from_the_babyface_control_port(self):
        report = packet(0, [1] * 44)
        self.midi.lib.queue = [(SYSEX, 32, 1, report[:200]), (SYSEX, 40, 0, report), (SYSEX, 40, 1, report),
                               (SYSEX, 32, 0, report), (6, 32, 1, b"\x90\x40\x7f"),
                               (SYSEX, 32, 1, report[200:])]
        self.assertEqual(self.midi.read(), report)

    def test_overrun_is_skipped_and_reading_continues(self):
        self.midi.lib.queue = [-errno.ENOSPC, (SYSEX, 32, 1, REQUEST_STATE)]
        self.assertEqual(self.midi.read(), REQUEST_STATE)

    def test_sends_one_complete_sysex_event_to_subscribers(self):
        self.assertEqual(self.midi.send(REQUEST_STATE), len(REQUEST_STATE))
        event_type, flags, queue, dest, data = self.midi.lib.sent[0]
        self.assertEqual((event_type, flags, queue, dest, data), (SYSEX, 4, 253, (254, 253), REQUEST_STATE))
        with self.assertRaises(ValueError):
            self.midi.send(b"\x90\x40\x7f")

    def test_one_read_is_bounded(self):
        self.midi.lib.queue = [(SYSEX, 32, 1, b"\xf8")] * 261
        self.assertEqual(len(self.midi.read()), 256)
        self.assertEqual(len(self.midi.lib.queue), 5)

    def test_open_subscribes_both_ways_to_the_control_port_of_the_card(self):
        lib = OpenLibrary(card_clients={2: 24, 4: 32})
        with patch("babyface.hardware.C.CDLL", lambda name: lib):
            midi = Midi(4)
        self.assertEqual(lib.connections, [("from", 7, 32, 1), ("to", 7, 32, 1)])
        self.assertEqual((midi.device.client, midi.device.port, midi.port), (32, 1, 7))
        midi.close()
        midi.close()
        self.assertEqual(lib.closed, 1)

    def test_failed_open_closes_the_sequencer(self):
        lib = OpenLibrary(card_clients={2: 24})
        with patch("babyface.hardware.C.CDLL", lambda name: lib), self.assertRaises(OSError):
            Midi(4)
        self.assertEqual(lib.closed, 1)
        lib = OpenLibrary(card_clients={4: 32}, connect_result=-errno.EBUSY)
        with patch("babyface.hardware.C.CDLL", lambda name: lib), self.assertRaises(OSError):
            Midi(4)
        self.assertEqual(lib.closed, 1)

    def test_event_layout_matches_alsa(self):
        self.assertEqual(ctypes.sizeof(Event), 28)
        self.assertEqual(Event.data.offset, 16)


class SequencerLibrary:
    def __init__(self):
        self.queue, self.sent, self.keep = [], [], []

    def snd_seq_event_output_direct(self, seq, event):
        event = event._obj
        data = ctypes.string_at(event.data.ext.ptr, event.data.ext.len)
        self.sent.append((event.type, event.flags, event.queue, (event.dest.client, event.dest.port), data))
        return 28 + len(data)

    def snd_seq_event_input(self, seq, pointer):
        if not self.queue:
            return -errno.EAGAIN
        item = self.queue.pop(0)
        if isinstance(item, int):
            return item
        event_type, client, port, data = item
        buffer = ctypes.create_string_buffer(data, len(data))
        event = Event(type=event_type, source=Address(client, port))
        event.data.ext.len, event.data.ext.ptr = len(data), ctypes.cast(buffer, ctypes.c_void_p)
        self.keep.append((buffer, event))
        pointer._obj.contents = event
        return len(self.queue)


class Function:
    """Stands in for a libasound symbol: accepts argtypes and forwards calls."""

    def __init__(self, call):
        self.call = call

    def __call__(self, *args):
        return self.call(*args)


class OpenLibrary:
    def __init__(self, card_clients, connect_result=0):
        self.cards = sorted(card_clients.items(), key=lambda item: item[1])
        self.connect_result, self.connections, self.closed, self.index = connect_result, [], 0, -1

    def __getattr__(self, name):
        calls = dict(
            snd_strerror=lambda code: b"error",
            snd_seq_open=lambda handle, name, mode, flags: setattr(handle._obj, "value", 1) or 0,
            snd_seq_close=lambda seq: setattr(self, "closed", self.closed + 1) or 0,
            snd_seq_set_client_name=lambda seq, name: 0,
            snd_seq_create_simple_port=lambda seq, name, caps, kind: 7,
            snd_seq_connect_from=lambda seq, port, client, dest: self.connect("from", port, client, dest),
            snd_seq_connect_to=lambda seq, port, client, dest: self.connect("to", port, client, dest),
            snd_seq_client_info_malloc=lambda info: 0,
            snd_seq_client_info_free=lambda info: None,
            snd_seq_client_info_set_client=lambda info, client: setattr(self, "index", -1),
            snd_seq_query_next_client=lambda seq, info: self.next_client(),
            snd_seq_client_info_get_card=lambda info: self.cards[self.index][0],
            snd_seq_client_info_get_client=lambda info: self.cards[self.index][1],
            snd_seq_event_output_direct=lambda seq, event: 0,
            snd_seq_event_input=lambda seq, event: -errno.EAGAIN,
        )
        if name not in calls:
            raise AttributeError(name)
        function = Function(calls[name])
        setattr(self, name, function)
        return function

    def next_client(self):
        self.index += 1
        return 0 if self.index < len(self.cards) else -errno.ENOENT

    def connect(self, direction, port, client, dest):
        self.connections.append((direction, port, client, dest))
        return self.connect_result


if __name__ == "__main__":
    unittest.main()
