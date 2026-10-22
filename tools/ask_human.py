# -*- coding: utf-8 -*-
"""ask_human：需要用户补充信息或做选择时，向用户提问。

什么时候用: 用户没给图片、图片里没有明确商品、没说场景类型或尺寸。
实现: 不调任何 API；"停下来等用户回答"由平台负责，这里只返回要问的内容。
"""

def run(question="", options=None):
    try:
        if not isinstance(question, str) or not question.strip():
            return {"ok": False, "error": "question 必填，且为非空字符串"}
        if options is None:
            options = []
        if not isinstance(options, list) or not all(isinstance(o, str) for o in options):
            return {"ok": False, "error": "options 必须是字符串数组"}
        return {"ok": True, "question": question.strip(), "options": options}
    except Exception as e:
        return {"ok": False, "error": f"ask_human 执行失败: {e}"}
