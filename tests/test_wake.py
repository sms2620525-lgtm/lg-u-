import threading
import unittest
from unittest.mock import Mock, patch
from wake import WakeController


class WakeTests(unittest.TestCase):
    def setUp(self):
        self.mic = Mock()
        self.mic.start.return_value = {'seq': 0}
        self.mic.snapshot.return_value = {'status': 'listening', 'events': []}
        self.voice = Mock()
        self.voice.snapshot.return_value = {'configured': True, 'status': 'idle'}
        self.chat = Mock()
        self.chat.lock = threading.RLock()
        self.chat.state = {'status': 'thinking'}
        self.account = Mock()
        self.account.public.return_value = {'connected': True, 'plan_enabled': True}
        with patch('wake.threading.Thread'):
            self.wake = WakeController(self.mic, self.voice, self.chat, self.account)

    def event(self, kind, text='hello', seq=1):
        self.mic.snapshot.return_value = {'status': 'listening', 'events': [{'seq':seq,'type':kind,'text':text}]}
        self.wake._tick()

    def test_background_full_conversation_and_followup(self):
        self.wake.enable()
        self.mic.stop.reset_mock()
        self.mic.start.assert_called_with('clap')
        self.event('clap_pair')
        self.mic.stop.assert_called_once()
        self.voice.speak.assert_called_once_with('네, 듣고 있어요.')
        self.voice.snapshot.return_value['status'] = 'playing'
        self.wake._tick()
        self.assertEqual(self.wake.phase, 'greeting')
        self.voice.snapshot.return_value['status'] = 'idle'
        self.wake._tick()
        self.mic.start.assert_called_with('speech')
        self.event('utterance', '질문')
        self.chat.start.assert_called_once_with('질문')
        self.assertTrue(self.chat.state['background'])
        self.chat.state['status'] = 'done'
        self.chat.snapshot.return_value = {'messages':[{'role':'assistant','text':'답변'}]}
        self.wake._tick()
        self.wake._tick()
        self.voice.speak.assert_called_with('답변')
        self.wake._tick()
        self.assertEqual(self.wake.phase, 'listening')
        self.wake.deadline = 0
        self.mic.snapshot.return_value['events'] = []
        self.wake._tick()
        self.mic.start.assert_called_with('clap')

    def test_manual_pause_resume_and_disable(self):
        self.wake.enable()
        self.wake.pause()
        self.event('clap_pair')
        self.voice.speak.assert_not_called()
        self.wake.resume()
        self.assertEqual(self.wake.phase, 'waiting')
        self.wake.pause(disable=True)
        self.wake.resume()
        self.assertFalse(self.wake.enabled)
        self.assertEqual(self.wake.phase, 'off')

    def test_missing_voice_or_account_cannot_enable_mic(self):
        self.voice.snapshot.return_value['configured'] = False
        with self.assertRaises(ValueError): self.wake.enable()
        self.mic.start.assert_not_called()
        self.account.public.return_value['connected'] = False
        with self.assertRaises(ValueError): self.wake.enable()
        self.mic.start.assert_not_called()

    def test_disable_cancels_owned_response(self):
        self.wake.enable()
        self.chat.cancel.reset_mock()
        self.voice.stop.reset_mock()
        self.wake.phase = 'thinking'
        self.wake.pause(disable=True)
        self.chat.cancel.assert_called_once()
        self.voice.stop.assert_called_once()

    def test_mic_error_is_surfaced(self):
        self.wake.enable()
        self.mic.snapshot.return_value = {'status':'error','error':'권한 없음'}
        with self.assertRaisesRegex(ValueError, '권한 없음'): self.wake._tick()
