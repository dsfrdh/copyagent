"""Hotspot analysis, topic generation, and copy generation."""
from __future__ import annotations

import json
from typing import Any

from generator.copywriter import _call_llm, _resolve_length_words, CONTENT_FORMAT_INSTRUCTION
from hotspot.providers import CompositeSearchProvider, SearchResult


PLATFORM_QUERY_HINTS = {
    "抖音": ["抖音 爆款", "短视频 热门", "直播带货", "种草"],
    "小红书": ["小红书 种草", "小红书 热门笔记", "真实测评"],
    "视频号": ["视频号 爆款", "私域 引流", "中视频"],
    "快手": ["快手 爆款", "直播带货", "老铁 推荐"],
    "全网": ["爆款", "热门话题", "种草", "测评"],
}


def build_hotspot_queries(product: str, platform: str = "抖音", days: int = 30,
                          audience: str = "", selling_points: str = "") -> list[str]:
    base = product.strip()
    platform_hints = PLATFORM_QUERY_HINTS.get(platform, PLATFORM_QUERY_HINTS["全网"])
    scope = f"近{days}天"
    extras = " ".join(x for x in [audience.strip(), selling_points.strip()] if x)
    queries = [
        f"{base} {scope} 热门话题",
        f"{base} {platform_hints[0]}",
        f"{base} 用户痛点",
        f"{base} 选题 文案",
        f"{base} 测评 推荐",
    ]
    for hint in platform_hints[1:]:
        queries.append(f"{base} {hint}")
    if extras:
        queries.append(f"{base} {extras} 热门")
    return list(dict.fromkeys(queries))[:8]


HOTSPOT_ANALYSIS_PROMPT = """你是一位短视频内容选题策划和电商文案策略师。请根据产品信息和搜索结果，提炼近期可用于创作的热点方向。

【产品】
{product}

【平台】
{platform}

【用户补充】
目标人群：{audience}
产品卖点：{selling_points}
视频目的：{purpose}
热点时间范围：近 {days} 天

【搜索结果】
{search_results}

请只输出 JSON，不要输出 Markdown：
{{
  "data_status": "enough 或 insufficient",
  "summary": "一句话总结当前热点机会",
  "hot_topics": ["热门话题1", "热门话题2"],
  "pain_points": ["痛点1", "痛点2"],
  "scenes": ["场景1", "场景2"],
  "selling_angles": ["卖点角度1", "卖点角度2"],
  "content_formats": ["痛点吐槽", "测评对比"],
  "keywords": ["关键词1", "关键词2"],
  "risk_notes": ["风险提醒1"]
}}

要求：
- 如果搜索结果为空或很弱，data_status 填 insufficient，并基于品类常识补足可用方向。
- 不要复制搜索结果中的完整文案，只提炼话题、痛点和表达结构。
- 结果要具体，可直接用于短视频选题。"""


TOPIC_GENERATION_PROMPT = """你是一位短视频选题策划。请根据热点分析，为产品生成 {topic_count} 个可拍摄选题。

【产品】
{product}

【平台】
{platform}

【视频目的】
{purpose}

【目标人群】
{audience}

【产品卖点】
{selling_points}

【热点分析】
{analysis_json}

请只输出 JSON，不要输出 Markdown：
{{
  "topics": [
    {{
      "title": "选题标题",
      "pain_point": "核心痛点",
      "target_audience": "目标人群",
      "angle": "内容角度",
      "opening": "一句可直接用的痛点开场",
      "shooting_tips": "拍摄建议",
      "hotspot_basis": "热点依据"
    }}
  ]
}}

要求：
- 必须生成 {topic_count} 个。
- 每个选题都要和产品强相关，并有明确痛点。
- 选题之间要覆盖不同场景，不要重复换皮。
- 标题适合短视频，但不要夸大或虚假承诺。
- opening 必须是痛点开头，适合前 3 秒口播。"""


HOTSPOT_COPY_PROMPT = """你是一位专业短视频口播文案写手。请根据用户选择的热点选题生成一篇完整口播文案。

【产品】
{product}

【平台】
{platform}

【视频目的】
{purpose}

【长度】
{length}，约 {max_words} 字

【风格】
{style}
{content_format_instruction}

【目标人群】
{audience}

【产品卖点】
{selling_points}

【选题】
{topic_json}

【热点分析】
{analysis_json}

请按以下结构输出：
1. 「发布标题」
2. 「口播正文」
3. 「分镜建议」
4. 「话题标签」
5. 「生成依据」

写作要求：
- 口播正文第一句必须是痛点开头，不能一上来硬推产品。
- 先痛点，再场景放大，再自然带出产品。
- 至少写出 2 个和产品相关的卖点，卖点必须放在真实场景里表达。
- 语言要像真人口播，不要像说明书。
- 不要承诺绝对效果，不要写医疗功效或夸大宣传。"""


def discover_hotspots(product: str, platform: str = "抖音", days: int = 30,
                      audience: str = "", selling_points: str = "",
                      purpose: str = "种草", provider=None) -> dict[str, Any]:
    queries = build_hotspot_queries(product, platform, days, audience, selling_points)
    provider = provider or CompositeSearchProvider()
    results = provider.search(queries, limit_per_query=4)
    analysis = analyze_hotspots(
        product=product,
        platform=platform,
        days=days,
        audience=audience,
        selling_points=selling_points,
        purpose=purpose,
        results=results,
    )
    return {
        "queries": queries,
        "results": [r.to_dict() for r in results],
        "analysis": analysis,
    }


def analyze_hotspots(product: str, platform: str, days: int, audience: str,
                     selling_points: str, purpose: str,
                     results: list[SearchResult] | list[dict]) -> dict[str, Any]:
    search_text = _format_search_results(results)
    prompt = HOTSPOT_ANALYSIS_PROMPT.format(
        product=product,
        platform=platform,
        audience=audience or "未指定",
        selling_points=selling_points or "未指定",
        purpose=purpose or "种草",
        days=days,
        search_results=search_text or "（未获取到有效搜索结果）",
    )
    raw = _call_llm(prompt, temperature=0.35, max_tokens=1200)
    parsed = _parse_json(raw)
    if not parsed:
        parsed = {
            "data_status": "insufficient",
            "summary": "当前热点数据不足，已基于品类常见痛点生成。",
            "hot_topics": [],
            "pain_points": [],
            "scenes": [],
            "selling_angles": [],
            "content_formats": [],
            "keywords": [],
            "risk_notes": [],
            "raw": raw,
        }
    return parsed


def generate_hotspot_topics(product: str, hotspot_analysis: dict[str, Any],
                            topic_count: int = 10, platform: str = "抖音",
                            audience: str = "", selling_points: str = "",
                            purpose: str = "种草") -> list[dict[str, str]]:
    prompt = TOPIC_GENERATION_PROMPT.format(
        product=product,
        platform=platform,
        purpose=purpose,
        audience=audience or "未指定",
        selling_points=selling_points or "未指定",
        topic_count=topic_count,
        analysis_json=json.dumps(hotspot_analysis, ensure_ascii=False, indent=2),
    )
    raw = _call_llm(prompt, temperature=0.75, max_tokens=2800)
    parsed = _parse_json(raw)
    topics = parsed.get("topics", []) if isinstance(parsed, dict) else []
    normalized = []
    for topic in topics:
        if not isinstance(topic, dict):
            continue
        normalized.append({
            "title": str(topic.get("title", "")).strip(),
            "pain_point": str(topic.get("pain_point", "")).strip(),
            "target_audience": str(topic.get("target_audience", "")).strip(),
            "angle": str(topic.get("angle", "")).strip(),
            "opening": str(topic.get("opening", "")).strip(),
            "shooting_tips": str(topic.get("shooting_tips", "")).strip(),
            "hotspot_basis": str(topic.get("hotspot_basis", "")).strip(),
        })
    return [t for t in normalized if t["title"]][:topic_count]


def generate_hotspot_copy(product: str, topic: dict[str, Any],
                          hotspot_analysis: dict[str, Any],
                          platform: str = "抖音", purpose: str = "种草",
                          audience: str = "", selling_points: str = "",
                          length: str = "60秒", style: str = "口语化",
                          content_format: str = "") -> str:
    max_words = _resolve_length_words(length)
    format_instruction = ""
    if content_format:
        fmt = CONTENT_FORMAT_INSTRUCTION.get(content_format, "")
        if fmt:
            format_instruction = f"\n【内容形式】{content_format}\n要求：{fmt}"
    prompt = HOTSPOT_COPY_PROMPT.format(
        product=product,
        platform=platform,
        purpose=purpose,
        length=length,
        max_words=max_words,
        style=style,
        audience=audience or "未指定",
        selling_points=selling_points or "未指定",
        topic_json=json.dumps(topic, ensure_ascii=False, indent=2),
        analysis_json=json.dumps(hotspot_analysis, ensure_ascii=False, indent=2),
        content_format_instruction=format_instruction,
    )
    return _call_llm(prompt, temperature=0.75, max_tokens=1800)


def _format_search_results(results: list[SearchResult] | list[dict]) -> str:
    lines = []
    for i, item in enumerate(results[:30], 1):
        if isinstance(item, SearchResult):
            data = item.to_dict()
        else:
            data = item
        lines.append(
            f"{i}. 标题：{data.get('title', '')}\n"
            f"   摘要：{data.get('snippet', '')}\n"
            f"   来源：{data.get('source', '')}\n"
            f"   时间：{data.get('published_at', '')}\n"
            f"   链接：{data.get('url', '')}\n"
            f"   搜索词：{data.get('query', '')}"
        )
    return "\n".join(lines)


def _parse_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}

