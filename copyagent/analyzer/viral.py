"""Viral content deconstruction using DeepSeek API."""
import json
from openai import OpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

DECONSTRUCT_PROMPT = """你是一位顶级短视频文案分析师。请严格按以下格式分析这篇口播文案。

【文案】
{text}

请输出 JSON（只输出 JSON，不要其他文字）：

{{
  "structure_type": "从以下选一个: hook_expand_climax(钩子-展开-高潮-收尾) | scqa(情境-冲突-问题-答案) | aida(注意-兴趣-欲望-行动) | golden_circle(为什么-怎么做-是什么) | pain_solution(痛点-解决方案) | story_lesson(故事-道理) | other",
  "structure_breakdown": "用1-2句话解释文案的结构逻辑",
  "hook_type": "从以下选一个: counterintuitive(反常识) | data(数据冲击) | suspense(悬念) | pain_point(痛点直击) | story(故事开头) | question(提问) | emotion(情绪共鸣) | other",
  "hook_analysis": "分析钩子为什么有效，提取可复用的句式模板",
  "emotion_curve": [
    {{"sentence_id": 1, "text": "原文前15字...", "emotion": "好奇|震惊|共鸣|焦虑|信任|激励|其他", "intensity": 3}}
  ],
  "golden_sentences": ["可直接复用的金句1", "金句2"],
  "rhythm_notes": "句长分布、转折频率、口语化程度分析",
  "rewrite_tips": "如果要仿写这篇，需要注意的3个要点",
  "target_audience": "推测目标受众",
  "keywords": ["关键词1", "关键词2"]
}}"""


def deconstruct(text: str) -> dict:
    """Analyze a viral copy and return structured analysis."""
    prompt = DECONSTRUCT_PROMPT.format(text=text[:3000])

    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=2000
    )
    raw = resp.choices[0].message.content.strip()

    json_str = raw
    if "```json" in raw:
        json_str = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        json_str = raw.split("```")[1].split("```")[0].strip()

    start = json_str.find("{")
    end = json_str.rfind("}")
    if start >= 0 and end > start:
        json_str = json_str[start:end + 1]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return {
            "structure_type": "other", "structure_breakdown": "",
            "hook_type": "other", "hook_analysis": "",
            "emotion_curve": [], "golden_sentences": [],
            "rhythm_notes": "", "rewrite_tips": "",
            "target_audience": "", "keywords": [],
            "raw_response": raw
        }


BATCH_DECONSTRUCT_PROMPT = """你是一位顶级短视频文案分析师。以下是多条文案，请逐条简要拆解。

{texts}

对每条文案输出一个 JSON 对象（用 --- 分隔各条）：
{{
  "title": "简短概括",
  "structure_type": "...",
  "hook_type": "...",
  "one_line_summary": "一句话总结这条文案的核心套路"
}}"""


def batch_deconstruct(texts: list[str]) -> list[dict]:
    """Quick batch analysis of multiple copies."""
    combined = "\n\n---\n\n".join(
        f"[文案{i+1}]\n{t[:1500]}" for i, t in enumerate(texts)
    )
    prompt = BATCH_DECONSTRUCT_PROMPT.format(texts=combined)

    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=2000
    )
    raw = resp.choices[0].message.content.strip()

    results = []
    for block in raw.split("---"):
        block = block.strip()
        if not block:
            continue
        try:
            start = block.find("{")
            end = block.rfind("}")
            if start >= 0 and end > start:
                results.append(json.loads(block[start:end + 1]))
        except json.JSONDecodeError:
            pass
    return results
