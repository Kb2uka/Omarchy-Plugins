import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from babyface.controller import Controller
from babyface.storage import Store


class FakeMidi:
    def __init__(self):
        self.writes = []
        self.closed = False

    def write(self, data):
        self.writes.append(data)

    def set_gain(self, key, packets):
        self.writes.extend(packets)

    def is_pending(self, key):
        return False

    def read(self):
        return b""

    def close(self):
        self.closed = True


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "settings.json"
        self.store = Store(self.path)
        self.now = 10.0
        self.control = Controller(self.store, clock=lambda: self.now)
        self.midi = FakeMidi()
        self.control.attach(self.midi, dict(serial="one"))
        self.control.receive_state(dict(mic1=40, out3=5, out4=5))

    def restore_gain(self, key):
        return next(c["restore_db"] for c in self.control.snapshot()["channels"] if c["id"] == key)

    def test_mute_retains_confirmed_gain_and_restores_only_that_output(self):
        self.control.receive_state(dict(out1=-14, out2=-10.5))
        self.control.command(dict(op="set", channel="out1", db=None))
        self.control.receive_state(dict(out1=None))
        self.assertEqual(self.restore_gain("out1"), -14)
        self.control.command(dict(op="set", channel="out1", db=self.restore_gain("out1")))
        self.assertEqual(set(self.control.pending), {"out1"})
        self.control.receive_state(dict(out1=-14))
        self.assertFalse(self.control.by_id["out1"]["muted"])
        self.assertEqual(self.control.known, dict(mic1=40, out1=-14, out2=-10.5, out3=5, out4=5))

    def test_restore_gain_does_not_use_an_unconfirmed_request(self):
        self.control.command(dict(op="set", channel="out3", db=6))
        self.control.command(dict(op="set", channel="out3", db=None))
        self.control.receive_state(dict(out3=None))
        self.assertEqual(self.restore_gain("out3"), 5)

    def test_restore_gain_survives_restart_while_muted(self):
        self.control.command(dict(op="set", channel="out3", db=None))
        self.control.receive_state(dict(out3=None))
        self.now += 0.5
        self.control.tick()
        self.control = Controller(Store(self.path), clock=lambda: self.now)
        self.control.attach(FakeMidi(), dict(serial="one"))
        self.control.receive_state(dict(out3=None))
        self.assertEqual(self.restore_gain("out3"), 5)

    def test_restore_gain_preserved_during_reconnect_mute_restore(self):
        self.control.command(dict(op="set", channel="out3", db=None))
        self.control.receive_state(dict(out3=None))
        self.control.detach()
        self.control.attach(FakeMidi(), dict(serial="one"))
        self.control.receive_state(dict(out3=0))
        self.control.receive_state(dict(out3=0))
        self.control.receive_state(dict(out3=None))
        self.assertEqual(self.restore_gain("out3"), 5)

    def test_restore_gain_isolated_by_serial_and_never_invented(self):
        self.control.detach()
        self.control.attach(FakeMidi(), dict(serial="two"))
        self.control.receive_state(dict(out3=None))
        self.assertIsNone(self.restore_gain("out3"))

    def test_manual_gain_becomes_next_restore_value(self):
        self.control.receive_state(dict(out3=0))
        self.control.receive_state(dict(out3=None))
        self.assertEqual(self.restore_gain("out3"), 0)

    def test_write_only_restore_gain_waits_for_transport(self):
        self.midi.is_pending = lambda key: True
        self.control.command(dict(op="set", channel="out7", db=-20))
        self.assertIsNone(self.restore_gain("out7"))
        self.midi.is_pending = lambda key: False
        self.control.tick()
        self.control.command(dict(op="set", channel="out7", db=None))
        self.control.tick()
        self.assertEqual(self.restore_gain("out7"), -20)

    def test_invalid_restore_values_rejected_without_changing_settings(self):
        for values in ({"mic1": 40}, {"out3": None}, {"out3": 100}, []):
            with self.subTest(values=values):
                self.path.write_text(json.dumps({"version": 1, "devices": {
                    "one": {"last": {}, "profiles": {}, "unmuted": values}}}))
                before = self.path.read_bytes()
                with self.assertRaises(ValueError):
                    Store(self.path)
                self.assertEqual(self.path.read_bytes(), before)

    def test_first_attach_adopts_hardware_without_writes(self):
        self.assertEqual(self.midi.writes, [])
        self.assertEqual(self.control.snapshot()["channels"][0]["db"], 40)

    def test_command_does_not_claim_requested_gain_before_feedback(self):
        self.control.command(dict(op="set", channel="mic1", db=41))
        self.assertEqual(self.control.by_id["mic1"]["db"], 40)
        self.assertIn("mic1", self.control.pending)
        self.control.receive_state(dict(mic1=41))
        self.assertEqual(self.control.by_id["mic1"]["db"], 41)
        self.assertNotIn("mic1", self.control.pending)

    def test_hardware_knob_updates_without_echo_writes(self):
        self.control.receive_state(dict(out3=4.5, out4=4.5))
        self.assertEqual(self.control.by_id["out3"]["db"], 4.5)
        self.assertEqual(self.midi.writes, [])

    def test_latest_command_can_return_to_reported_baseline(self):
        self.control.command(dict(op="set", channel="out3", db=4.5))
        self.control.command(dict(op="set", channel="out3", db=5))
        self.assertEqual(self.control.pending["out3"][0], 5)

    def test_unplug_during_debounce_preserves_last_hardware_change(self):
        self.store.remember("one", dict(mic1=40, out3=5, out4=5))
        self.control.receive_state(dict(mic1=41))
        self.control.detach()
        self.assertEqual(self.store.device("one")["last"]["mic1"], 41)

    def test_write_only_gain_waits_for_transport_before_profile_save(self):
        self.midi.is_pending = lambda key: True
        self.control.command(dict(op="set", channel="out7", db=-10))
        self.assertNotIn("out7", self.control.known)
        with self.assertRaisesRegex(ValueError, "pending"):
            self.control.command(dict(op="save_profile", name="Desk"))
        self.midi.is_pending = lambda key: False
        self.control.tick()
        self.assertEqual(self.control.known["out7"], -10)

    def test_unknown_optical_settings_are_never_saved_as_mute(self):
        self.control.command(dict(op="save_profile", name="Desk"))
        self.assertNotIn("out7", self.store.load("one", "Desk"))

    def test_stale_feedback_blocks_commands(self):
        self.now += 1
        with self.assertRaisesRegex(ValueError, "live Babyface"):
            self.control.command(dict(op="set", channel="out3", db=4))
        self.assertFalse(self.control.snapshot()["synced"])

    def test_timeout_reports_actual_not_requested(self):
        self.control.command(dict(op="set", channel="mic1", db=41))
        self.now += 2.6
        self.control.receive_state(dict(mic1=40))
        self.control.tick()
        self.assertIn("did not confirm", self.control.error)
        self.assertEqual(self.control.by_id["mic1"]["db"], 40)

    def test_invalid_profile_performs_no_partial_writes(self):
        with self.assertRaises(ValueError):
            self.control.apply(dict(mic1=39, out3=999))
        self.assertEqual(self.midi.writes, [])

    def test_disconnect_clears_pending_and_meters(self):
        self.control.command(dict(op="set", channel="mic1", db=41))
        self.control.detach()
        self.assertFalse(self.control.synced)
        self.assertEqual(self.control.pending, {})
        self.assertTrue(self.midi.closed)

    def test_no_feedback_connect_timeout(self):
        self.control.attach(self.midi, dict(serial="one"))
        self.now += 4
        with self.assertRaisesRegex(OSError, "No hardware feedback"):
            self.control.tick()

    def test_save_debounces_and_only_remembers_actual_values(self):
        self.control.command(dict(op="set", channel="mic1", db=41))
        self.now += 0.5
        self.control.tick()
        self.assertFalse(self.path.exists())
        self.control.receive_state(dict(mic1=41))
        self.now += 0.5
        self.control.tick()
        self.assertEqual(Store(self.path).device("one")["last"]["mic1"], 41)

    def test_saved_settings_restore_once_after_first_feedback(self):
        self.store.remember("one", dict(mic1=39))
        self.control.attach(self.midi, dict(serial="one"))
        self.assertEqual(self.midi.writes, [])
        self.control.receive_state(dict(mic1=40))
        count = len(self.midi.writes)
        self.assertGreater(count, 0)
        self.control.receive_state(dict(mic1=39))
        self.control.receive_state(dict(mic1=38))
        self.assertEqual(len(self.midi.writes), count)

    def test_other_device_never_inherits_gains(self):
        self.store.remember("one", dict(mic1=39))
        self.control.attach(self.midi, dict(serial="two"))
        self.control.receive_state(dict(mic1=11))
        self.assertEqual(self.midi.writes, [])

    def test_profile_snapshot_save_load_delete(self):
        self.control.command(dict(op="save_profile", name=" Desk "))
        self.control.receive_state(dict(mic1=38))
        self.assertEqual(self.control.snapshot()["profile"], "")
        self.control.command(dict(op="load_profile", name="Desk"))
        self.assertIn("mic1", self.control.pending)
        self.control.receive_state(dict(mic1=40))
        self.assertEqual(self.control.snapshot()["profile"], "Desk")
        self.control.command(dict(op="delete_profile", name="Desk"))
        self.assertEqual(self.control.snapshot()["profiles"], [])

    def test_atomic_save_failure_preserves_existing_profile(self):
        self.store.save("one", "Desk", dict(mic1=40))
        before = self.path.read_bytes()
        with patch("babyface.files.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.store.save("one", "Desk", dict(mic1=41))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.store.load("one", "Desk"), dict(mic1=40))
        self.assertEqual(list(self.path.parent.glob(".babyface-*")), [])

    def test_profile_names_do_not_become_file_paths(self):
        self.store.save("one", "../Desk", dict(mic1=40))
        self.assertEqual(self.store.load("one", "../Desk"), dict(mic1=40))
        self.assertFalse((self.path.parent.parent / "Desk").exists())
        for name in ("", "x" * 49, "line\nbreak", None):
            with self.assertRaises(ValueError):
                self.store.save("one", name, dict(mic1=40))

    def test_corrupted_settings_are_preserved_and_rejected(self):
        self.path.write_text('{"version": 99}')
        with self.assertRaises(ValueError):
            Store(self.path)
        self.assertEqual(json.loads(self.path.read_text())["version"], 99)


if __name__ == "__main__":
    unittest.main()
