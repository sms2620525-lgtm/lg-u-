import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from voice import Voice, extract_key

class VoiceTests(unittest.TestCase):
    def test_key_document_import_and_reject_ambiguous(self):
        key = 'example_test_key_' + 'x' * 35
        self.assertEqual(extract_key('{\\rtf1\\ansi ' + key + '}'), key)
        with self.assertRaises(ValueError):
            extract_key(key + ' ' + key)

    def test_config_never_contains_key(self):
        with tempfile.TemporaryDirectory() as d:
            v = Voice(d)
            key = 'example_test_key_' + 'x' * 35
            with patch.object(v, 'keychain', return_value=Mock()):
                result = v.save({'key_document': key, 'reference_id': 'a' * 32})
            self.assertNotIn(key, Path(v.config).read_text())
            self.assertNotIn(key, str(result))

    def test_cancel_during_generation_does_not_play(self):
        with tempfile.TemporaryDirectory() as d:
            v = Voice(d)
            entered, release = threading.Event(), threading.Event()
            def request(*args):
                entered.set()
                release.wait(2)
                return b'audio'
            with patch.object(v, 'settings', return_value={'reference_id': 'a' * 32, 'model': 's1'}), patch.object(v, 'request', side_effect=request), patch('voice.subprocess.Popen') as player:
                v.speak('hello')
                self.assertTrue(entered.wait(2))
                v.stop()
                release.set()
                # Acquire/release thread completion using enumerate rather than timing playback.
                for t in threading.enumerate():
                    if t.name.endswith('(worker)'):
                        t.join(2)
                player.assert_not_called()
                self.assertEqual(v.state, 'idle')
