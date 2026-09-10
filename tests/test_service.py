import selectors
import tempfile
import unittest
from pathlib import Path

from babyface import service


class ServiceTests(unittest.TestCase):
    def test_corrupt_settings_are_reported_without_opening_hardware_or_rewriting(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            path.write_text('{"version": 99}')
            controller = service.load_controller(path)
            snapshot = controller.snapshot()
            self.assertFalse(snapshot['connected'])
            self.assertFalse(snapshot['persisted'])
            self.assertIn(str(path), snapshot['error'])
            self.assertIn('restore a backup', snapshot['error'])
            self.assertIsNone(controller.midi)
            with self.assertRaisesRegex(ValueError, 'restore a backup'):
                controller.command({'op': 'set', 'channel': 'out3', 'db': 0})
            self.assertEqual(path.read_text(), '{"version": 99}')

    def test_partial_command_does_not_arm_empty_socket_writes(self):
        self.assertEqual(service.client_events({'output': bytearray()}), selectors.EVENT_READ)
        self.assertEqual(service.client_events({'output': bytearray(b'ok\n')}),
                         selectors.EVENT_READ | selectors.EVENT_WRITE)
