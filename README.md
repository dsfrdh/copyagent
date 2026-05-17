# CopyAgent - AI 文案智能体

4 步向导式短视频口播文案生成器，基于 DeepSeek API。

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

如果网络慢，用清华镜像：
```bash
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

### 3. 设置 API Key

```bash
# Windows (CMD)
set DEEPSEEK_API_KEY=sk-你的key

# Windows (PowerShell)
$env:DEEPSEEK_API_KEY="sk-你的key"

# Mac / Linux
export DEEPSEEK_API_KEY=sk-你的key
```

或者在应用内的 ⚙️ 设置 → API Key 填入。

### 4. 启动

```bash
python -m streamlit run app.py
```

浏览器打开 http://localhost:8501

## 更新代码

每次开始工作前：

```bash
git pull
```

改了代码想同步到另一台电脑：

```bash
git add .
git commit -m "描述你改了什么"
git push
```

## 功能

| 模块 | 说明 |
|------|------|
| 🏠 首页 | 今日文案总览，一键生成，状态管理 |
| 📚 知识库 | 上传课程文档，自动分块入库 |
| 🔍 爆款拆解 | 粘贴文案 → AI 分析结构/钩子/情绪/金句 |
| ✍️ 文案向导 | 4 步引导：产品 → 卖点 → 用途 → 开头 → 生成 |
| 📋 历史 | 文案管理、评分、搜索 |
| ⚙️ 设置 | API Key、定时生成、话题库 |

## 项目结构

```
copyagent/
├── app.py              # Streamlit UI
├── config.py           # 配置
├── scheduler.py        # 定时任务
├── analyzer/viral.py   # 爆款拆解
├── generator/copywriter.py  # 文案生成
├── knowledge/          # 知识库（文档加载/分块/检索）
└── utils/db.py         # SQLite 数据层
```
