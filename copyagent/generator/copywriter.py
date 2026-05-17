"""Copy generation with RAG: retrieve → prompt → generate via DeepSeek API."""
import json
from openai import OpenAI
import config
from knowledge.retriever import query_chunks
from utils.db import build_preference_memory_text

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.DEEPSEEK_API_KEY, base_url=config.DEEPSEEK_BASE_URL)
    return _client


def reset_client():
    global _client
    _client = None

# ── Content Format Instructions ──

CONTENT_FORMAT_INSTRUCTION = {
    "单人口播": "文案为单人面对镜头口播形式，语气像在和观众对话，句式简短自然，多用'你''我'拉近距离。不要在文案中设计角色或情景切换。",
    "剧情演绎": "文案需要设计1-2个角色的简短对话或情景剧，有人物互动和情节推进。可以包含角色台词标记，有起承转合的小故事线。",
    "测评对比": "文案包含产品对比或使用前后对比，有客观数据和主观体验，结构清晰。对比要具体（价格/效果/体验），有结论推荐。",
    "Vlog分享": "文案以第一人称生活分享形式，穿插日常场景描述，口吻轻松自然像记录生活。用'今天来...''最近发现...'等日常开场。",
    "干货讲解": "文案为知识科普+产品植入形式，先讲干货建立专业感，再自然带出产品。用'你知道吗''很多人不知道'等句式。",
    "对话访谈": "文案为两人对话形式，一问一答推进内容。提问者代表用户疑惑，回答者代表专家/使用者解答。角色自然不做作。",
    "开箱体验": "文案为第一人称开箱/体验记录，从收到产品到使用的完整过程。强调真实感受和细节发现。",
    "场景种草": "文案聚焦一个具体使用场景，先渲染场景需求，再展示产品如何解决。强调'用了之后'的变化。",
}

# ── Prompt Templates ──

FREE_PROMPT = """你是一位专业的短视频口播文案写手。请根据以下课程知识，撰写一条{length}的短视频口播文案。

【课程参考资料】
{knowledge}

{preference_memory}

【创作要求】
- 目的：{purpose}
- 风格：{style}
- 字数：约{max_words}字
- 必须是口播友好的语言，念出来自然流畅
- 开头必须有强钩子，3秒内抓住注意力
{content_format_instruction}

【输出格式】
1. 先写「钩子设计」：一句话说明用了什么钩子
2. 再写「文案正文」
3. 最后写「使用的知识点」：列出引用了课程中的哪些观点"""

IMITATE_PROMPT = """你要写文案的产品是：{product}
该产品的卖点：{selling_points}
该产品的用户痛点：{pain_points}

请模仿下面这条爆款文案的【结构和节奏】，为「{product}」撰写一条新文案。

【爆款原文（供参考结构和风格）】
{original_text}

【爆款结构拆解】
{reference_structure}

【课程参考资料】
{knowledge}

{preference_memory}

写作要求：
- 产品是「{product}」，内容必须围绕这个产品展开
- 保留爆款原文的：钩子类型、段落推进节奏、句式长短结构
- 替换内容为「{product}」的相关信息和卖点
- 不要直接抄袭爆款原文的句子
- 用课程方法论来组织说服逻辑
- 字数：约{max_words}字，{length}长度
- 风格：{style}
{content_format_instruction}

【输出格式】
1. 「结构对照」：说明你如何复用了原爆款的结构
2. 「文案正文」
3. 「使用的知识点」"""

REWRITE_PROMPT = """你是一位专业的短视频口播文案写手。请用课程方法论优化下面这段文案草稿。

【原文案】
{draft}

【课程参考资料】
{knowledge}

{preference_memory}

【优化方向】
- 强化开头钩子
- 优化情绪节奏
- 融入课程中的金句和观点
- 保持{length}的长度
- 风格：{style}
{content_format_instruction}

【输出格式】
1. 「优化说明」：列出了哪些改进
2. 「优化后文案」
3. 「使用的知识点」"""

COMBINE_PROMPT = """你是一位专业的短视频口播文案写手。请组合多条爆款的特点来创作。

【钩子参考】用这条爆款的钩子方式：
{hook_reference}

【展开逻辑参考】用这条爆款的展开方式：
{body_reference}

【收尾参考】用这条爆款的收尾方式：
{ending_reference}

【课程参考资料】
{knowledge}

{preference_memory}

【创作要求】
- 长度：{length}
- 风格：{style}
- 字数：约{max_words}字
{content_format_instruction}

【输出格式】
1. 「组合说明」
2. 「文案正文」
3. 「使用的知识点」"""


def _build_knowledge_text(chunks: list[dict]) -> str:
    if not chunks:
        return "（暂无课程参考资料，请基于通用知识创作）"
    items = []
    for i, c in enumerate(chunks):
        items.append(f"[知识点{i+1}] (相关度: {c.get('score', 'N/A')})\n{c['content']}")
    return "\n\n".join(items)


def _call_llm(prompt: str, temperature=0.8, max_tokens=1500) -> str:
    resp = _get_client().chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens
    )
    return resp.choices[0].message.content.strip()


# ── Wizard: AI Sellpoint Search ──

SELLPOINT_SEARCH_PROMPT = """你是一位产品营销专家。请分析以下产品，输出卖点和用户痛点。

产品：{product}

{knowledge_hint}

请输出 JSON（只输出 JSON）：
{{
  "selling_points": ["卖点1", "卖点2", "卖点3", "卖点4", "卖点5"],
  "pain_points": ["痛点1", "痛点2", "痛点3", "痛点4", "痛点5"]
}}

要求：
- 卖点：产品的核心优势、差异化特点、用户为什么买
- 痛点：目标用户在使用前/使用中遇到的真实痛苦场景
- 每个点一句话，具体不空洞
- 如果产品在课程知识中有提及，优先从课程中提取"""


def search_selling_points(product: str) -> dict:
    """AI auto-search selling points + pain points for a product."""
    chunks = query_chunks(product)
    if chunks:
        knowledge_hint = "请参考以下课程知识来分析这个产品：\n" + "\n".join(
            c["content"][:300] for c in chunks[:3]
        )
    else:
        knowledge_hint = "（无课程参考资料，请基于你对这个产品的了解来分析）"

    prompt = SELLPOINT_SEARCH_PROMPT.format(product=product, knowledge_hint=knowledge_hint)
    raw = _call_llm(prompt, temperature=0.5, max_tokens=800)

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
        return {"selling_points": [], "pain_points": [], "raw": raw}


# ── Wizard: Guided Generation ──

PURPOSE_STRATEGY = {
    "卖货/挂车": "文案中后段自然引导下单，强调产品效果和紧迫感，可以加入1-2个用户案例或使用场景。结尾要有行动号召。",
    "引流直播间": "文案制造悬念，结尾不要说完整答案，引导用户进直播间获取更多。用'想知道...来我直播间'等句式。",
    "种草/品宣": "只做认知教育，不做硬推销。让用户觉得'这个我需要'但不直接卖。建立专业感和信任度。",
    "通用文案": "",
}

HOOK_INSTRUCTION = {
    "提问式": "开头用一个面向用户灵魂深处的问题切入，让用户产生'对啊，为什么'的思考。如'你知道为什么...？'",
    "反问式": "开头用'难道...吗'的反问句式，打破用户的固有认知，制造情绪张力。",
    "痛点直击": "开头直接描述用户的一个痛苦场景或尴尬时刻，用'你是不是也...''每天...'等共鸣句式，让用户觉得'说的就是我'。",
    "数据冲击": "开头抛出一个具体数据或比例，制造'原来如此'的冲击感，如'90%的人不知道...''每天有XX人...'。",
    "反常识": "开头说一个和大众认知相反的结论，颠覆用户预期，然后用正文解释为什么。如'真正能XX的，恰恰不是XX的那种'。",
    "故事开头": "开头用'前几天/昨天/我有个朋友/一个学员跟我说'引出一个小故事，在故事中埋入产品相关信息。",
    "悬念": "开头暗示接下来要说的内容很重要，用'接下来这个方法/这个公式/这个秘密'等词制造期待。",
    "AI自动选": "",
}

WIZARD_PROMPT = """你是一位专业的短视频口播文案写手。请根据以下信息撰写一条{length}的短视频口播文案。

【产品信息】
产品：{product}
核心卖点：{selling_points}
用户痛点：{pain_points}

【课程参考资料】
{knowledge}

{preference_memory}

【写作要求】
- 风格：{style}
- 字数：约{max_words}字
- 必须是口播友好语言，念出来自然流畅
{content_format_instruction}{purpose_strategy}{hook_instruction}

【输出格式】
1. 「钩子设计」：说明用了什么钩子类型
2. 「文案正文」：完整口播文案
3. 「引用来源」：使用了课程中的哪些知识点"""


def generate_wizard(
    product: str,
    selling_points: list[str],
    pain_points: list[str],
    purpose: str = "通用文案",
    hook_style: str = "AI自动选",
    length: str = "60秒",
    style: str = "口语化",
    content_format: str = ""
) -> str:
    """Guided wizard generation with product info + purpose + hook style."""
    # RAG retrieval
    search_query = f"{product} {' '.join(selling_points)} {' '.join(pain_points)}"
    chunks = query_chunks(search_query)
    knowledge = _build_knowledge_text(chunks)
    max_words = _resolve_length_words(length)
    preference_memory, _ = build_preference_memory_text(
        product=product,
        video_type=purpose,
        length_label=length
    )

    # Build strategy & hook instruction
    purpose_strategy = PURPOSE_STRATEGY.get(purpose, "")
    hook_instruction = HOOK_INSTRUCTION.get(hook_style, "")
    format_instruction = ""
    if content_format:
        fmt = CONTENT_FORMAT_INSTRUCTION.get(content_format, "")
        if fmt:
            format_instruction = f"\n【内容形式】{content_format}\n要求：{fmt}"

    if purpose_strategy:
        purpose_strategy = f"\n【视频用途】{purpose}\n策略：{purpose_strategy}"
    if hook_instruction:
        hook_instruction = f"\n【开头风格】{hook_style}\n要求：{hook_instruction}"

    sp_text = "\n".join(f"- {sp}" for sp in selling_points) if selling_points else "（未指定，请基于产品通用卖点创作）"
    pp_text = "\n".join(f"- {pp}" for pp in pain_points) if pain_points else "（未指定）"

    prompt = WIZARD_PROMPT.format(
        product=product,
        selling_points=sp_text,
        pain_points=pp_text,
        knowledge=knowledge,
        length=length,
        style=style,
        max_words=max_words,
        preference_memory=preference_memory,
        purpose_strategy=purpose_strategy,
        hook_instruction=hook_instruction,
        content_format_instruction=format_instruction
    )
    return _call_llm(prompt)


def _resolve_length_words(length_label: str) -> int:
    mapping = {"30秒": 120, "60秒": 250, "90秒": 400}
    return mapping.get(length_label, 250)


def generate_free(
    topic: str,
    length: str = "60秒",
    style: str = "口语化",
    purpose: str = "涨粉",
    content_format: str = ""
) -> str:
    chunks = query_chunks(topic)
    knowledge = _build_knowledge_text(chunks)
    max_words = _resolve_length_words(length)
    preference_memory, _ = build_preference_memory_text(
        product=topic,
        video_type=purpose,
        length_label=length
    )
    format_instruction = ""
    if content_format:
        fmt = CONTENT_FORMAT_INSTRUCTION.get(content_format, "")
        if fmt:
            format_instruction = f"\n【内容形式】{content_format}\n要求：{fmt}"
    prompt = FREE_PROMPT.format(
        knowledge=knowledge, length=length,
        style=style, purpose=purpose, max_words=max_words,
        preference_memory=preference_memory,
        content_format_instruction=format_instruction
    )
    return _call_llm(prompt)


def generate_imitate(
    analysis_json: dict,
    original_text: str = "",
    product: str = "",
    selling_points: list = None,
    pain_points: list = None,
    length: str = "60秒",
    style: str = "口语化",
    content_format: str = ""
) -> str:
    if selling_points is None:
        selling_points = []
    if pain_points is None:
        pain_points = []

    ref = analysis_json
    ref_text = f"""
结构类型：{ref.get('structure_type', '未知')}
结构说明：{ref.get('structure_breakdown', '')}
钩子类型：{ref.get('hook_type', '')}
钩子分析：{ref.get('hook_analysis', '')}
节奏特点：{ref.get('rhythm_notes', '')}
改写要点：{ref.get('rewrite_tips', '')}
"""
    search_query = f"{product} {' '.join(selling_points)} {' '.join(pain_points)}" if product else ref.get("structure_breakdown", "")
    chunks = query_chunks(search_query)
    knowledge = _build_knowledge_text(chunks)
    max_words = _resolve_length_words(length)
    preference_memory, _ = build_preference_memory_text(
        product=product,
        video_type="仿写爆款",
        length_label=length
    )

    sp_text = "\n".join(f"- {sp}" for sp in selling_points) if selling_points else "（未指定，请基于产品通用卖点创作）"
    pp_text = "\n".join(f"- {pp}" for pp in pain_points) if pain_points else "（未指定）"

    format_instruction = ""
    if content_format:
        fmt = CONTENT_FORMAT_INSTRUCTION.get(content_format, "")
        if fmt:
            format_instruction = f"\n【内容形式】{content_format}\n要求：{fmt}"

    prompt = IMITATE_PROMPT.format(
        product=product or "（未指定产品）",
        selling_points=sp_text,
        pain_points=pp_text,
        original_text=original_text or ref.get("structure_breakdown", ""),
        reference_structure=ref_text,
        knowledge=knowledge,
        length=length,
        style=style,
        max_words=max_words,
        preference_memory=preference_memory,
        content_format_instruction=format_instruction
    )
    return _call_llm(prompt)


def generate_rewrite(
    draft: str,
    length: str = "60秒",
    style: str = "口语化",
    content_format: str = ""
) -> str:
    chunks = query_chunks(draft[:500])
    knowledge = _build_knowledge_text(chunks)
    max_words = _resolve_length_words(length)
    preference_memory, _ = build_preference_memory_text(
        product=draft[:80],
        video_type="改写润色",
        length_label=length
    )
    format_instruction = ""
    if content_format:
        fmt = CONTENT_FORMAT_INSTRUCTION.get(content_format, "")
        if fmt:
            format_instruction = f"\n【内容形式】{content_format}\n要求：{fmt}"
    prompt = REWRITE_PROMPT.format(
        draft=draft, knowledge=knowledge,
        length=length, style=style, max_words=max_words,
        preference_memory=preference_memory,
        content_format_instruction=format_instruction
    )
    return _call_llm(prompt)


def generate_combine(
    hook_analysis: dict,
    body_analysis: dict,
    ending_analysis: dict,
    topic: str = "",
    length: str = "60秒",
    style: str = "口语化",
    content_format: str = ""
) -> str:
    hook_ref = json.dumps(hook_analysis, ensure_ascii=False, indent=2)
    body_ref = json.dumps(body_analysis, ensure_ascii=False, indent=2)
    ending_ref = json.dumps(ending_analysis, ensure_ascii=False, indent=2)
    search_query = topic if topic else hook_analysis.get("structure_breakdown", "")
    chunks = query_chunks(search_query)
    knowledge = _build_knowledge_text(chunks)
    max_words = _resolve_length_words(length)
    preference_memory, _ = build_preference_memory_text(
        product=topic,
        video_type="组合生成",
        length_label=length
    )
    format_instruction = ""
    if content_format:
        fmt = CONTENT_FORMAT_INSTRUCTION.get(content_format, "")
        if fmt:
            format_instruction = f"\n【内容形式】{content_format}\n要求：{fmt}"
    prompt = COMBINE_PROMPT.format(
        hook_reference=hook_ref, body_reference=body_ref,
        ending_reference=ending_ref, knowledge=knowledge,
        length=length, style=style, max_words=max_words,
        preference_memory=preference_memory,
        content_format_instruction=format_instruction
    )
    return _call_llm(prompt)
