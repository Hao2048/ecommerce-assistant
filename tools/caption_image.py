# -*- coding: utf-8 -*-
"""caption_image：看图识别商品。

什么时候用: 拿到用户图片后第一步调用。判断有没有明确的商品主体，
描述品类、外观、颜色、材质、用途，忽略文字和背景。
服务: DeepSeek 看图模型（OpenAI 兼容格式），模型用 config.CAPTION_MODEL
"""

import base64
import json
import mimetypes

from openai import OpenAI

from settings import config
from chat_support import local_image
from network import http_client


PROMPT = (
    "看这张图，判断里面有没有明确的商品主体（忽略文字和水印，忽略背景）。"
    "如果有商品，描述该商品的品类、外观、颜色、材质、用途；"
    "如果没有明确商品，说明原因。"
    '只返回 JSON，格式：{"has_product": true或false, "product_info": "商品描述或没有商品的原因"}'
)


def run(image_path=""):
    try:
        if not isinstance(image_path, str) or not image_path.strip():
            return {"ok": False, "error": "image_path 必填，如 样图/产品.jpg"}
        src = local_image(image_path)
        if not config.DEEPSEEK_API_KEY:
            return {"ok": False, "error": "请在 config/config.py 配置 DEEPSEEK_API_KEY"}

        image_b64 = base64.b64encode(src.read_bytes()).decode("utf-8")
        mime = mimetypes.guess_type(str(src))[0] or "image/jpeg"

        client = OpenAI(api_key=config.DEEPSEEK_API_KEY, base_url=config.DEEPSEEK_BASE_URL,
                        timeout=60, max_retries=2,
                        http_client=http_client(config.DEEPSEEK_BASE_URL))
        resp = client.chat.completions.create(
            model=config.CAPTION_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                    {"type": "text", "text": PROMPT},
                ],
            }],
            response_format={"type": "json_object"},
            extra_body={"thinking": {"type": "disabled"}},
        )

        text = (resp.choices[0].message.content or "").strip()
        if text.startswith("```"):  # 兜底剥掉可能出现的 markdown 代码围栏
            text = text.strip("`").lstrip("json").strip()
        data = json.loads(text)
        if not isinstance(data, dict) or not isinstance(data.get("has_product"), bool):
            return {"ok": False, "error": "识别模型未返回合法的 has_product 布尔值，请重试"}
        return {
            "ok": True,
            "has_product": data["has_product"],
            "product_info": str(data.get("product_info", "")),
        }
    except Exception as e:
        return {"ok": False, "error": f"caption_image 执行失败: {e}"}
    finally:
        if "client" in locals():
            client.close()
