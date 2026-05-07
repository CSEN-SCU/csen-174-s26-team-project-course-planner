# SCU Course Planner — `project/course_planner/`

**完整产品说明、架构、环境变量、测试命令与 lecture/lab 规则**与仓库根目录 **[`README.md`](../../README.md)** 保持一致；请先阅读根目录 README。

下面仅为在本目录开发时的**最短上手**。

---

## Quick start

```bash
cd project/course_planner
pip install -r requirements.txt
cp .env.example .env   # GEMINI_API_KEY or GOOGLE_API_KEY
streamlit run main.py
```

测试（在 `project/course_planner/` 下执行）：

```bash
../../.venv/bin/python -m pytest tests/
```

---

## Team

Jason · Ismael · Joey · Jiasheng
