"""Offline regressions: no credentials or paid model calls are used."""
import json
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import engine

ROOT = Path(__file__).resolve().parents[1]


def response(calls=(), content=None):
    return NS(choices=[NS(finish_reason='tool_calls' if calls else 'stop', message=NS(
        content=content, tool_calls=[NS(id=f'call_{i}', function=NS(name=name, arguments=args))
                                   for i, (name, args) in enumerate(calls)]))])


class EngineRegressionTests(unittest.TestCase):
    def setUp(self):
        key = patch.object(engine.config, 'DEEPSEEK_API_KEY', 'offline-test-key')
        key.start()
        self.addCleanup(key.stop)

    def test_callback_failure_does_not_poison_conversation(self):
        messages = [{'role': 'user', 'content': '图片用1:1'}]
        def broken_callback(*args):
            raise RuntimeError('render failure')
        with patch.object(engine, '_chat_with_retry', side_effect=[
            response([('ask_human', '{"question":"确认？"}')])]):
            try:
                engine.run_agent('product_scene_design_agent', messages, broken_callback)
            except RuntimeError:
                pass
        call_ids = [tc['id'] for m in messages for tc in m.get('tool_calls', [])]
        result_ids = [m['tool_call_id'] for m in messages if m['role'] == 'tool']
        self.assertEqual(call_ids, result_ids, '渲染异常不能留下没有结果的工具调用，否则下轮API会400')

    def test_invalid_question_is_repaired_instead_of_stopping(self):
        messages = [{'role': 'user', 'content': '你好'}]
        with patch.object(engine, '_chat_with_retry', side_effect=[
            response([('ask_human', '{"options":"bad"}')]), response(content='请上传商品图')]) as chat:
            reply = engine.run_agent('product_scene_design_agent', messages)
        self.assertEqual(reply, '请上传商品图')
        self.assertEqual(chat.call_count, 2)

    def test_unmounted_tool_cannot_execute(self):
        messages = [{'role': 'user', 'content': '开始'}]
        with patch.object(engine, '_chat_with_retry', side_effect=[
            response([('generate_scene_image', '{"prompt":"test"}')]), response(content='结束')]), \
                patch.object(engine, '_call_tool', return_value={'ok': True}) as tool:
            engine.run_agent('product_scene_design_agent', messages)
        tool.assert_not_called()
        result = next(json.loads(m['content']) for m in messages if m['role'] == 'tool')
        self.assertFalse(result['ok'])

    def test_interruption_completes_all_tool_call_ids(self):
        class UserStopped(BaseException):
            pass
        messages = [{'role': 'user', 'content': '识别商品'}]
        with patch.object(engine, '_chat_with_retry', return_value=response([
                ('caption_image', '{}'), ('remove_background', '{}')])), \
                patch.object(engine, '_call_tool', side_effect=UserStopped):
            with self.assertRaises(UserStopped):
                engine.run_agent('product_scene_design_agent', messages)
        self.assertEqual([m['tool_call_id'] for m in messages if m['role'] == 'tool'],
                         ['call_0', 'call_1'])

    def test_asking_user_defers_other_tool_calls(self):
        messages = [{'role': 'user', 'content': '确认比例'}]
        with patch.object(engine, '_chat_with_retry', return_value=response([
            ('ask_human', '{"question":"选哪个比例？"}'), ('remove_background', '{}')])):
            engine.run_agent('product_scene_design_agent', messages)
        results = [json.loads(m['content']) for m in messages if m['role'] == 'tool']
        self.assertTrue(results[0]['ok'])
        self.assertIn('尚未执行', results[1]['error'])

    def test_prompts_only_refer_to_available_runtime(self):
        obsolete = ['caption_image_tool_gpt_4o', 'image_editing_tool_meitu_image_segmentation',
                    'image_to_image_tool_gemini_2_5_flash_image_preview',
                    'image_to_image_tool_gpt_image_1_edit', 'parallel_tool_invoker', 'agent_end_tool']
        for path in (ROOT / 'prompts').glob('*.md'):
            for name in obsolete:
                self.assertNotIn(name, path.read_text(), f'{path.name}引用了未注册工具 {name}')


class UIRegressionTests(unittest.TestCase):
    def test_same_artifact_can_render_in_two_turns(self):
        from streamlit.testing.v1 import AppTest
        import tempfile
        from PIL import Image
        (ROOT / '输出').mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix='.png', dir=ROOT / '输出', delete=False) as handle:
            image = Path(handle.name)
        Image.new('RGB', (8, 8)).save(image)
        self.addCleanup(image.unlink)
        at = AppTest.from_file(str(ROOT / 'pages_test.py'))
        at.session_state['messages'] = [dict(role='assistant', content='已生成', images=[str(image)]) for _ in range(2)]
        at.run()
        self.assertFalse(list(at.exception), '同一图片在历史消息重复展示不能导致下载按钮key冲突')




class ImagePipelineTests(unittest.TestCase):
    def setUp(self):
        import io
        import tempfile
        key = patch.object(engine.config, 'DEEPSEEK_API_KEY', 'offline-test-key')
        key.start()
        self.addCleanup(key.stop)
        from PIL import Image
        (ROOT / '输出').mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / '输出')
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / 'reference.png'
        Image.new('RGB', (8, 8), 'red').save(self.source)
        self.buffer = io.BytesIO()
        Image.new('RGB', (16, 16), 'blue').save(self.buffer, format='JPEG')

    def test_generation_normalizes_real_image_bytes(self):
        from tools import generate_scene_image as generator
        from PIL import Image
        import base64
        with patch.object(generator, '_request_image', return_value={'data': [
                {'b64_json': base64.b64encode(self.buffer.getvalue()).decode()}]}), \
                patch.object(generator.config, 'ARK_API_KEY', 'offline-test-key'):
            result = generator.run(str(self.source), 'a studio product scene')
        self.assertTrue(result['ok'], result)
        dest = ROOT / result['image_path']
        self.addCleanup(dest.unlink)
        with Image.open(dest) as image:
            self.assertEqual(image.format, 'PNG')
        from chat_support import image_artifacts
        self.assertEqual(image_artifacts('handoff_to_psd_generate_agent', {
            'ok': False, 'artifacts': [{'image_path': result['image_path'], 'tool': 'generate_scene_image'}]
        }), [result['image_path']])

    def test_unique_basename_resolves_to_real_reference(self):
        from chat_support import local_image
        self.assertEqual(local_image(self.source.name), self.source.resolve())

    def test_ambiguous_basename_is_rejected(self):
        from chat_support import local_image
        duplicate_dir = self.source.parent / 'duplicate'
        duplicate_dir.mkdir()
        (duplicate_dir / self.source.name).write_bytes(self.source.read_bytes())
        with self.assertRaises(ValueError):
            local_image(self.source.name)

    def test_upload_rejects_disguised_non_image(self):
        from chat_support import save_upload
        with self.assertRaises(ValueError):
            save_upload(NS(name='fake.png', getvalue=lambda: b'not an image'))

    def test_partial_handoff_preserves_artifacts_on_exception(self):
        def fake_run(name, messages, callback, **kwargs):
            callback(name, 'generate_scene_image', {}, {'ok': True, 'image_path': str(self.source)})
            raise RuntimeError('later network failure')
        with patch.object(engine, 'run_agent', side_effect=fake_run):
            result = engine._run_handoff('psd_generate_agent', 'generate', None, 0)
        self.assertFalse(result['ok'])
        self.assertEqual(result['artifacts'][0]['image_path'], str(self.source))

    def test_ui_renders_child_image_and_preserves_it_after_rerun(self):
        from streamlit.testing.v1 import AppTest
        def fake_run(name, messages, callback):
            callback('psd_generate_agent', 'generate_scene_image', {},
                     {'ok': True, 'image_path': str(self.source)})
            return '已生成1张场景图'
        at = AppTest.from_file(str(ROOT / 'pages_test.py'))
        at.session_state['messages'] = [{'role': 'user', 'content': '生成1张'}]
        at.session_state['agent_messages'] = [{'role': 'user', 'content': '生成1张'}]
        at.session_state['need_reply'] = True
        with patch.object(engine, 'run_agent', side_effect=fake_run):
            at.run()
        self.assertFalse(list(at.exception))
        self.assertEqual(at.session_state['messages'][-1]['images'], [str(self.source)])
        at.run()
        self.assertFalse(list(at.exception))
        self.assertEqual(len(at.get('download_button')), 1)


if __name__ == '__main__':
    unittest.main()
