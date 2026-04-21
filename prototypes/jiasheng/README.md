# Jiasheng — prototype

This prototype explores an end-to-end planning flow where a student enters their major, pastes a transcript (or course list), and the app searches a demo “current term” offering list to produce a ranked, explainable shortlist (separating teaching quality from workload/difficulty via adjustable weights).

Compared to teammates’ approaches that lean more on static browsing or manual filtering, this direction emphasizes transcript-driven eligibility/prereq matching, automated ranking, and transparent tradeoffs (why a course is recommended, what risks/uncertainties exist, and what alternatives look like).

Path: `course-planner/prototypes/jiasheng/`

## 技术栈（满足课程要求）

- **Front end**: Web UI（Jinja2 模板 + 少量 JS），含 **落地介绍页**（`/`）与试用页（`/app`）
- **Back end**: FastAPI（`app/main.py`）
- **Database**: SQLite + SQLAlchemy（默认写入 `data/app.db`）
- **AI API**（二选一或都配）：
  - **Gemini**：Google Generative Language API（`generateContent` + JSON MIME type），用于成绩单结构化解析 + 推荐解释增强
  - **OpenAI**：Chat Completions（JSON 模式），同上
  - 未配置任何 key / 或 `AI_PROVIDER=none`：自动降级为规则解析 + 占位解释（保证展示可用）

### 选择用 Gemini（推荐你现在的方向）

在运行 `uvicorn` 的终端里设置（示例）：

```bash
export GEMINI_API_KEY="你的key"
export AI_PROVIDER="gemini"   # 或 auto（auto 会优先走 Gemini）
# 可选：换模型（以 Google AI Studio 里可用的为准）
# export GEMINI_MODEL="gemini-2.0-flash"
```

> 说明：**仍然需要“接 API”**，但 key 应该只放在**后端环境变量**里，由服务器调用；不要写进前端页面或提交到 Git。

## 本地运行（课堂展示：works on your laptop）

在目录 `course-planner/prototypes/jiasheng/` 下：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 可选：避免某些 macOS 环境下 Python 写入系统缓存目录失败
export PYTHONPYCACHEPREFIX="$(pwd)/.pycache_dir"

# 可选：启用 AI（复制 .env.example 为 .env 自行填写）
# export $(grep -v '^#' .env | xargs)

python -m uvicorn app.main:app --reload --port 8010
```

### 一键启动（推荐，避免在错误目录运行）

在目录 `course-planner/prototypes/jiasheng/` 下：

```bash
./run_dev.sh
```

如需换端口：

```bash
PORT=8011 ./run_dev.sh
```

打开浏览器访问：

- `v`（介绍页：是什么 / 给谁 / 解决什么 / 怎么用）
- `http://127.0.0.1:8010/app`（试用页）

## API（便于你现场演示）

- `POST /api/plan`：生成推荐并写入数据库
- `GET /api/session/{id}`：读取历史会话与推荐

