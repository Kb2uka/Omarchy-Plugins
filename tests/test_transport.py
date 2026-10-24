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
        self.midi.lib.queue = [(SYSEX, 32, 1, report[:200]), (SYSEX, 40, 0, report),
                               (SYSEX, 32, 0, report), (6, 32, 1, b"\x90\x40\x7f"),
                               (SYSEX, 32, 1, report[200:])]
        self.assertEqual(self.midi.read(), report)

    def test_overrun_is_skipped_and_reading_continues(self):
        self.midi.lib.queue = [-errno.ENOSPC, (SYSEX, 32, 1, REQUEST_STATE)]
        self.assertEqual(self.midi.read(), REQUEST_STATE)

    def test_sends_one_complete_sysex_event_to_subscribers(self):
        self.assertEqual(self.midi.send(REQUEST_STATE), len(REQUEST_STATE))
        event_type, flags, dest, data = self.midi.lib.sent[0]
        self.assertEqual((event_type, flags, dest, data), (SYSEX, 4, (254, 253), REQUEST_STATE))
        with self.assertRaises(ValueError):
            self.midi.send(b"\x90\x40\x7f")

    def test_event_layout_matches_alsa(self):
        self.assertEqual(ctypes.sizeof(Event), 28)
        self.assertEqual(Event.data.offset, 16)


class SequencerLibrary:
    def __init__(self):
        self.queue, self.sent, self.keep = [], [], []

    def snd_seq_event_output_direct(self, seq, event):
        event = event._obj
        data = ctypes.string_at(event.data.ext.ptr, event.data.ext.len)
        self.sent.append((event.type, event.flags, (event.dest.client, event.dest.port), data))
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


if __name__ == "__main__":
    unittest.main()
