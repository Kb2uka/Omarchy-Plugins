import ctypes
import errno
import unittest
from collections import deque
from unittest.mock import patch

from babyface.hardware import Midi
from babyface.protocol import REQUEST_STATE, channels, gain_packets


class FakeLibrary:
    def __init__(self):
        self.sent = []
        self.limit = 10000

    def snd_rawmidi_write(self, handle, data, size):
        if self.limit == 0:
            return -errno.EAGAIN
        count = min(size, self.limit)
        self.sent.append(data[:count])
        return count


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.midi = object.__new__(Midi)
        self.midi.lib = FakeLibrary()
        self.midi.pending = deque()
        self.midi.last_send = -1
        self.midi.partial = False
        self.midi.poll_requested = False
        self.midi.output = ctypes.c_void_p()
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


if __name__ == "__main__":
    unittest.main()
