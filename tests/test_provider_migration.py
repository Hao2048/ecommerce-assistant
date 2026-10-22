"""Provider contracts: offline, credential-free, no external requests."""
import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace as NS

import httpx
from PIL import Image

import config
import engine
from tools import generate_scene_image as generator

ROOT = Path(__file__).resolve().parents[1]


class MigrationTests(unittest.TestCase):
    def setUp(self):
        (ROOT / '输出').mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / '输出')
        self.addCleanup(self.tmp.cleanup)
        self.src = Path(self.tmp.name) / '商品_抠图_reference.png'
        Image.new('RGBA', (32, 32), (255, 0, 0, 128)).save(self.src)
        buf = io.BytesIO()
        Image.new('RGB', (32, 32), 'blue').save(buf, 'JPEG')
        self.encoded = base64.b64encode(buf.getvalue()).decode()

    def test_all_agents_use_requested_deepseek_model(self):
        for path in (ROOT / 'agents').glob('*.json'):
            self.assertEqual(json.loads(path.read_text())['modelName'], 'deepseek-flash', path.name)
        self.assertEqual(engine._client.base_url.host, 'api.deepseek.com')
        self.assertEqual(config.CAPTION_MODEL, 'deepseek-flash')

    def test_agent_explicitly_disables_default_thinking(self):
        with patch.object(engine._client.chat.completions, 'create', return_value=NS(choices=[])) as create:
            engine._chat_with_retry('deepseek-flash', [{'role': 'user', 'content': 'test'}], [])
        self.assertEqual(create.call_args.kwargs.get('extra_body'), {'thinking': {'type': 'disabled'}})

    def test_seedream_sends_reference_and_exact_aspect_size(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={'data': [{'b64_json': self.encoded}]})
        with patch.object(generator, 'http_client', side_effect=lambda *a, **k:
                          httpx.Client(transport=httpx.MockTransport(handler))), \
                patch.object(config, 'ARK_API_KEY', 'test-key'):
            result = generator.run(str(self.src), '参考商品拍摄场景图', '3:4')
        self.assertTrue(result['ok'], result)
        dest = ROOT / result['image_path']
        self.addCleanup(dest.unlink)
        self.assertEqual(result['kind'], 'scene')
        request = requests[0]
        self.assertEqual(str(request.url), 'https://ark.cn-beijing.volces.com/api/v3/images/generations')
        body = json.loads(request.content)
        self.assertEqual(body['model'], 'doubao-seedream-5-0-flash-260915')
        self.assertEqual(body['size'], '1536x2048')
        self.assertTrue(body['image'].startswith('data:image/png;base64,'))
        self.assertEqual(body['response_format'], 'b64_json')
        self.assertNotIn('sequential_image_generation', body, 'Flash does not support group-generation parameters')
        with Image.open(dest) as image:
            self.assertEqual(image.format, 'PNG')

    def test_seedream_retries_503_with_fresh_client(self):
        seen = []
        def handler(request):
            seen.append(request)
            if len(seen) == 1:
                return httpx.Response(503, json={'error': {'message': 'temporarily unavailable'}})
            return httpx.Response(200, json={'data': [{'b64_json': self.encoded}]})
        with patch.object(generator, 'http_client', side_effect=lambda *a, **k:
                          httpx.Client(transport=httpx.MockTransport(handler))) as factory, \
                patch.object(generator.time, 'sleep'), \
                patch.object(config, 'ARK_API_KEY', 'test-key'):
            result = generator.run(str(self.src), 'a home scene')
        self.assertTrue(result['ok'])
        self.addCleanup((ROOT / result['image_path']).unlink)
        self.assertEqual(factory.call_count, 2)

    def test_seedream_does_not_retry_invalid_credentials(self):
        with patch.object(generator, 'http_client', side_effect=lambda *a, **k:
                          httpx.Client(transport=httpx.MockTransport(lambda request:
                              httpx.Response(401, json={'error': {'message': 'invalid credential'}})))) as factory, \
                patch.object(config, 'ARK_API_KEY', 'test-key'):
            result = generator.run(str(self.src), 'a home scene')
        self.assertFalse(result['ok'])
        self.assertNotIn('image_path', result)
        self.assertEqual(factory.call_count, 1)

    def test_seedream_empty_result_is_failure(self):
        with patch.object(generator, '_request_image', return_value={'data': []}), \
                patch.object(config, 'ARK_API_KEY', 'test-key'):
            result = generator.run(str(self.src), 'a home scene')
        self.assertFalse(result['ok'])
        self.assertNotIn('image_path', result)


if __name__ == '__main__':
    unittest.main()
