# ✍️ CopyAgent — AI 短视频文案智能体

CopyAgent 是一个为短视频创作者打造的 **AI 文案创作工作台**。它不是简单的「输入关键词→出文案」工具，而是覆盖**热点选题 → 爆款拆解 → 多模式文案生成 → 用户偏好学习 → 定时自动化**的完整创作闭环。

基于 DeepSeek API，配合本地 RAG 知识库，所有文案遵循你的课程方法论。Streamlit 构建，本地运行，数据不外泄。

---

## 核心能力

### 🔥 热点选题（置顶入口，三重创作路径）

| 路径 | 说明 |
|------|------|
| **热点驱动** | 输入产品 → 自动搜索近期热点 → AI 分析趋势/痛点/场景 → 生成 10-20 个选题 → 选中后生成完整口播文案 |
| **向导模式** | 4 步渐进式引导：产品 → 卖点/痛点 → 视频用途 → 开头风格 → 生成，零 Prompt 基础也能写出专业文案 |
| **高级模式** | 自由创作 / 仿写爆款 / 改写润色 / 组合生成，四种模式满足不同创作需求 |

### 🎬 内容形式定制（8 种）

| 单人口播 | 剧情演绎 | 测评对比 | Vlog分享 | 干货讲解 | 对话访谈 | 开箱体验 | 场景种草 |
|----------|----------|----------|----------|----------|----------|----------|----------|

AI 会根据你选中的内容形式自动调整脚本结构——剧情演绎生成角色对话、测评对比输出对比框架、Vlog 分享用第一人称生活化口吻。

### 📚 课程知识库（RAG）

上传你的课程文档（md / txt / docx / pdf），系统自动分块、向量化入库。每次生成文案时，从知识库检索相关内容注入 Prompt，确保文案风格和方法论与你的一致。

### 🔍 爆款拆解

粘贴竞品或同赛道的爆款文案 → AI 自动分析：

- **结构模型**：SCQA / AIDA / 钩子-展开-高潮-收尾 等
- **钩子类型**：反常识 / 数据 / 悬念 / 痛点直击 / 故事开头
- **情绪曲线**：逐句情感标注和强度
- **金句提取**：可复用的高价值表达
- **节奏特点**：句长分布、转折频率

拆解结果自动入库，可在仿写模式中直接引用作为结构模板。

### 🧠 偏好记忆与迭代学习

每条生成的文案都可以提交反馈：
- 上传你拍摄前实际使用的最终修改稿
- AI 对比原稿和修改稿，自动分析你改了什么、为什么改
- 沉淀为「应该这样做」和「避免这样做」的结构化规则
- 下次同类生成时，规则自动注入 Prompt，越用越像你的风格

### ⏰ 定时自动化

设置每天定时（如早 7:00），系统自动生成当日文案。支持配置默认主题、数量、长度、风格、用途、内容形式。上班前文案已就位，打开即可拍摄。

---

## 快速开始

### 1. 克隆代码

```bash
git clone https://github.com/dsfrdh/copyagent.git
cd copyagent/copyagent
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

网络慢可用清华镜像：
```bash
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

### 3. 配置 API Key

在应用的「⚙️ 设置 → API Key」页面填入你的 DeepSeek API Key，或者在启动前设置环境变量：

```bash
# Windows (PowerShell)
$env:DEEPSEEK_API_KEY="sk-你的key"

# Mac / Linux
export DEEPSEEK_API_KEY=sk-你的key
```

> 获取 Key：[platform.deepseek.com](https://platform.deepseek.com)

### 4. 启动

```bash
python -m streamlit run app.py
```

浏览器打开 [http://localhost:8501](http://localhost:8501)

---

## 推荐使用流程

```
1. 📚 知识库 — 上传你的课程/方法论文档
2. 🔍 爆款拆解 — 拆几条同赛道爆款，建立拆解库
3. 🔥 热点选题 — 日常创作入口，选择创作路径
   - 追热点 → 热点驱动
   - 系统写 → 向导模式  
   - 仿爆款 → 高级模式
4. 🧠 偏好记忆 — 拍摄前改了文案？上传修改稿让 AI 学习
5. ⏰ 设置定时 → 每天自动产出，打开即用
```

---

## 项目结构

```
copyagent/
├── app.py                    # Streamlit UI 主入口
├── config.py                 # 全局配置
├── scheduler.py              # APScheduler 定时任务
├── analyzer/
│   └── viral.py              # 爆款拆解 Prompt 与逻辑
├── generator/
│   ├── copywriter.py         # 5 种文案生成模式 + 卖点搜索
│   └── feedback.py           # 用户修改稿差异分析与偏好规则提取
├── hotspot/
│   ├── service.py            # 热点发现 → 选题生成 → 文案生成
│   └── providers.py          # 搜索提供者（Bing + DuckDuckGo 复合）
├── knowledge/
│   ├── loader.py             # 文档加载（md/txt/docx/pdf）
│   ├── chunker.py            # 文本分块
│   └── retriever.py          # 向量检索（ChromaDB）
└── utils/
    └── db.py                 # SQLite 数据层 + 偏好记忆引擎
```

---

## 技术栈

| 层 | 选型 |
|---|---|
| UI 框架 | Streamlit |
| AI 模型 | DeepSeek (deepseek-chat) |
| 向量检索 | ChromaDB + sentence-transformers |
| 元数据存储 | SQLite |
| 定时任务 | APScheduler |
| 文档解析 | python-docx / PyPDF2 / markdown |
| 搜索增强 | Bing Search API + DuckDuckGo |

---

## License

MIT
