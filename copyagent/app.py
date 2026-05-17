"""CopyAgent - AI 文案智能体 Streamlit App (DeepSeek API)."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import json
from datetime import datetime

from config import KNOWLEDGE_DOCS_DIR, DEEPSEEK_MODEL
from utils.db import (
    init_db, add_knowledge_doc, update_chunk_count, list_knowledge_docs,
    delete_knowledge_doc, save_analysis, list_analyses, get_analysis,
    delete_analysis, save_copy, list_copies, update_copy_status, update_copy_rating,
    delete_copy, get_setting, set_setting, get_recent_products,
    save_copy_version, list_copy_versions, save_copy_feedback, list_copy_feedback,
    save_preference_rules_from_analysis, list_preference_rules,
    update_preference_rule_status, build_preference_memory_text
)
from knowledge.loader import load_file
from knowledge.chunker import split_chunks
from knowledge.retriever import add_chunks, remove_doc_chunks, get_collection_stats
from analyzer.viral import deconstruct
from generator.copywriter import (
    generate_free, generate_imitate, generate_rewrite, generate_combine,
    generate_wizard, search_selling_points, reset_client
)
from generator.feedback import analyze_revision
from hotspot.service import discover_hotspots, generate_hotspot_topics, generate_hotspot_copy
from scheduler import (
    start_scheduler, stop_scheduler, is_scheduler_running,
    get_next_run_time, set_schedule_time, get_schedule_time, manual_generate_now
)

st.set_page_config(page_title="CopyAgent - 文案智能体", page_icon="✍️", layout="wide")

init_db()

# Load saved API key
import config as cfg
saved_key = get_setting("deepseek_api_key", "")
if saved_key:
    cfg.DEEPSEEK_API_KEY = saved_key
    reset_client()
saved_bing_key = get_setting("bing_search_api_key", "")
if saved_bing_key:
    os.environ["BING_SEARCH_API_KEY"] = saved_bing_key

if not is_scheduler_running():
    start_scheduler()

st.sidebar.title("✍️ CopyAgent")
st.sidebar.caption(f"模型: {DEEPSEEK_MODEL}")

tab = st.sidebar.radio(
    "导航",
    ["🔥 热点选题", "🏠 首页", "📚 知识库", "🔍 爆款拆解", "📋 历史记录", "🧠 偏好记忆", "⚙️ 设置"]
)

LENGTH_OPTIONS = ["30秒", "60秒", "90秒"]
STYLE_OPTIONS = ["口语化", "情绪化", "专业感", "幽默"]
PURPOSE_OPTIONS = ["涨粉", "引流", "成交", "种草", "品牌"]

CONTENT_FORMAT_OPTIONS = [
    "单人口播", "剧情演绎", "测评对比", "Vlog分享",
    "干货讲解", "对话访谈", "开箱体验", "场景种草",
]

CONTENT_FORMAT_DESCRIPTIONS = {
    "单人口播": "单人面对镜头口播，语气像和观众对话，句式简短自然。",
    "剧情演绎": "设计1-2个角色的简短对话或情景剧，有人物互动和情节推进。",
    "测评对比": "产品对比或使用前后对比，有客观数据和主观体验，结构清晰。",
    "Vlog分享": "第一人称生活分享，穿插日常场景描述，口吻轻松自然。",
    "干货讲解": "知识科普+产品植入，先讲干货建立专业感，再自然带出产品。",
    "对话访谈": "两人对话形式，一问一答推进内容，角色自然不做作。",
    "开箱体验": "第一人称开箱/体验记录，强调真实感受和细节发现。",
    "场景种草": "聚焦一个具体使用场景，先渲染需求再展示产品如何解决。",
}

FEEDBACK_RATING_OPTIONS = {
    "满意，已采用": "satisfied",
    "基本可用，我做了修改": "edited",
    "不满意，原因是": "unsatisfied",
    "上传最终拍摄稿": "used",
}

FEEDBACK_REASON_OPTIONS = [
    "太书面", "太夸张", "不像我", "卖点不准", "节奏慢",
    "剧情弱", "字数不合适", "开头不够抓人", "转化引导太硬"
]


def _json_list(value):
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _copy_metadata(c):
    return {
        "product": c.get("product", ""),
        "mode": c.get("mode", ""),
        "video_type": c.get("purpose", "") or c.get("mode", ""),
        "purpose": c.get("purpose", ""),
        "length": c.get("length", ""),
        "style": c.get("style", ""),
    }


def render_preference_hits(product="", video_type="", people_count="", length_label="", title="本次可参考的历史偏好"):
    _, rules = build_preference_memory_text(product, video_type, people_count, length_label, limit=5)
    if rules:
        with st.expander(f"🧠 {title}（{len(rules)} 条）", expanded=False):
            for r in rules:
                prefix = "应该" if r.get("rule_type") == "prefer" else "避免"
                st.caption(f"{prefix}：{r.get('rule_text', '')}")


def render_feedback_form(c, prefix):
    feedbacks = list_copy_feedback(c["id"], limit=3)
    if feedbacks:
        with st.expander(f"🧠 最近反馈记忆（{len(feedbacks)} 条）", expanded=False):
            for fb in feedbacks:
                analysis = {}
                try:
                    analysis = json.loads(fb.get("analysis_json") or "{}")
                except Exception:
                    pass
                st.caption(f"{fb.get('created_at', '')[:16]} · {fb.get('rating', '')}")
                if analysis.get("summary"):
                    st.write(analysis["summary"])
                elif fb.get("note"):
                    st.write(fb["note"])

    with st.expander("🧠 反馈 / 上传修改稿", expanded=False):
        rating_label = st.selectbox(
            "这条文案的使用情况",
            list(FEEDBACK_RATING_OPTIONS.keys()),
            key=f"{prefix}_fb_rating_{c['id']}"
        )
        reason_tags = st.multiselect(
            "修改或不满意的原因",
            FEEDBACK_REASON_OPTIONS,
            key=f"{prefix}_fb_reasons_{c['id']}"
        )
        final_content = st.text_area(
            "最终使用稿 / 修改后文案",
            value=c.get("content", ""),
            height=180,
            key=f"{prefix}_fb_final_{c['id']}",
            help="如果你拍摄前改过文案，把最终版本粘贴在这里，系统会学习你的修改偏好。"
        )
        note = st.text_area(
            "补充说明（可选）",
            placeholder="例：我不喜欢一上来制造焦虑，更想用生活化场景开头。",
            height=90,
            key=f"{prefix}_fb_note_{c['id']}"
        )
        is_shot = st.checkbox("这版已经用于拍摄", key=f"{prefix}_fb_shot_{c['id']}")
        performance_note = st.text_input(
            "视频表现备注（可选）",
            placeholder="例：评论区问价格的人变多了",
            key=f"{prefix}_fb_perf_{c['id']}"
        )

        if st.button("保存反馈并生成记忆", type="primary", key=f"{prefix}_fb_submit_{c['id']}"):
            rating = FEEDBACK_RATING_OPTIONS[rating_label]
            analysis = {}
            if final_content.strip():
                version_type = "final_shooting" if is_shot else "user_edited"
                save_copy_version(c["id"], version_type, final_content.strip())

                try:
                    with st.spinner("正在分析你修改了什么..."):
                        analysis = analyze_revision(
                            original_content=c.get("content", ""),
                            final_content=final_content.strip(),
                            metadata=_copy_metadata(c),
                            reason_tags=reason_tags,
                            note=note
                        )
                except Exception as e:
                    st.warning(f"反馈已保存，但 AI 分析失败：{e}")

            feedback_id = save_copy_feedback(
                c["id"],
                rating=rating,
                reason_tags=reason_tags,
                note=note,
                final_content=final_content.strip(),
                is_shot=is_shot,
                performance_note=performance_note,
                analysis_json=analysis,
            )

            saved_rules = save_preference_rules_from_analysis(
                analysis,
                source_feedback_id=feedback_id,
                product=c.get("product", ""),
                video_type=c.get("purpose", "") or c.get("mode", ""),
                length_min=0,
                length_max=0,
            )
            if is_shot:
                update_copy_status(c["id"], "shot")

            st.success(f"已保存反馈，新增 {len(saved_rules)} 条偏好记忆")
            st.rerun()

# ═══════════════════ TAB: 首页 ═══════════════════
if tab == "🏠 首页":
    st.title("今日文案")

    col1, col2, col3 = st.columns(3)
    with col1:
        stats = get_collection_stats()
        st.metric("知识库片段", stats["chunk_count"])
    with col2:
        next_run = get_next_run_time()
        st.metric("下次自动生成", next_run.strftime("%H:%M") if next_run else "未启动")
    with col3:
        today = datetime.now().strftime("%Y-%m-%d")
        recent = list_copies(limit=50)
        today_count = sum(1 for c in recent if c["created_at"] and c["created_at"].startswith(today))
        st.metric("今日已生成", today_count)

    st.divider()

    col_btn, _ = st.columns([1, 3])
    with col_btn:
        if st.button("⚡ 立即生成今日文案", type="primary", use_container_width=True):
            with st.spinner("正在生成..."):
                try:
                    results = manual_generate_now()
                    st.success(f"已生成 {len(results)} 条文案")
                    st.rerun()
                except Exception as e:
                    st.error(f"生成失败: {e}")

    st.subheader("最近文案")
    copies = list_copies(limit=20)
    if not copies:
        st.info("还没有文案。上传课程文档后，点击上方按钮或等待定时生成。")
    else:
        for c in copies:
            with st.expander(f"{c['title']}  [{c.get('mode','')}] [{c.get('created_at','')[:16]}]"):
                st.text_area("内容", c["content"], height=200, key=f"copy_{c['id']}", label_visibility="collapsed")
                col1, col2, col3, _ = st.columns([1, 1, 1, 3])
                with col1:
                    status_map = {"draft": "📝 待拍", "shot": "🎬 已拍", "published": "✅ 已发"}
                    cur = c.get("status", "draft")
                    if st.button(status_map.get(cur, cur), key=f"stat_{c['id']}"):
                        nxt = {"draft": "shot", "shot": "published", "published": "draft"}
                        update_copy_status(c["id"], nxt.get(cur, "draft"))
                        st.rerun()
                with col2:
                    rating = c.get("rating", 0) or 0
                    st.caption(f"评分: {'⭐'*rating if rating else '—'}")
                with col3:
                    if st.button("🗑️", key=f"del_{c['id']}"):
                        delete_copy(c["id"])
                        st.rerun()
                render_feedback_form(c, "home")

# ═══════════════════ TAB: 知识库 ═══════════════════
elif tab == "📚 知识库":
    st.title("知识库管理")

    with st.expander("➕ 导入文档", expanded=True):
        uploaded = st.file_uploader(
            "上传课程文档 (md/txt/docx/pdf)",
            type=["md", "txt", "docx", "pdf"],
            accept_multiple_files=True
        )
        if uploaded:
            for f in uploaded:
                suffix = f.name.split(".")[-1].lower()
                save_path = KNOWLEDGE_DOCS_DIR / f.name
                save_path.write_bytes(f.getvalue())
                try:
                    text = load_file(str(save_path))
                    chunks = split_chunks(text)
                    doc_id = add_knowledge_doc(f.name, str(save_path), suffix)
                    add_chunks(doc_id, chunks)
                    update_chunk_count(doc_id, len(chunks))
                    st.success(f"✅ {f.name} — {len(chunks)} 个片段")
                except Exception as e:
                    st.error(f"❌ {f.name}: {e}")

    st.subheader("已导入文档")
    docs = list_knowledge_docs()
    if not docs:
        st.info("还没有导入任何文档。上传你的课程资料开始吧。")
    else:
        for d in docs:
            c1, c2, c3 = st.columns([4, 1, 1])
            with c1:
                st.write(f"📄 {d['title']} ({d['file_type']}) — {d['chunk_count']} 片段")
            with c2:
                st.caption(d["created_at"][:10] if d["created_at"] else "")
            with c3:
                if st.button("🗑️", key=f"deldoc_{d['id']}"):
                    remove_doc_chunks(d["id"])
                    delete_knowledge_doc(d["id"])
                    st.rerun()

# ═══════════════════ TAB: 爆款拆解 ═══════════════════
elif tab == "🔍 爆款拆解":
    st.title("爆款拆解")

    mode = st.radio("输入方式", ["粘贴文本", "批量粘贴"], horizontal=True)

    if mode == "粘贴文本":
        col1, col2 = st.columns([2, 1])
        with col1:
            raw_text = st.text_area("粘贴爆款文案", height=200, placeholder="粘贴短视频口播文案...")
            title = st.text_input("标题（可选）", placeholder="给这条分析起个名字")
        with col2:
            st.caption("拆解维度")
            st.markdown("🏗️ 结构模型 | 🪝 钩子类型 | 📈 情绪曲线 | ✨ 金句提取 | 🎵 节奏分析")

        if st.button("🔍 开始拆解", type="primary", use_container_width=True):
            if not raw_text.strip():
                st.warning("请先粘贴文案")
            else:
                with st.spinner("拆解中..."):
                    result = deconstruct(raw_text)
                    title_final = title or raw_text[:30] + "..."
                    save_analysis(title_final, raw_text, result)
                    st.session_state["last_analysis"] = result
                    st.session_state["last_raw"] = raw_text

        if "last_analysis" in st.session_state:
            a = st.session_state["last_analysis"]
            st.divider()
            st.subheader("拆解结果")
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("结构模型", a.get("structure_type", ""))
            with c2: st.metric("钩子类型", a.get("hook_type", ""))
            with c3: st.metric("目标受众", a.get("target_audience", ""))
            st.write("**结构分析**:", a.get("structure_breakdown", ""))
            st.write("**钩子分析**:", a.get("hook_analysis", ""))
            st.write("**节奏特点**:", a.get("rhythm_notes", ""))
            st.write("**仿写要点**:", a.get("rewrite_tips", ""))
            if a.get("golden_sentences"):
                st.write("**金句**:")
                for s in a["golden_sentences"]:
                    st.info(s)
            if a.get("emotion_curve"):
                st.write("**情绪曲线**:")
                st.dataframe([
                    {"句子": e.get("text", "")[:30], "情绪": e.get("emotion", ""),
                     "强度": "█" * e.get("intensity", 1)}
                    for e in a["emotion_curve"]
                ], use_container_width=True)

            if st.button("🎯 用这个结构仿写", type="primary"):
                st.session_state["imitate_analysis"] = a
                st.session_state["creation_path"] = "高级模式"
                st.session_state["mode"] = "仿写爆款"

    else:
        raw_text = st.text_area("批量粘贴（每条用 --- 分隔）", height=200,
                                placeholder="文案1\n---\n文案2\n---\n文案3")
        if st.button("🔍 批量拆解", type="primary"):
            if not raw_text.strip():
                st.warning("请先粘贴文案")
            else:
                texts = [t.strip() for t in raw_text.split("---") if t.strip()]
                with st.spinner(f"正在拆解 {len(texts)} 条..."):
                    for i, t in enumerate(texts):
                        result = deconstruct(t)
                        save_analysis(f"批量拆解 #{i+1}", t, result)
                    st.success(f"已完成 {len(texts)} 条拆解")

    st.divider()
    st.subheader("拆解历史")
    for a in list_analyses()[:10]:
        with st.expander(f"{a['title']} [{a.get('structure_type','')}] [{a.get('created_at','')[:16]}]"):
            st.text_area("原文", a.get("raw_text", ""), height=100, key=f"araw_{a['id']}", label_visibility="collapsed")
            analysis = json.loads(a.get("analysis_json", "{}"))
            if analysis: st.json(analysis)
            if st.button("🗑️", key=f"dela_{a['id']}"):
                delete_analysis(a["id"]); st.rerun()

# ═══════════════════ TAB: 热点选题 & 文案生成 ═══════════════════
elif tab == "🔥 热点选题":
    st.title("🔥 热点选题 & 文案生成")

    # ── Session State Init (all merged keys) ──
    for key, default in [
        ("creation_path", "热点驱动"),
        ("content_format", "单人口播"),
        # Hotspot keys
        ("hotspot_product", ""), ("hotspot_platform", "抖音"),
        ("hotspot_days", 30), ("hotspot_count", 10),
        ("hotspot_audience", ""), ("hotspot_selling_points", ""),
        ("hotspot_purpose", "种草"), ("hotspot_bundle", None),
        ("hotspot_topics", []), ("hotspot_selected_topic", None),
        ("hotspot_copy", ""), ("hotspot_length", "60秒"),
        ("hotspot_style", "口语化"),
        # Wizard keys
        ("wizard_step", 1), ("wizard_product", ""), ("wizard_selling_points", []),
        ("wizard_pain_points", []), ("wizard_sellpoint_mode", "manual"),
        ("wizard_purpose", "通用文案"), ("wizard_hook_style", "痛点直击"),
        ("wizard_length", "60秒"), ("wizard_style", "口语化"),
        ("wizard_result", ""), ("wizard_search_done", False),
        # Advanced mode keys
        ("show_advanced", False), ("mode", "自由创作"),
        ("imit_product", ""), ("imit_sellpoint_mode", "ai"),
        ("imit_selling_points", []), ("imit_pain_points", []),
        ("imit_search_done", False), ("imit_result", ""),
        ("imit_ai_sps", []), ("imit_ai_pps", []),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    hs = lambda k: st.session_state[k]

    # ── Handle redirect from 爆款拆解 ──
    if st.session_state.get("imitate_analysis"):
        st.session_state["creation_path"] = "高级模式"
        st.session_state["creation_path_radio"] = "高级模式"
        st.session_state["mode"] = "仿写爆款"

    # ── Shared: Creation Path ──
    creation_path = st.radio(
        "创作路径",
        ["热点驱动", "向导模式", "高级模式"],
        horizontal=True,
        key="creation_path_radio",
        index=["热点驱动", "向导模式", "高级模式"].index(st.session_state.get("creation_path", "热点驱动"))
    )
    st.session_state["creation_path"] = creation_path

    # ── Shared: Content Format ──
    content_format = st.selectbox(
        "🎬 内容形式",
        CONTENT_FORMAT_OPTIONS,
        index=CONTENT_FORMAT_OPTIONS.index(st.session_state.get("content_format", "单人口播"))
            if st.session_state.get("content_format", "单人口播") in CONTENT_FORMAT_OPTIONS else 0,
        key="content_format_select",
        help="选择文案的表现形式，AI 会根据不同形式调整脚本结构和表达方式"
    )
    st.session_state["content_format"] = content_format
    st.caption(CONTENT_FORMAT_DESCRIPTIONS.get(content_format, ""))

    st.divider()

    # ═══════════════════════════════════════════
    # PATH: 热点驱动 (Hotspot Discovery Flow)
    # ═══════════════════════════════════════════
    if creation_path == "热点驱动":

        st.subheader("第 1 步：输入产品")
        c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
        with c1:
            product = st.text_input(
                "产品名称",
                value=hs("hotspot_product"),
                placeholder="例：水杯、保温杯、空气炸锅"
            )
            st.session_state["hotspot_product"] = product
            # Cross-pollinate to wizard
            if product.strip():
                st.session_state["wizard_product"] = product
        with c2:
            platform_options = ["抖音", "小红书", "视频号", "快手", "全网"]
            platform = st.selectbox(
                "平台",
                platform_options,
                index=platform_options.index(hs("hotspot_platform")) if hs("hotspot_platform") in platform_options else 0
            )
            st.session_state["hotspot_platform"] = platform
        with c3:
            days = st.selectbox(
                "时间范围",
                [7, 30, 90],
                index=[7, 30, 90].index(hs("hotspot_days")) if hs("hotspot_days") in [7, 30, 90] else 1,
                format_func=lambda x: f"近 {x} 天"
            )
            st.session_state["hotspot_days"] = days
        with c4:
            topic_count = st.selectbox(
                "选题数量",
                [10, 15, 20],
                index=[10, 15, 20].index(hs("hotspot_count")) if hs("hotspot_count") in [10, 15, 20] else 0
            )
            st.session_state["hotspot_count"] = topic_count

        c1, c2 = st.columns(2)
        with c1:
            audience = st.text_input(
                "目标人群（可选）",
                value=hs("hotspot_audience"),
                placeholder="例：上班族、宝妈、学生、健身人群"
            )
            st.session_state["hotspot_audience"] = audience
        with c2:
            purpose_options = ["种草", "卖货/挂车", "引流直播间", "品牌曝光"]
            purpose = st.selectbox(
                "视频目的",
                purpose_options,
                index=purpose_options.index(hs("hotspot_purpose")) if hs("hotspot_purpose") in purpose_options else 0
            )
            st.session_state["hotspot_purpose"] = purpose

        selling_points = st.text_area(
            "产品卖点（可选，一行一个或逗号分隔）",
            value=hs("hotspot_selling_points"),
            height=80,
            placeholder="例：大容量、不漏水、316不锈钢、杯口好清洗"
        )
        st.session_state["hotspot_selling_points"] = selling_points

        c1, c2 = st.columns([1, 4])
        with c1:
            if st.button("🔍 找热点并生成选题", type="primary", use_container_width=True):
                if not product.strip():
                    st.warning("请先输入产品名称")
                else:
                    with st.spinner(f"正在搜索「{product.strip()}」的近期热点，并生成选题..."):
                        try:
                            bundle = discover_hotspots(
                                product=product.strip(),
                                platform=platform,
                                days=days,
                                audience=audience.strip(),
                                selling_points=selling_points.strip(),
                                purpose=purpose,
                            )
                            topics = generate_hotspot_topics(
                                product=product.strip(),
                                hotspot_analysis=bundle.get("analysis", {}),
                                topic_count=topic_count,
                                platform=platform,
                                audience=audience.strip(),
                                selling_points=selling_points.strip(),
                                purpose=purpose,
                            )
                            st.session_state["hotspot_bundle"] = bundle
                            st.session_state["hotspot_topics"] = topics
                            st.session_state["hotspot_selected_topic"] = None
                            st.session_state["hotspot_copy"] = ""
                            st.rerun()
                        except Exception as e:
                            st.error(f"热点选题生成失败：{e}")
        with c2:
            st.caption("第一版优先用搜索结果标题和摘要做热点分析；如果没有搜索 API Key，会尝试免 Key 搜索兜底，搜索失败时会基于品类常见痛点生成。")

        bundle = hs("hotspot_bundle")
        topics = hs("hotspot_topics")

        if bundle:
            st.divider()
            st.subheader("第 2 步：热点分析")
            analysis = bundle.get("analysis", {})
            data_status = analysis.get("data_status", "")
            if data_status == "insufficient":
                st.warning("当前热点数据不足，已基于品类常见痛点补足选题方向。")
            else:
                st.success("已完成热点分析")

            st.write(analysis.get("summary", ""))
            c1, c2, c3 = st.columns(3)
            with c1:
                st.write("**热门话题**")
                for item in analysis.get("hot_topics", [])[:6]:
                    st.caption(item)
            with c2:
                st.write("**用户痛点**")
                for item in analysis.get("pain_points", [])[:6]:
                    st.caption(item)
            with c3:
                st.write("**高频场景**")
                for item in analysis.get("scenes", [])[:6]:
                    st.caption(item)

            with st.expander("查看搜索词和原始搜索结果", expanded=False):
                st.write("**搜索词：**")
                st.code("\n".join(bundle.get("queries", [])), language="text")
                results = bundle.get("results", [])
                if results:
                    for r in results[:20]:
                        st.markdown(f"- **{r.get('title', '')}**  \n  {r.get('snippet', '')}  \n  `{r.get('source', '')}` · {r.get('url', '')}")
                else:
                    st.info("没有获取到搜索结果。")

        if topics:
            st.divider()
            st.subheader("第 3 步：选择一个选题")

            for i, topic in enumerate(topics):
                with st.expander(f"{i + 1}. {topic.get('title', '')}", expanded=i == 0):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.write("**核心痛点**")
                        st.write(topic.get("pain_point", ""))
                        st.write("**推荐开头**")
                        st.info(topic.get("opening", ""))
                    with c2:
                        st.write("**人群 / 角度**")
                        st.write(f"{topic.get('target_audience', '')} · {topic.get('angle', '')}")
                        st.write("**拍摄建议**")
                        st.write(topic.get("shooting_tips", ""))
                        st.caption(f"热点依据：{topic.get('hotspot_basis', '')}")

                    if st.button("用这个选题生成文案", key=f"hotspot_pick_{i}", type="primary"):
                        st.session_state["hotspot_selected_topic"] = topic
                        with st.spinner("正在根据选题生成痛点开头文案..."):
                            try:
                                copy = generate_hotspot_copy(
                                    product=hs("hotspot_product").strip(),
                                    topic=topic,
                                    hotspot_analysis=(hs("hotspot_bundle") or {}).get("analysis", {}),
                                    platform=hs("hotspot_platform"),
                                    purpose=hs("hotspot_purpose"),
                                    audience=hs("hotspot_audience").strip(),
                                    selling_points=hs("hotspot_selling_points").strip(),
                                    length=hs("hotspot_length"),
                                    style=hs("hotspot_style"),
                                    content_format=hs("content_format"),
                                )
                                st.session_state["hotspot_copy"] = copy
                                st.rerun()
                            except Exception as e:
                                st.error(f"文案生成失败：{e}")

        if hs("hotspot_selected_topic"):
            st.divider()
            st.subheader("第 4 步：生成文案")
            c1, c2 = st.columns(2)
            with c1:
                length = st.selectbox(
                    "文案长度",
                    LENGTH_OPTIONS,
                    index=LENGTH_OPTIONS.index(hs("hotspot_length")) if hs("hotspot_length") in LENGTH_OPTIONS else 1,
                    key="hotspot_length_select"
                )
                st.session_state["hotspot_length"] = length
            with c2:
                style = st.selectbox(
                    "文案风格",
                    STYLE_OPTIONS,
                    index=STYLE_OPTIONS.index(hs("hotspot_style")) if hs("hotspot_style") in STYLE_OPTIONS else 0,
                    key="hotspot_style_select"
                )
                st.session_state["hotspot_style"] = style

            selected = hs("hotspot_selected_topic")
            st.caption(f"当前选题：{selected.get('title', '')}")
            render_preference_hits(
                hs("hotspot_product"),
                hs("hotspot_purpose"),
                length_label=hs("hotspot_length")
            )

            c1, c2, c3 = st.columns([1, 1, 4])
            with c1:
                if st.button("🔄 重新生成", use_container_width=True):
                    with st.spinner("正在重新生成..."):
                        try:
                            copy = generate_hotspot_copy(
                                product=hs("hotspot_product").strip(),
                                topic=selected,
                                hotspot_analysis=(hs("hotspot_bundle") or {}).get("analysis", {}),
                                platform=hs("hotspot_platform"),
                                purpose=hs("hotspot_purpose"),
                                audience=hs("hotspot_audience").strip(),
                                selling_points=hs("hotspot_selling_points").strip(),
                                length=hs("hotspot_length"),
                                style=hs("hotspot_style"),
                                content_format=hs("content_format"),
                            )
                            st.session_state["hotspot_copy"] = copy
                            st.rerun()
                        except Exception as e:
                            st.error(f"重新生成失败：{e}")
            with c2:
                if st.button("💾 保存", type="primary", use_container_width=True):
                    if not hs("hotspot_copy").strip():
                        st.warning("还没有可保存的文案")
                    else:
                        save_copy(
                            title=f"{hs('hotspot_product')} - {selected.get('title', '')}",
                            content=hs("hotspot_copy"),
                            mode="hotspot",
                            length=hs("hotspot_length"),
                            style=hs("hotspot_style"),
                            purpose=hs("hotspot_purpose"),
                            product=hs("hotspot_product"),
                            selling_points=[s.strip() for s in hs("hotspot_selling_points").replace("，", ",").split(",") if s.strip()],
                            pain_points=[selected.get("pain_point", "")]
                        )
                        st.success("已保存到历史记录")

            if hs("hotspot_copy"):
                st.text_area("文案", hs("hotspot_copy"), height=420, key="hotspot_copy_display", label_visibility="collapsed")
                st.caption("按 Ctrl+A 全选后 Ctrl+C 复制")

    # ═══════════════════════════════════════════
    # PATH: 向导模式 (Wizard)
    # ═══════════════════════════════════════════
    elif creation_path == "向导模式":
        ws = lambda k: st.session_state[k]

        # Progress bar
        steps = ["1.产品", "2.卖点", "3.用途", "4.开头"]
        pct = (ws("wizard_step") - 1) / 3 if ws("wizard_step") <= 4 else 1.0
        st.progress(pct)

        cols = st.columns(4)
        for i, label in enumerate(steps):
            step_num = i + 1
            cur = ws("wizard_step")
            if ws("wizard_step") > 4:
                marker = "✅" if i < 4 else "📝"
            elif step_num < cur:
                marker = "✅"
            elif step_num == cur:
                marker = "●"
            else:
                marker = "○"
            with cols[i]:
                st.caption(f"{marker} {label}")

        st.divider()

        # Step 1: Product
        if ws("wizard_step") == 1:
            st.subheader("第 1 步：你要推广什么产品？")
            recent = get_recent_products(8)
            product_input = st.text_input(
                "产品名称", value=ws("wizard_product"),
                placeholder="例：AI写作训练营、胶原蛋白饮、私域运营课",
                key="wiz_product_input"
            )
            if recent:
                st.caption("最近用过的产品：")
                rcols = st.columns(4)
                for i, rp in enumerate(recent):
                    with rcols[i % 4]:
                        if st.button(rp, key=f"rec_{i}"):
                            st.session_state["wizard_product"] = rp
                            st.rerun()

            st.session_state["wizard_product"] = product_input

            c1, c2 = st.columns([1, 4])
            with c1:
                if st.button("下一步 →", type="primary", use_container_width=True):
                    if not ws("wizard_product").strip():
                        st.warning("请先输入产品名称")
                    else:
                        st.session_state["wizard_search_done"] = False
                        st.session_state["wizard_sellpoint_mode"] = "manual"
                        st.session_state["wizard_selling_points"] = []
                        st.session_state["wizard_pain_points"] = []
                        st.session_state["wizard_step"] = 2
                        st.rerun()

        # Step 2: Selling Points
        elif ws("wizard_step") == 2:
            st.subheader(f"第 2 步：{ws('wizard_product')} 的核心卖点和用户痛点")

            sellpoint_mode = st.radio(
                "卖点来源",
                ["我自己填", "帮我自动搜索"],
                horizontal=True,
                key="wiz_sp_mode",
                index=0 if ws("wizard_sellpoint_mode") == "manual" else 1
            )
            st.session_state["wizard_sellpoint_mode"] = "manual" if sellpoint_mode == "我自己填" else "ai"

            if ws("wizard_sellpoint_mode") == "manual":
                sp_default = ws("wizard_selling_points") if ws("wizard_selling_points") else [""]
                new_sps = []
                for i, sp in enumerate(sp_default):
                    new_val = st.text_input(f"卖点 {i+1}", value=sp, placeholder="例：7天写出100条爆款文案", key=f"sp_{i}")
                    new_sps.append(new_val)

                pp_default = ws("wizard_pain_points") if ws("wizard_pain_points") else [""]
                new_pps = []
                for i, pp in enumerate(pp_default):
                    new_val = st.text_input(f"痛点 {i+1}", value=pp, placeholder="例：每天没时间写文案", key=f"pp_{i}")
                    new_pps.append(new_val)

                st.session_state["wizard_selling_points"] = [s for s in new_sps if s.strip()]
                st.session_state["wizard_pain_points"] = [p for p in new_pps if p.strip()]

            else:
                if st.button("🔍 开始搜索", type="primary", use_container_width=True):
                    with st.spinner(f"正在搜索「{ws('wizard_product')}」的卖点和痛点..."):
                        result = search_selling_points(ws("wizard_product"))
                        st.session_state["wizard_selling_points"] = result.get("selling_points", [])
                        st.session_state["wizard_pain_points"] = result.get("pain_points", [])
                        st.session_state["wizard_search_done"] = True
                        st.rerun()

                if ws("wizard_search_done"):
                    st.success("搜索完成，勾选你要用的：")

                    sps = ws("wizard_selling_points")
                    pps = ws("wizard_pain_points")

                    st.write("**卖点：**")
                    selected_sps = []
                    for i, sp in enumerate(sps):
                        if st.checkbox(sp, value=True, key=f"sel_sp_{i}"):
                            selected_sps.append(sp)
                    st.write("**痛点：**")
                    selected_pps = []
                    for i, pp in enumerate(pps):
                        if st.checkbox(pp, value=True, key=f"sel_pp_{i}"):
                            selected_pps.append(pp)

                    st.session_state["wizard_selling_points"] = selected_sps
                    st.session_state["wizard_pain_points"] = selected_pps

                    if st.button("🔄 重新搜索", key="research"):
                        st.session_state["wizard_search_done"] = False
                        st.rerun()

            c1, c2, c3 = st.columns([1, 1, 5])
            with c1:
                if st.button("← 上一步", use_container_width=True):
                    st.session_state["wizard_step"] = 1
                    st.rerun()
            with c2:
                if st.button("跳过 →", use_container_width=True):
                    st.session_state["wizard_step"] = 3
                    st.rerun()
            st.caption("不填也没关系，AI 会基于产品名自动发挥。点「跳过」直接进入下一步。")

            c1, c2 = st.columns([1, 4])
            with c1:
                if st.button("下一步 →", type="primary", use_container_width=True):
                    st.session_state["wizard_step"] = 3
                    st.rerun()

        # Step 3: Purpose
        elif ws("wizard_step") == 3:
            st.subheader("第 3 步：这个视频用来干什么？")
            purpose = st.radio(
                "视频用途",
                ["卖货/挂车", "引流直播间", "种草/品宣", "通用文案"],
                horizontal=True,
                index=["卖货/挂车", "引流直播间", "种草/品宣", "通用文案"].index(ws("wizard_purpose")) if ws("wizard_purpose") in ["卖货/挂车", "引流直播间", "种草/品宣", "通用文案"] else 3,
                key="wiz_purpose"
            )
            st.session_state["wizard_purpose"] = purpose

            desc = {
                "卖货/挂车": "突出产品效果 + 用户见证 + 引导下单",
                "引流直播间": "留悬念 + 不说完 + 引导进直播间",
                "种草/品宣": "建立认知 + 激发兴趣 + 不硬卖",
                "通用文案": "AI 自由发挥，不做特别限定"
            }
            st.info(f"📌 {desc.get(purpose, '')}")

            c1, c2, c3 = st.columns([1, 1, 5])
            with c1:
                if st.button("← 上一步", key="back3", use_container_width=True):
                    st.session_state["wizard_step"] = 2
                    st.rerun()
            with c2:
                if st.button("下一步 →", type="primary", key="next3", use_container_width=True):
                    st.session_state["wizard_step"] = 4
                    st.rerun()

        # Step 4: Hook Style
        elif ws("wizard_step") == 4:
            st.subheader("第 4 步：开头用什么风格？")

            hook_options = ["痛点直击", "提问式", "反问式", "数据冲击", "反常识", "故事开头", "悬念", "AI自动选"]
            hook_descriptions = {
                "痛点直击": "\"你是不是也有这个问题...\" — 强共鸣、快速留人",
                "提问式": "\"你知道为什么...？\" — 引发思考、适合干货",
                "反问式": "\"难道...？\" — 打破偏见、情绪张力",
                "数据冲击": "\"90%的人不知道...\" — 建立权威、制造好奇",
                "反常识": "\"你以为...其实...\" — 颠覆认知、高停留",
                "故事开头": "\"昨天一个学员跟我说...\" — 代入感、信任感",
                "悬念": "\"接下来这个方法...\" — 制造期待、高完播率",
                "AI自动选": "系统根据产品和用途自动选择最合适的开头"
            }

            hook_style = st.radio(
                "开头风格",
                hook_options,
                horizontal=False,
                index=hook_options.index(ws("wizard_hook_style")) if ws("wizard_hook_style") in hook_options else 0,
                key="wiz_hook",
                format_func=lambda x: f"{x} — {hook_descriptions.get(x, '')}"
            )
            st.session_state["wizard_hook_style"] = hook_style

            c1, c2 = st.columns(2)
            with c1:
                length = st.selectbox("文案长度", LENGTH_OPTIONS, index=1, key="wiz_len")
                st.session_state["wizard_length"] = length
            with c2:
                style = st.selectbox("文案风格", STYLE_OPTIONS, key="wiz_style")
                st.session_state["wizard_style"] = style

            st.divider()

            st.caption("📋 生成预览：")
            st.markdown(f"""
            | 项目 | 内容 |
            |------|------|
            | 产品 | {ws('wizard_product')} |
            | 卖点 | {', '.join(ws('wizard_selling_points')) if ws('wizard_selling_points') else 'AI 自动发挥'} |
            | 痛点 | {', '.join(ws('wizard_pain_points')) if ws('wizard_pain_points') else 'AI 自动发挥'} |
            | 用途 | {ws('wizard_purpose')} |
            | 开头 | {ws('wizard_hook_style')} |
            | 长度 | {ws('wizard_length')} |
            """)
            render_preference_hits(
                ws("wizard_product"),
                ws("wizard_purpose"),
                length_label=ws("wizard_length")
            )

            c1, c2, c3 = st.columns([1, 1, 5])
            with c1:
                if st.button("← 上一步", key="back4", use_container_width=True):
                    st.session_state["wizard_step"] = 3
                    st.rerun()
            with c2:
                if st.button("✍️ 生成文案", type="primary", key="generate_wiz", use_container_width=True):
                    with st.spinner("AI 正在创作..."):
                        result = generate_wizard(
                            product=ws("wizard_product"),
                            selling_points=ws("wizard_selling_points"),
                            pain_points=ws("wizard_pain_points"),
                            purpose=ws("wizard_purpose"),
                            hook_style=ws("wizard_hook_style"),
                            length=ws("wizard_length"),
                            style=ws("wizard_style"),
                            content_format=hs("content_format"),
                        )
                        st.session_state["wizard_result"] = result
                        st.session_state["wizard_step"] = 5
                        st.rerun()

        # Step 5: Result
        elif ws("wizard_step") == 5:
            st.success("✅ 文案生成完成")

            st.subheader("生成结果")
            st.text_area("文案", ws("wizard_result"), height=400, key="wiz_result_display", label_visibility="collapsed")
            st.caption("按 Ctrl+A 全选后 Ctrl+C 复制")

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                if st.button("💾 保存文案", type="primary", use_container_width=True):
                    save_copy(
                        title=f"{ws('wizard_product')} - {ws('wizard_purpose')}",
                        content=ws("wizard_result"),
                        mode="wizard",
                        length=ws("wizard_length"),
                        style=ws("wizard_style"),
                        purpose=ws("wizard_purpose"),
                        product=ws("wizard_product"),
                        selling_points=ws("wizard_selling_points"),
                        pain_points=ws("wizard_pain_points")
                    )
                    st.success("已保存到历史记录")
                    st.rerun()
            with c2:
                if st.button("🔄 换个风格", use_container_width=True):
                    st.session_state["wizard_step"] = 4
                    st.rerun()
            with c3:
                if st.button("📝 重新开始", use_container_width=True):
                    for k in ["wizard_step", "wizard_product", "wizard_selling_points",
                              "wizard_pain_points", "wizard_purpose", "wizard_hook_style",
                              "wizard_result", "wizard_search_done"]:
                        st.session_state[k] = {"wizard_step": 1, "wizard_product": "", "wizard_selling_points": [],
                                               "wizard_pain_points": [], "wizard_purpose": "通用文案",
                                               "wizard_hook_style": "痛点直击", "wizard_result": "",
                                               "wizard_search_done": False}[k]
                    st.rerun()

    # ═══════════════════════════════════════════
    # PATH: 高级模式 (Advanced)
    # ═══════════════════════════════════════════
    elif creation_path == "高级模式":
        st.subheader("高级模式")

        # Handle redirect from 爆款拆解
        if st.session_state.get("imitate_analysis"):
            st.session_state["mode"] = "仿写爆款"

        if "mode" not in st.session_state:
            st.session_state["mode"] = "自由创作"

        gen_mode = st.radio("生成模式", ["自由创作", "仿写爆款", "改写润色", "组合生成"], horizontal=True, key="mode")

        col1, col2, col3 = st.columns(3)
        with col1: length = st.selectbox("长度", LENGTH_OPTIONS, index=1, key="adv_len")
        with col2: style = st.selectbox("风格", STYLE_OPTIONS, key="adv_style")
        with col3: purpose = st.selectbox("目的", PURPOSE_OPTIONS, key="adv_purp")

        st.divider()

        if gen_mode == "自由创作":
            topic = st.text_input("主题/关键词", placeholder="例如：如何提升执行力")
            render_preference_hits(topic, purpose, length_label=length)
            if st.button("✍️ 生成文案", type="primary", use_container_width=True):
                if not topic.strip():
                    st.warning("请输入主题")
                else:
                    with st.spinner("生成中..."):
                        result = generate_free(topic, length=length, style=style, purpose=purpose,
                                              content_format=hs("content_format"))
                        save_copy(f"{topic} - {gen_mode}", result, mode="free", length=length, style=style, purpose=purpose)
                        st.session_state["gen_result"] = result

        elif gen_mode == "仿写爆款":
            analyses = list_analyses()
            if not analyses:
                st.warning("还没有拆解记录，先去「爆款拆解」拆一条吧")
            else:
                im = lambda k: st.session_state[k]

                # Step 1: Select viral
                opts = {f"{a['title']} [{a.get('structure_type','')}]": a for a in analyses}
                sel = st.selectbox("Step 1: 选择要模仿的爆款", list(opts.keys()))
                selected = opts[sel]

                st.divider()

                # Step 2: Product + Sellpoints
                st.subheader("Step 2: 你要给什么产品写文案？")
                product = st.text_input(
                    "产品名称", value=im("imit_product"),
                    placeholder="例：加热棒、胶原蛋白饮",
                    key="imit_product_input"
                )
                st.session_state["imit_product"] = product
                render_preference_hits(product, "仿写爆款", length_label=length)

                sp_mode = st.radio(
                    "卖点来源",
                    ["帮我自动搜索（推荐）", "我自己填"],
                    horizontal=True,
                    index=0 if im("imit_sellpoint_mode") == "ai" else 1,
                    key="imit_sp_mode"
                )
                st.session_state["imit_sellpoint_mode"] = "ai" if "自动搜索" in sp_mode else "manual"

                if im("imit_sellpoint_mode") == "manual":
                    sp_count = max(3, len(im("imit_selling_points")) if im("imit_selling_points") else 3)
                    sps = []
                    for i in range(sp_count):
                        val = st.text_input(
                            f"卖点 {i+1}",
                            value=im("imit_selling_points")[i] if i < len(im("imit_selling_points")) else "",
                            key=f"imit_man_sp_{i}"
                        )
                        if val.strip():
                            sps.append(val.strip())
                    st.session_state["imit_selling_points"] = sps

                    pp_count = max(3, len(im("imit_pain_points")) if im("imit_pain_points") else 3)
                    pps = []
                    for i in range(pp_count):
                        val = st.text_input(
                            f"痛点 {i+1}",
                            value=im("imit_pain_points")[i] if i < len(im("imit_pain_points")) else "",
                            key=f"imit_man_pp_{i}"
                        )
                        if val.strip():
                            pps.append(val.strip())
                    st.session_state["imit_pain_points"] = pps
                else:
                    if st.button("🔍 搜索卖点和痛点", type="primary", use_container_width=True):
                        if not product.strip():
                            st.warning("请先输入产品名称")
                        else:
                            with st.spinner(f"正在搜索「{product}」..."):
                                result = search_selling_points(product)
                                st.session_state["imit_ai_sps"] = result.get("selling_points", [])
                                st.session_state["imit_ai_pps"] = result.get("pain_points", [])
                                for k in list(st.session_state.keys()):
                                    if k.startswith("imit_sel_sp_") or k.startswith("imit_sel_pp_"):
                                        del st.session_state[k]
                                st.session_state["imit_search_done"] = True
                                st.rerun()

                    if im("imit_search_done"):
                        if im("imit_ai_sps") or im("imit_ai_pps"):
                            st.success("搜索完成，勾选你要用的：")
                            st.write("**卖点：**")
                            for i, sp in enumerate(im("imit_ai_sps")):
                                st.checkbox(sp, value=True, key=f"imit_sel_sp_{i}")
                            st.write("**痛点：**")
                            for i, pp in enumerate(im("imit_ai_pps")):
                                st.checkbox(pp, value=True, key=f"imit_sel_pp_{i}")

                            selected_sps = [sp for i, sp in enumerate(im("imit_ai_sps"))
                                            if st.session_state.get(f"imit_sel_sp_{i}", True)]
                            selected_pps = [pp for i, pp in enumerate(im("imit_ai_pps"))
                                            if st.session_state.get(f"imit_sel_pp_{i}", True)]
                            st.session_state["imit_selling_points"] = selected_sps
                            st.session_state["imit_pain_points"] = selected_pps

                            if st.button("🔄 重新搜索"):
                                st.session_state["imit_search_done"] = False
                                st.rerun()
                        else:
                            st.warning("未搜到卖点信息，请尝试更具体的产品名称或手动填写")
                            if st.button("🔄 重新搜索"):
                                st.session_state["imit_search_done"] = False
                                st.rerun()

                st.divider()

                # Step 3: Generate
                if st.button("✍️ 开始仿写", type="primary", use_container_width=True):
                    if not product.strip():
                        st.warning("请先输入产品名称")
                    else:
                        analysis_json = json.loads(selected.get("analysis_json", "{}"))
                        with st.spinner("仿写中..."):
                            result = generate_imitate(
                                analysis_json=analysis_json,
                                original_text=selected.get("raw_text", ""),
                                product=product.strip(),
                                selling_points=im("imit_selling_points"),
                                pain_points=im("imit_pain_points"),
                                length=length,
                                style=style,
                                content_format=hs("content_format"),
                            )
                            st.session_state["imit_result"] = result
                            st.session_state["gen_result"] = result
                            save_copy(
                                title=f"仿写 {selected['title']} → {product}",
                                content=result,
                                mode="imitate",
                                length=length,
                                style=style,
                                product=product.strip(),
                                selling_points=im("imit_selling_points"),
                                pain_points=im("imit_pain_points")
                            )
                            st.rerun()

                if im("imit_result"):
                    st.divider()
                    st.subheader("生成结果")
                    st.text_area("文案", im("imit_result"), height=400, key="imit_result_display", label_visibility="collapsed")
                    st.caption("按 Ctrl+A 全选后 Ctrl+C 复制")

        elif gen_mode == "改写润色":
            draft = st.text_area("粘贴你的文案草稿", height=200, placeholder="粘贴你需要优化的文案...")
            render_preference_hits(draft[:80], "改写润色", length_label=length)
            if st.button("✍️ 改写优化", type="primary", use_container_width=True):
                if not draft.strip():
                    st.warning("请粘贴文案")
                else:
                    with st.spinner("改写中..."):
                        result = generate_rewrite(draft, length=length, style=style,
                                                 content_format=hs("content_format"))
                        save_copy(f"改写 {draft[:30]}...", result, mode="rewrite", length=length, style=style)
                        st.session_state["gen_result"] = result

        elif gen_mode == "组合生成":
            analyses = list_analyses()
            if len(analyses) < 3:
                st.warning("需要至少 3 条拆解记录才能使用组合模式")
            else:
                opts = {f"{a['title']} [{a.get('structure_type','')}]": a for a in analyses}
                k = list(opts.keys())
                hook_key = st.selectbox("钩子参考", k, key="hook")
                body_key = st.selectbox("展开逻辑参考", k, key="body")
                ending_key = st.selectbox("收尾参考", k, key="ending")
                topic = st.text_input("主题（可选）", placeholder="输入主题或留空")
                render_preference_hits(topic, "组合生成", length_label=length)
                if st.button("✍️ 组合生成", type="primary", use_container_width=True):
                    ha = json.loads(opts[hook_key].get("analysis_json", "{}"))
                    ba = json.loads(opts[body_key].get("analysis_json", "{}"))
                    ea = json.loads(opts[ending_key].get("analysis_json", "{}"))
                    with st.spinner("组合生成中..."):
                        result = generate_combine(ha, ba, ea, topic=topic.strip(), length=length, style=style,
                                                  content_format=hs("content_format"))
                        save_copy(f"组合 {topic or '未命名'}", result, mode="combine", length=length, style=style)
                        st.session_state["gen_result"] = result

        if "gen_result" in st.session_state:
            st.divider()
            st.subheader("生成结果")
            st.text_area("文案", st.session_state["gen_result"], height=400, key="result_display", label_visibility="collapsed")
            st.caption("按 Ctrl+A 全选后 Ctrl+C 复制")

        # Clear redirect flag after rendering
        if st.session_state.get("imitate_analysis"):
            del st.session_state["imitate_analysis"]

    # ── Shared Bottom: Scheduler & Auto-Gen Settings ──
    st.divider()

    with st.expander("⏰ 定时生成配置", expanded=False):
        hour, minute = get_schedule_time()
        c1, c2, c3 = st.columns(3)
        with c1: nh = st.number_input("小时", 0, 23, hour)
        with c2: nm = st.number_input("分钟", 0, 59, minute)
        with c3:
            st.caption(""); st.caption("")
            if st.button("保存时间"):
                set_schedule_time(nh, nm)
                st.success(f"已设为每天 {nh:02d}:{nm:02d}")
        nr = get_next_run_time()
        if nr: st.info(f"下次执行: {nr.strftime('%Y-%m-%d %H:%M:%S')}")

    with st.expander("📝 自动生成默认参数", expanded=False):
        auto_topic = st.text_input("默认主题", value=get_setting("auto_topic", "通用"))
        auto_count = st.number_input("每日生成数量", 1, 10, int(get_setting("auto_count", "3")))
        auto_length = st.selectbox("默认长度", LENGTH_OPTIONS,
                                   index=LENGTH_OPTIONS.index(get_setting("auto_length", "60秒")) if get_setting("auto_length", "60秒") in LENGTH_OPTIONS else 1)
        auto_style = st.selectbox("默认风格", STYLE_OPTIONS,
                                  index=STYLE_OPTIONS.index(get_setting("auto_style", "口语化")) if get_setting("auto_style", "口语化") in STYLE_OPTIONS else 0)
        auto_purpose = st.selectbox("默认目的", PURPOSE_OPTIONS,
                                    index=PURPOSE_OPTIONS.index(get_setting("auto_purpose", "涨粉")) if get_setting("auto_purpose", "涨粉") in PURPOSE_OPTIONS else 0)
        auto_content_format = st.selectbox("默认内容形式", CONTENT_FORMAT_OPTIONS,
                                           index=CONTENT_FORMAT_OPTIONS.index(get_setting("auto_content_format", "单人口播")) if get_setting("auto_content_format", "单人口播") in CONTENT_FORMAT_OPTIONS else 0)
        if st.button("💾 保存默认参数"):
            set_setting("auto_topic", auto_topic)
            set_setting("auto_count", str(auto_count))
            set_setting("auto_length", auto_length)
            set_setting("auto_style", auto_style)
            set_setting("auto_purpose", auto_purpose)
            set_setting("auto_content_format", auto_content_format)
            st.success("已保存")

# ═══════════════════ TAB: 历史记录 ═══════════════════
elif tab == "📋 历史记录":
    st.title("历史记录")
    fs = st.selectbox("筛选状态", ["全部", "待拍", "已拍", "已发"], key="hist_filter")
    smap = {"全部": None, "待拍": "draft", "已拍": "shot", "已发": "published"}
    copies = list_copies(limit=100, status=smap[fs])

    if not copies:
        st.info("暂无记录")
    else:
        st.write(f"共 {len(copies)} 条")
        for c in copies:
            rating = c.get("rating", 0) or 0
            sl = {"draft": "📝待拍", "shot": "🎬已拍", "published": "✅已发"}.get(c.get("status", ""), "")
            with st.expander(f"{c['title']} {sl} {'⭐'*rating} [{c.get('mode','')}] [{c.get('created_at','')[:16]}]"):
                st.text_area("内容", c["content"], height=150, key=f"hcopy_{c['id']}", label_visibility="collapsed")
                c1, c2, c3 = st.columns(3)
                with c1:
                    r = st.select_slider("评分", options=[0,1,2,3,4,5], value=rating, key=f"rate_{c['id']}")
                    if r != rating:
                        update_copy_rating(c["id"], r); st.rerun()
                with c2:
                    cur = c.get("status", "draft")
                    ns = st.selectbox("状态", ["draft","shot","published"],
                                      index=["draft","shot","published"].index(cur) if cur in ["draft","shot","published"] else 0,
                                      format_func=lambda x: {"draft":"待拍","shot":"已拍","published":"已发"}[x],
                                      key=f"hs_{c['id']}")
                    if ns != cur:
                        update_copy_status(c["id"], ns); st.rerun()
                with c3:
                    if st.button("🗑️", key=f"hd_{c['id']}"):
                        delete_copy(c["id"]); st.rerun()
                render_feedback_form(c, "hist")

# ═══════════════════ TAB: 偏好记忆 ═══════════════════
elif tab == "🧠 偏好记忆":
    st.title("偏好记忆")
    st.caption("这里保存你上传修改稿后沉淀出来的写作偏好。生成新文案时，系统会自动检索相关规则。")

    status_filter = st.selectbox("状态", ["active", "paused"], format_func=lambda x: {"active": "启用中", "paused": "已停用"}[x])
    rules = list_preference_rules(limit=200, status=status_filter)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("当前规则", len(rules))
    with c2:
        st.metric("应该这样写", sum(1 for r in rules if r.get("rule_type") == "prefer"))
    with c3:
        st.metric("不要这样写", sum(1 for r in rules if r.get("rule_type") == "avoid"))

    st.divider()

    if not rules:
        st.info("还没有偏好记忆。去「历史记录」里给一条文案上传修改稿后，这里就会出现规则。")
    else:
        for r in rules:
            label = "应该" if r.get("rule_type") == "prefer" else "避免"
            with st.expander(f"{label}：{r.get('rule_text', '')}"):
                st.write(f"**产品：** {r.get('product') or '通用'}")
                st.write(f"**场景：** {r.get('video_type') or '通用'}")
                st.write(f"**可信度：** {r.get('confidence', 0)}")
                st.caption(f"创建时间：{r.get('created_at', '')}")
                next_status = "paused" if status_filter == "active" else "active"
                btn_label = "停用这条记忆" if status_filter == "active" else "重新启用"
                if st.button(btn_label, key=f"rule_status_{r['id']}"):
                    update_preference_rule_status(r["id"], next_status)
                    st.rerun()

    st.divider()
    st.subheader("最近反馈")
    feedbacks = list_copy_feedback(limit=20)
    if not feedbacks:
        st.caption("暂无反馈记录")
    else:
        for fb in feedbacks:
            with st.expander(f"{fb.get('created_at', '')[:16]} · {fb.get('rating', '')} · 文案 #{fb.get('copy_id')}"):
                reasons = _json_list(fb.get("reason_tags"))
                if reasons:
                    st.write("原因：", "、".join(reasons))
                if fb.get("note"):
                    st.write("说明：", fb["note"])
                if fb.get("final_content"):
                    st.text_area("最终稿", fb["final_content"], height=120, key=f"fb_final_{fb['id']}", label_visibility="collapsed")
                try:
                    analysis = json.loads(fb.get("analysis_json") or "{}")
                except Exception:
                    analysis = {}
                if analysis:
                    st.json(analysis)

# ═══════════════════ TAB: 设置 ═══════════════════
elif tab == "⚙️ 设置":
    st.title("设置")

    st.subheader("🔑 DeepSeek API")
    api_key = st.text_input("API Key", value="sk-...", type="password",
                            help="在 https://platform.deepseek.com 获取")
    if st.button("💾 保存 API Key"):
        import config as cfg
        cfg.DEEPSEEK_API_KEY = api_key
        set_setting("deepseek_api_key", api_key)
        reset_client()
        st.success("已保存（本次会话生效）")

    st.divider()
    st.subheader("🔎 热点搜索")
    bing_key = st.text_input(
        "Bing Search API Key（可选）",
        value=get_setting("bing_search_api_key", ""),
        type="password",
        help="不填也可以使用免 Key 搜索兜底；填写后热点结果会更稳定。"
    )
    if st.button("💾 保存搜索配置"):
        set_setting("bing_search_api_key", bing_key)
        if bing_key:
            os.environ["BING_SEARCH_API_KEY"] = bing_key
        st.success("已保存搜索配置")

    nr = get_next_run_time()
    st.divider()
    st.subheader("🖥️ 系统信息")
    st.json({
        "调度器": "🟢 运行中" if is_scheduler_running() else "🔴 已停止",
        "下次执行": str(nr) if nr else "无",
        "知识库": get_collection_stats(),
        "模型": DEEPSEEK_MODEL
    })

st.sidebar.divider()
st.sidebar.caption(f"调度器: {'🟢 运行中' if is_scheduler_running() else '🔴 已停止'}")
if get_next_run_time():
    st.sidebar.caption(f"下次生成: {get_next_run_time().strftime('%m/%d %H:%M')}")
