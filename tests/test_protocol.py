import math
import unittest

from babyface.protocol import Decoder, REQUEST_STATE, channels, gain_packets, packet, peak_values, state_values, validate_gain


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.channels = {c["id"]: c for c in channels()}

    def test_state_request_is_exact_capture(self):
        self.assertEqual(REQUEST_STATE, bytes.fromhex("f0 00 20 0d 10 10 f7"))

    def test_read_actual_capture_header_and_mute(self):
        values = state_values([0x00840100, 0x0001B6DB, 0x793C85A8, 0x0058763B] + [0] * 40)
        self.assertEqual(values, dict(mic1=40, mic2=11, line3=5.5, line4=0,
                                    out1=-12, out2=-12, out3=-0.5, out4=-0.5,
                                    out5=None, out6=None))

    def test_fragmented_sysex_with_midi_clock(self):
        wire = bytes.fromhex("f0 00 20 0d 10 04 4d 78 2c 51 01 f7")
        decoder = Decoder()
        output = []
        for byte in wire:
            output.extend(decoder.feed(bytes([byte, 0xF8])))
        self.assertEqual(output, [(4, [0x1A2B3C4D])])

    def test_broken_message_resynchronizes(self):
        decoder = Decoder()
        bad = b"\xf0" + b"\x01" * 5000 + b"\xf7"
        bad += bytes.fromhex("f0 00 20 0d 10 00 7f f7")
        self.assertEqual(decoder.feed(bad + REQUEST_STATE), [(16, [])])

    def test_out_of_range_word_rejected(self):
        self.assertEqual(Decoder().feed(bytes.fromhex("f0 00 20 0d 10 00 7f 7f 7f 7f 7f f7")), [])
        with self.assertRaises(ValueError):
            packet(1, [1 << 32])

    def test_mic_coarse_fine_boundary(self):
        for gain, encoded in [(0, 0), (40, 45), (59, 83), (60, 20), (61, 52), (65, 180)]:
            data = gain_packets(self.channels["mic1"], gain)[0]
            self.assertEqual(Decoder().feed(data), [(4, [encoded << 16])])

    def test_line_half_db_encoding(self):
        data = gain_packets(self.channels["line3"], 5.5)[0]
        self.assertEqual(Decoder().feed(data), [(4, [0x000B0002])])

    def test_output_unity_master_and_companion(self):
        messages = gain_packets(self.channels["out3"], 0)
        self.assertEqual(Decoder().feed(b"".join(messages)), [(1, [0x200003E2]), (4, [0x00F30006])])

    def test_output_mute_and_no_speculative_digital_register(self):
        self.assertEqual(Decoder().feed(b"".join(gain_packets(self.channels["out3"], None))),
                         [(1, [0x3E2]), (4, [0x003B0006])])
        self.assertEqual(Decoder().feed(b"".join(gain_packets(self.channels["out12"], 0))),
                         [(1, [0x200003EB])])

    def test_meters_full_scale_and_silence(self):
        words = [0] * 40
        words[0], words[26] = 0x08000000, 0x04000000
        inputs, outputs = peak_values(words)
        self.assertEqual(inputs[:2], [0, -100])
        self.assertAlmostEqual(outputs[0], -6.020599913)

    def test_malformed_state_is_not_partially_applied(self):
        for words in ([0] * 43, [0, 0, 127, 0] + [0] * 40):
            with self.assertRaises(ValueError):
                state_values(words)

    def test_invalid_gain_rejected_before_transport(self):
        for value in (True, math.nan, math.inf, -1, 66, 40.5, None, "40"):
            with self.assertRaises(ValueError):
                validate_gain(self.channels["mic1"], value)
        with self.assertRaises(ValueError):
            validate_gain(self.channels["in5"], 0)

    def test_all_channels_and_capabilities(self):
        self.assertEqual(len(self.channels), 24)
        self.assertEqual(sum(c["adjustable"] for c in self.channels.values()), 16)
        self.assertEqual(sum(c["readback"] for c in self.channels.values()), 10)


if __name__ == "__main__":
    unittest.main()
