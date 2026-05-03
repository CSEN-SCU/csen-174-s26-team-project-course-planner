import json
import os
import re

from google import genai
from google.genai import types

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client()
    return _client

RESULT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "completed": {"type": "ARRAY", "items": {"type": "STRING"}},
        "missing": {"type": "ARRAY", "items": {"type": "STRING"}},
        "missing_details": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "course": {"type": "STRING"},
                    "category": {"type": "STRING"},
                    "units": {"type": "INTEGER"},
                },
                "required": ["course", "category", "units"],
            },
        },
    },
    "required": ["completed", "missing", "missing_details"],
}

# 新账号无法再用 gemini-2.0-flash，默认改为当前 Gemini API 可用的 Flash 模型。
DEFAULT_MODEL = "gemini-2.5-flash"


def _parse_json_from_response(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        text = m.group(1).strip()
    return json.loads(text)


def run_requirement_agent(pdf_bytes: bytes, completed_courses: list[str]) -> dict:
    completed_str = json.dumps(completed_courses, ensure_ascii=False)
    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)

    prompt = f"""
你是一个大学选课顾问。

学生已修课程：{completed_str}

请分析这份 major requirement PDF，找出：
1. 学生已完成哪些必修课（与 PDF 中的要求对照，仅列出在要求中出现且学生已修的）
2. 学生还缺哪些必修课

按约定的 JSON 结构输出（已通过 response schema 约束字段）。
"""

    response = _get_client().models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            prompt,
        ],
        config=types.GenerateContentConfig(
            max_output_tokens=8192,
            response_mime_type="application/json",
            response_schema=RESULT_SCHEMA,
        ),
    )

    text = (response.text or "").strip()
    if not text:
        raise ValueError("模型未返回文本内容")
    return _parse_json_from_response(text)
