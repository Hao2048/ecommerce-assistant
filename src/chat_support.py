"""Small, UI-independent helpers for local image artifacts and safe user feedback."""
import io
import re
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from project_paths import ROOT
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def local_image(path):
    if not isinstance(path, str) or not path.strip():
        raise ValueError('图片路径不能为空')
    relative = Path(path)
    if not relative.is_absolute() and relative.parent == Path('.'):
        # Models sometimes shorten a supplied path to its basename. Resolve only
        # an exact, unique match inside the two artifact roots; never guess.
        matches = [candidate for parent in (ROOT / '样图', ROOT / '输出')
                   for candidate in parent.rglob('*')
                   if candidate.name == relative.name and candidate.is_file()]
        if len(matches) != 1:
            raise ValueError(f'图片路径不完整或有重名文件：{path}，请传入包含样图/或输出/的完整相对路径')
        resolved = matches[0].resolve()
    else:
        resolved = (ROOT / path).resolve()
    if not any(parent in resolved.parents for parent in (ROOT / '输出', ROOT / '样图')):
        raise ValueError('图片必须位于项目的样图或输出目录中')
    if not resolved.is_file():
        raise ValueError('图片文件不存在，可能已被移动或删除')
    return resolved


def save_upload(upfile):
    data = upfile.getvalue()
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError('图片超过20MB，请压缩后重新上传')
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > 25_000_000:
                raise ValueError('图片像素过大，请缩小到2500万像素以内')
            image = ImageOps.exif_transpose(image)
            image.load()
            image = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
            dest = ROOT / '样图' / '上传' / f'商品_{uuid4().hex}.png'
            dest.parent.mkdir(parents=True, exist_ok=True)
            image.save(dest, format='PNG')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('无法读取这张图片，请上传有效的 JPG、PNG 或 WebP 文件') from exc
    return dest.relative_to(ROOT).as_posix()


def deliverable_paths(paths):
    """Filter legacy history too: cutouts must never appear as final scenes."""
    return list(dict.fromkeys(path for path in paths if isinstance(path, str)
                              and '_抠图_' not in Path(path).name))


def image_artifacts(tool, result):
    if not isinstance(result, dict):
        return []
    paths = []
    if tool == 'generate_scene_image' and result.get('ok') and result.get('image_path'):
        paths.append(result['image_path'])
    for artifact in result.get('artifacts') or []:
        if (isinstance(artifact, dict) and artifact.get('image_path')
                and (artifact.get('tool') == 'generate_scene_image' or artifact.get('kind') == 'scene')):
            paths.append(artifact['image_path'])
    return deliverable_paths(paths)


def generation_task_key(arguments):
    import json
    return json.dumps(arguments or {}, sort_keys=True, ensure_ascii=False)


def retry_tasks_from_results(results):
    """The last outcome of each exact generation task wins (a retry can recover)."""
    pending = {}
    for tool, arguments, result in results:
        if tool != 'generate_scene_image' or not isinstance(arguments, dict):
            continue
        if not isinstance(result, dict):
            continue
        key = generation_task_key(arguments)
        if result.get('ok'):
            pending.pop(key, None)
        elif result.get('ok') is False and not result.get('deferred'):
            pending[key] = dict(arguments)
    return list(pending.values())


def clean_reply(text, is_ask=False):
    # Local artifacts are rendered by Streamlit, never as browser-relative Markdown URLs.
    text = re.sub(r'!?\[[^\]]*\]\([^)]*(?:输出|样图)/[^)]*\)', '', text)
    text = re.sub(r'`?[^`\s]*?(?:输出|样图)/[^`\s]*`?', '', text)
    if is_ask:
        text = re.sub(r'（可选：[^）]*）\s*$|（请直接回答）\s*$', '', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def error_message(exc):
    import openai
    if isinstance(exc, openai.AuthenticationError):
        return '模型服务鉴权失败，请在搭建配置中检查 API Key。'
    if isinstance(exc, openai.RateLimitError):
        return '模型服务额度不足或请求过于频繁，请稍后重试并检查服务额度。'
    if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError)):
        return '暂时无法连接模型服务，请检查网络后重试。'
    if isinstance(exc, openai.BadRequestError):
        return '模型服务拒绝了当前请求，请检查模型与工具配置，或开始新对话。'
    return '本轮处理未完成，已生成的图片会保留。你可以重试，或补充说明后继续。'
