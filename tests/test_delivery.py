"""Final-image delivery and partial-failure regressions."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from streamlit.testing.v1 import AppTest

import engine
from chat_support import image_artifacts

ROOT = Path(__file__).resolve().parents[1]


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        (ROOT / '输出').mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / '输出')
        self.addCleanup(self.tmp.cleanup)
        self.cutout = Path(self.tmp.name) / '商品_抠图_test.png'
        self.scene = Path(self.tmp.name) / '商品_场景_test.png'
        Image.new('RGBA', (8, 8)).save(self.cutout)
        Image.new('RGB', (8, 8)).save(self.scene)

    def test_cutouts_never_become_deliverables(self):
        self.assertEqual(image_artifacts('remove_background', {
            'ok': True, 'image_path': str(self.cutout)}), [])
        self.assertEqual(image_artifacts('handoff_to_worker', {'ok': True, 'artifacts': [
            {'tool': 'remove_background', 'image_path': str(self.cutout)},
            {'tool': 'generate_scene_image', 'image_path': str(self.scene)},
        ]}), [str(self.scene)])

    def test_transient_tls_failure_retries_generation(self):
        import io
        import ssl
        from types import SimpleNamespace as NS
        from unittest.mock import Mock
        from tools import generate_scene_image as generator
        buffer = io.BytesIO()
        Image.new('RGB', (8, 8)).save(buffer, format='PNG')
        import base64
        import httpx
        calls = []
        def handler(request):
            calls.append(request)
            if len(calls) == 1:
                raise ssl.SSLEOFError(8, 'EOF occurred in violation of protocol')
            return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(buffer.getvalue()).decode()}]})
        with patch.object(generator, 'http_client', side_effect=lambda *a, **k:
                          httpx.Client(transport=httpx.MockTransport(handler))), \
                patch.object(generator.time, 'sleep'), \
                patch.object(generator.config, 'ARK_API_KEY', 'offline-key'):
            result = generator.run(str(self.cutout), 'a gradient product scene')
        self.assertTrue(result['ok'], result)
        self.addCleanup((ROOT / result['image_path']).unlink)
        self.assertEqual(len(calls), 2)

    def test_existing_history_hides_cutouts(self):
        at = AppTest.from_file(str(ROOT / 'pages_test.py'))
        at.session_state['messages'] = [{'role': 'assistant', 'content': '已完成',
                                         'images': [str(self.cutout), str(self.scene)]}]
        at.run()
        self.assertFalse(list(at.exception))
        self.assertEqual(len(at.get('download_button')), 1)

    def test_partial_success_uses_warning_and_retries_only_remaining(self):
        def run(name, messages, callback):
            callback('worker', 'generate_scene_image', {'prompt': 'home', 'image_path': str(self.cutout)},
                     {'ok': True, 'image_path': str(self.scene)})
            callback('worker', 'generate_scene_image', {'prompt': 'gradient', 'image_path': str(self.cutout)},
                     {'ok': False, 'error': 'Server disconnected without sending a response.'})
            return '已成功生成1张，路径：`输出/foo.png`。其他未完成'
        at = AppTest.from_file(str(ROOT / 'pages_test.py'))
        at.session_state['messages'] = [{'role': 'user', 'content': '拍2张'}]
        at.session_state['agent_messages'] = [{'role': 'user', 'content': '拍2张'}]
        at.session_state['need_reply'] = True
        with patch.object(engine, 'run_agent', side_effect=run):
            at.run()
        self.assertFalse(list(at.exception))
        self.assertEqual(len(at.error), 0, '部分成功不能把成功文字整段标红')
        self.assertEqual(len(at.warning), 1)
        self.assertNotIn('路径：', at.session_state['messages'][-1]['content'])
        self.assertEqual(len(at.session_state['messages'][-1]['retry_tasks']), 1)

    def test_handoff_contains_only_final_images(self):
        def run(name, messages, callback, **kwargs):
            callback(name, 'remove_background', {}, {'ok': True, 'image_path': str(self.cutout)})
            callback(name, 'generate_scene_image', {}, {'ok': True, 'image_path': str(self.scene)})
            return '已完成'
        with patch.object(engine, 'run_agent', side_effect=run):
            result = engine._run_handoff('worker', 'task', None, 0)
        self.assertEqual([a['image_path'] for a in result['artifacts']], [str(self.scene)])

    def test_recovered_task_does_not_make_handoff_fail(self):
        def run(name, messages, callback, **kwargs):
            callback(name, 'generate_scene_image', {'prompt': 'same'}, {'ok': False, 'error': 'temporary'})
            callback(name, 'generate_scene_image', {'prompt': 'same'}, {'ok': True, 'image_path': str(self.scene)})
            return '已完成'
        with patch.object(engine, 'run_agent', side_effect=run):
            result = engine._run_handoff('worker', 'task', None, 0)
        self.assertTrue(result['ok'])
        self.assertEqual(result['failures'], [])

    def test_retry_button_executes_only_failed_job(self):
        job = {'image_path': str(self.cutout), 'prompt': 'failed gradient scene', 'aspect_ratio': '3:4'}
        at = AppTest.from_file(str(ROOT / 'pages_test.py'))
        at.session_state['messages'] = [{'role': 'assistant', 'content': '部分完成',
            'images': [str(self.scene)], 'error': True, 'retry_tasks': [job]}]
        at.run()
        button = next(button for button in at.button if button.label == '重试未完成图片')
        with patch.object(engine, '_call_tool', return_value={'ok': True, 'image_path': str(self.scene)}) as call:
            button.click().run()
        call.assert_called_once_with('generate_scene_image', job)
        self.assertFalse(list(at.exception))
        self.assertFalse(at.session_state['messages'][-1]['error'])
        self.assertEqual(at.session_state['messages'][-1]['retry_tasks'], [])


if __name__ == '__main__':
    unittest.main()
