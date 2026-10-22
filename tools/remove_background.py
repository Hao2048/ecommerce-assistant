# -*- coding: utf-8 -*-
"""remove_background：把商品图的背景去掉，只留下商品。

什么时候用: 识别出商品之后、生成场景图之前。
服务: Pixian 抠图 API（https://pixian.ai/api）
  POST https://api.pixian.ai/api/v2/remove-background
  鉴权: HTTP Basic Auth，用户名 config.PIXIAN_API_ID，密码 config.PIXIAN_API_SECRET
  请求: multipart 表单，字段 image 放图片文件
  返回: 成功时响应体就是 PNG 图片；失败时是 JSON 错误信息
"""
import json
from uuid import uuid4
import io
from PIL import Image

import requests

from settings import config
from chat_support import local_image

from project_paths import ROOT
API_URL = "https://api.pixian.ai/api/v2/remove-background"


def run(image_path=""):
    try:
        if not isinstance(image_path, str) or not image_path.strip():
            return {"ok": False, "error": "image_path 必填，如 样图/产品.jpg"}
        src = local_image(image_path)
        if not config.PIXIAN_API_ID or not config.PIXIAN_API_SECRET:
            return {"ok": False, "error": "未配置 Pixian 凭证，请在 config/config.py 里填写 PIXIAN_API_ID 和 PIXIAN_API_SECRET"}

        with open(src, "rb") as f:
            resp = requests.post(
                API_URL,
                files={"image": (src.name, f)},
                auth=(config.PIXIAN_API_ID, config.PIXIAN_API_SECRET),
                timeout=120,
            )

        if resp.status_code != 200 or "image" not in resp.headers.get("Content-Type", ""):
            try:
                data = resp.json()
                msg = data.get("error") or data.get("message") or json.dumps(data, ensure_ascii=False)[:200]
            except ValueError:
                msg = resp.text[:200]
            return {"ok": False, "error": f"Pixian 抠图失败(HTTP {resp.status_code}): {msg}"}

        out_dir = ROOT / "输出"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = uuid4().hex
        out_name = f"{src.stem}_抠图_{stamp}.png"
        with Image.open(io.BytesIO(resp.content)) as image:
            image.save(out_dir / out_name, format="PNG")
        return {"ok": True, "image_path": f"输出/{out_name}"}
    except Exception as e:
        return {"ok": False, "error": f"remove_background 执行失败: {e}"}
