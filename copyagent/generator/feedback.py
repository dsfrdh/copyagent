"""Feedback analysis: turn user edits into reusable preference rules."""
import json

from generator.copywriter import _call_llm


FEEDBACK_ANALYSIS_PROMPT = """你是一个短视频文案复盘助手。请对比 AI 原稿和用户最终修改稿，分析用户修改偏好。

【文案信息】
产品：{product}
生成模式：{mode}
视频类型/用途：{video_type}
长度：{length}
风格：{style}

【用户选择的原因标签】
{reason_tags}

【用户补充说明】
{note}

【AI 原稿】
{original_content}

【用户最终修改稿】
{final_content}

请只输出 JSON，不要输出 Markdown，不要解释。格式如下：
{{
  "summary": "一句话总结用户主要改了什么",
  "changed_aspects": ["语气", "结构", "卖点表达"],
  "avoid_rules": ["以后要避免的规则1", "以后要避免的规则2"],
  "prefer_rules": ["以后优先采用的规则1", "以后优先采用的规则2"],
  "applicable_conditions": {{
    "product": "{product}",
    "video_type": "{video_type}",
    "people_count": "",
    "length_range": "{length}"
  }}
}}

要求：
- 规则要短、具体、可执行。
- 不要写空泛规则，例如“写得更好”。
- 如果用户只是微调措辞，也要总结成口吻偏好。
- 如果用户删掉某种表达，要放入 avoid_rules。
- 如果用户新增某种表达方式、结构、角色台词或场景，要放入 prefer_rules。
"""


def _extract_json(raw: str) -> dict:
    text = raw.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def analyze_revision(original_content: str, final_content: str, metadata: dict | None = None,
                     reason_tags: list[str] | None = None, note: str = "") -> dict:
    """Analyze user edits and return structured preference rules."""
    metadata = metadata or {}
    reason_tags = reason_tags or []
    prompt = FEEDBACK_ANALYSIS_PROMPT.format(
        product=metadata.get("product", ""),
        mode=metadata.get("mode", ""),
        video_type=metadata.get("video_type") or metadata.get("purpose", ""),
        length=metadata.get("length", ""),
        style=metadata.get("style", ""),
        reason_tags="、".join(reason_tags) if reason_tags else "无",
        note=note or "无",
        original_content=original_content,
        final_content=final_content,
    )
    raw = _call_llm(prompt, temperature=0.3, max_tokens=1000)
    try:
        return _extract_json(raw)
    except Exception:
        return {
            "summary": "AI 已完成分析，但返回格式无法自动解析。",
            "changed_aspects": [],
            "avoid_rules": [],
            "prefer_rules": [],
            "raw": raw,
        }
