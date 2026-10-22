# -*- coding: utf-8 -*-
"""Generate one final product scene using Volcengine Seedream 5.0 Flash.

Uses Ark's reference-image API, with explicit aspect sizes and PNG output.
Transient network/server failures get at most three attempts with fresh clients.
"""
import base64
import io
import ssl
import time
from pathlib import Path
from uuid import uuid4

import httpx
from PIL import Image

import config
from chat_support import local_image
from network import http_client

ROOT = Path(__file__).resolve().parent.parent
RATIO_SIZES = {
    '1:1': '2048x2048', '3:4': '1536x2048', '4:3': '2048x1536',
    '9:16': '1440x2560', '16:9': '2560x1440',
}
ALLOW_RATIOS = tuple(RATIO_SIZES)


def _retryable(error):
    if isinstance(error, (httpx.TransportError, ssl.SSLEOFError)):
        return True
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in (408, 429) or error.response.status_code >= 500
    return any(signal in str(error).lower() for signal in (
        'timeout', 'timed out', 'eof occurred in violation of protocol', 'server disconnected'))


def _request_image(payload):
    url = config.ARK_BASE_URL.rstrip('/') + '/images/generations'
    for attempt in range(1, 4):
        try:
            # A new pool per attempt avoids reusing an interrupted TLS connection.
            with http_client(url, timeout=180) as client:
                response = client.post(url, json=payload,
                                       headers={'Authorization': 'Bearer ' + config.ARK_API_KEY})
                response.raise_for_status()
                return response.json()
        except Exception as error:
            if not _retryable(error) or attempt == 3:
                raise
            time.sleep(3 * attempt)


def run(image_path='', prompt='', aspect_ratio='1:1'):
    try:
        if not isinstance(image_path, str) or not image_path.strip():
            return {'ok': False, 'error': 'image_path 必填，请传入真实商品参考图路径'}
        if not isinstance(prompt, str) or not prompt.strip():
            return {'ok': False, 'error': 'prompt 必填，请描述具体商品拍摄场景'}
        if not isinstance(aspect_ratio, str) or aspect_ratio not in RATIO_SIZES:
            return {'ok': False, 'error': 'aspect_ratio 只支持 ' + ' / '.join(ALLOW_RATIOS)}
        if not config.ARK_API_KEY:
            return {'ok': False, 'error': '请在 config.py 配置 ARK_API_KEY'}
        src = local_image(image_path)
        buffer = io.BytesIO()
        with Image.open(src) as product:
            product.save(buffer, format='PNG')
        reference = buffer.getvalue()
        if len(reference) > 30 * 1024 * 1024:
            return {'ok': False, 'error': '参考图超过30MB，请压缩后重新上传'}
        payload = {
            'model': config.IMAGE_MODEL,
            'prompt': prompt.strip(),
            'image': 'data:image/png;base64,' + base64.b64encode(reference).decode('ascii'),
            'size': RATIO_SIZES[aspect_ratio],
            'response_format': 'b64_json',
            'output_format': 'png',
            'watermark': False,
        }
        # Flash generates one image per request; group-generation parameters are unsupported.
        data = _request_image(payload)
        items = data.get('data') or []
        image_data = next((item.get('b64_json') for item in items
                           if isinstance(item, dict) and item.get('b64_json')), None)
        if not image_data:
            error = data.get('error') or next((item.get('error') for item in items
                                              if isinstance(item, dict) and item.get('error')), {})
            detail = error.get('message', '') if isinstance(error, dict) else str(error)
            return {'ok': False, 'error': 'Seedream 没有返回最终图片' + (f'：{detail[:250]}' if detail else '')}
        raw = base64.b64decode(image_data, validate=True)
        out_dir = ROOT / '输出'
        out_dir.mkdir(exist_ok=True)
        base = src.stem.split('_抠图_')[0]
        out_name = f'{base}_场景_{uuid4().hex}.png'
        with Image.open(io.BytesIO(raw)) as generated:
            generated.load()
            size = f'{generated.width}x{generated.height}'
            generated.save(out_dir / out_name, format='PNG')
        return {'ok': True, 'image_path': f'输出/{out_name}', 'kind': 'scene',
                'model': config.IMAGE_MODEL, 'size': size}
    except httpx.HTTPStatusError as error:
        code = error.response.status_code
        hints = {401: '方舟 API Key 鉴权失败', 403: '当前账号无模型权限，请检查模型开通状态',
                 404: '未找到模型，请检查 IMAGE_MODEL', 429: '模型服务限流或额度不足'}
        try:
            detail = error.response.json().get('error', {})
            detail = detail.get('message', '') if isinstance(detail, dict) else ''
        except (ValueError, AttributeError):
            detail = ''
        return {'ok': False, 'error': f'Seedream HTTP {code}: {hints.get(code, "模型请求失败")}' +
                (f'；{detail[:250]}' if detail else '')}
    except Exception as error:
        return {'ok': False, 'error': f'Seedream 生图失败: {error}'}
