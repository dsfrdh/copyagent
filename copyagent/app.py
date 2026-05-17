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
    delete_copy, get_setting, set_setting, get_recent_products
)
from knowledge.loader import load_file
from knowledge.chunker import split_chunks
from knowledge.retriever import add_chunks, remove_doc_chunks, get_collection_stats
from analyzer.viral import deconstruct
from generator.copywriter import (
    generate_free, generate_imitate, generate_rewrite, generate_combine,
    generate_wizard, search_selling_points
)
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

if not is_scheduler_running():
    start_scheduler()

st.sidebar.title("✍️ CopyAgent")
st.sidebar.caption(f"模型: {DEEPSEEK_MODEL}")

tab = st.sidebar.radio(
    "导航",
    ["🏠 首页", "📚 知识库", "🔍 爆款拆解", "✍️ 文案生成", "📋 历史记录", "⚙️ 设置"]
)

LENGTH_OPTIONS = ["30秒", "60秒", "90秒"]
STYLE_OPTIONS = ["口语化", "情绪化", "专业感", "幽默"]
PURPOSE_OPTIONS = ["涨粉", "引流", "成交", "种草", "品牌"]

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
                st.session_state["tab_redirect"] = "✍️ 文案生成"

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

# ═══════════════════ TAB: 文案生成 ═══════════════════
elif tab == "✍️ 文案生成":
    st.title("文案向导")

    # Toggle: wizard vs advanced
    show_advanced = st.session_state.get("show_advanced", False)
    toggle_label = "🔙 回到向导模式" if show_advanced else "🔧 切换到高级模式"
    if st.button(toggle_label, key="toggle_mode"):
        st.session_state["show_advanced"] = not show_advanced
        st.rerun()

    if show_advanced:
        # ── Advanced Mode (original 4 modes) ──
        st.subheader("高级模式")

        if st.session_state.get("tab_redirect"):
            st.session_state["mode"] = "仿写爆款"
            del st.session_state["tab_redirect"]

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
            if st.button("✍️ 生成文案", type="primary", use_container_width=True):
                if not topic.strip():
                    st.warning("请输入主题")
                else:
                    with st.spinner("生成中..."):
                        result = generate_free(topic, length=length, style=style, purpose=purpose)
                        save_copy(f"{topic} - {gen_mode}", result, mode="free", length=length, style=style, purpose=purpose)
                        st.session_state["gen_result"] = result

        elif gen_mode == "仿写爆款":
            analyses = list_analyses()
            if not analyses:
                st.warning("还没有拆解记录，先去「爆款拆解」拆一条吧")
            else:
                opts = {f"{a['title']} [{a.get('structure_type','')}]": a for a in analyses}
                sel = st.selectbox("选择要模仿的爆款", list(opts.keys()))
                topic = st.text_input("主题（可选）", placeholder="输入主题或留空")
                if st.button("✍️ 仿写", type="primary", use_container_width=True):
                    analysis_json = json.loads(opts[sel].get("analysis_json", "{}"))
                    with st.spinner("仿写中..."):
                        result = generate_imitate(analysis_json, topic=topic.strip(), length=length, style=style)
                        save_copy(f"仿写 {opts[sel]['title']}", result, mode="imitate", length=length, style=style)
                        st.session_state["gen_result"] = result

        elif gen_mode == "改写润色":
            draft = st.text_area("粘贴你的文案草稿", height=200, placeholder="粘贴你需要优化的文案...")
            if st.button("✍️ 改写优化", type="primary", use_container_width=True):
                if not draft.strip():
                    st.warning("请粘贴文案")
                else:
                    with st.spinner("改写中..."):
                        result = generate_rewrite(draft, length=length, style=style)
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
                if st.button("✍️ 组合生成", type="primary", use_container_width=True):
                    ha = json.loads(opts[hook_key].get("analysis_json", "{}"))
                    ba = json.loads(opts[body_key].get("analysis_json", "{}"))
                    ea = json.loads(opts[ending_key].get("analysis_json", "{}"))
                    with st.spinner("组合生成中..."):
                        result = generate_combine(ha, ba, ea, topic=topic.strip(), length=length, style=style)
                        save_copy(f"组合 {topic or '未命名'}", result, mode="combine", length=length, style=style)
                        st.session_state["gen_result"] = result

        if "gen_result" in st.session_state:
            st.divider()
            st.subheader("生成结果")
            st.text_area("文案", st.session_state["gen_result"], height=400, key="result_display", label_visibility="collapsed")
            st.caption("按 Ctrl+A 全选后 Ctrl+C 复制")

    else:
        # ── Wizard Mode ──
        # Init session state
        for key, default in [
            ("wizard_step", 1), ("wizard_product", ""), ("wizard_selling_points", []),
            ("wizard_pain_points", []), ("wizard_sellpoint_mode", "manual"),
            ("wizard_purpose", "通用文案"), ("wizard_hook_style", "痛点直击"),
            ("wizard_length", "60秒"), ("wizard_style", "口语化"),
            ("wizard_result", ""), ("wizard_search_done", False)
        ]:
            if key not in st.session_state:
                st.session_state[key] = default

        ws = lambda k: st.session_state[k]

        # ── Progress bar ──
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

        # ═══════════ STEP 1: Product ═══════════
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
                        # Reset sellpoint search state
                        st.session_state["wizard_search_done"] = False
                        st.session_state["wizard_sellpoint_mode"] = "manual"
                        st.session_state["wizard_selling_points"] = []
                        st.session_state["wizard_pain_points"] = []
                        st.session_state["wizard_step"] = 2
                        st.rerun()

        # ═══════════ STEP 2: Selling Points ═══════════
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
                # Allow skip
                if st.button("跳过 →", use_container_width=True):
                    st.session_state["wizard_step"] = 3
                    st.rerun()
            st.caption("不填也没关系，AI 会基于产品名自动发挥。点「跳过」直接进入下一步。")

            c1, c2 = st.columns([1, 4])
            with c1:
                if st.button("下一步 →", type="primary", use_container_width=True):
                    st.session_state["wizard_step"] = 3
                    st.rerun()

        # ═══════════ STEP 3: Purpose ═══════════
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

        # ═══════════ STEP 4: Hook Style ═══════════
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

            # Length & Style
            c1, c2 = st.columns(2)
            with c1:
                length = st.selectbox("文案长度", LENGTH_OPTIONS, index=1, key="wiz_len")
                st.session_state["wizard_length"] = length
            with c2:
                style = st.selectbox("文案风格", STYLE_OPTIONS, key="wiz_style")
                st.session_state["wizard_style"] = style

            st.divider()

            # Summary before generate
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
                            style=ws("wizard_style")
                        )
                        st.session_state["wizard_result"] = result
                        st.session_state["wizard_step"] = 5
                        st.rerun()

        # ═══════════ STEP 5: Result ═══════════
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
        st.success("已保存（本次会话生效）")

    st.divider()
    st.subheader("⏰ 定时生成")
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

    st.divider()
    st.subheader("📝 自动生成默认参数")
    auto_topic = st.text_input("默认主题", value=get_setting("auto_topic", "通用"))
    auto_count = st.number_input("每日生成数量", 1, 10, int(get_setting("auto_count", "3")))
    auto_length = st.selectbox("默认长度", LENGTH_OPTIONS,
                               index=LENGTH_OPTIONS.index(get_setting("auto_length", "60秒")) if get_setting("auto_length", "60秒") in LENGTH_OPTIONS else 1)
    auto_style = st.selectbox("默认风格", STYLE_OPTIONS,
                              index=STYLE_OPTIONS.index(get_setting("auto_style", "口语化")) if get_setting("auto_style", "口语化") in STYLE_OPTIONS else 0)
    auto_purpose = st.selectbox("默认目的", PURPOSE_OPTIONS,
                                index=PURPOSE_OPTIONS.index(get_setting("auto_purpose", "涨粉")) if get_setting("auto_purpose", "涨粉") in PURPOSE_OPTIONS else 0)
    if st.button("💾 保存默认参数"):
        set_setting("auto_topic", auto_topic)
        set_setting("auto_count", str(auto_count))
        set_setting("auto_length", auto_length)
        set_setting("auto_style", auto_style)
        set_setting("auto_purpose", auto_purpose)
        st.success("已保存")

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
