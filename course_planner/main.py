from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

import streamlit as st

from utils.academic_progress_xlsx import parse_academic_progress_xlsx

st.set_page_config(page_title="SCU Course Planner", layout="wide")

st.title("SCU Course Planner")

COL_ZH = {
    "requirement": "要求 / 条目",
    "status": "状态",
    "remaining": "尚缺说明",
    "registration": "登记课程",
    "course_code": "解析课号",
    "academic_period": "学期",
    "units": "学分",
    "grade": "成绩",
}

with st.sidebar:
    st.markdown("上传 **SCU → View My Academic Progress** 导出的 `.xlsx`（本地解析，无需调用 API）。")
    xlsx_file = st.file_uploader("上传 Academic Progress (.xlsx)", type=["xlsx"])
    hide_empty = st.checkbox("明细表隐藏「仅有状态、未登记课程」的空行", value=False)
    run = st.button("解析")


def _detail_table_rows(rows: list[dict]) -> list[dict]:
    return [{COL_ZH.get(k, k): row.get(k) for k in COL_ZH if k in row} for row in rows]


def _not_satisfied_table(items: list[dict]) -> list[dict]:
    return [
        {
            "要求 / 条目": i.get("requirement"),
            "尚缺说明": i.get("remaining"),
        }
        for i in items
    ]


if run:
    if not xlsx_file:
        st.warning("请先上传 xlsx。")
    else:
        data = parse_academic_progress_xlsx(xlsx_file.getvalue())
        counts = data.get("requirement_status_counts", {})

        st.subheader("进度总览（按「一整条 DegreeWorks 要求」合并状态）")
        c1, c2, c3 = st.columns(3)
        c1.metric("已满足条目数", counts.get("Satisfied", 0))
        c2.metric("进行中条目数", counts.get("In Progress", 0))
        c3.metric("未满足条目数", counts.get("Not Satisfied", 0))

        st.subheader("仍未满足的要求")
        ns = data.get("not_satisfied", [])
        if ns:
            st.dataframe(_not_satisfied_table(ns), use_container_width=True, hide_index=True)
        else:
            st.success("当前没有发现状态为「Not Satisfied」的要求块（以 Excel 为准）。")

        st.subheader("表中解析出的课程课号（去重）")
        codes = data.get("course_codes", [])
        st.write(", ".join(codes) if codes else "（无可解析课号的登记行）")

        st.subheader("全部明细（与 Excel 行一致）")
        detail = list(data.get("detail_rows", []))
        if hide_empty:
            detail = [r for r in detail if r.get("registration")]
        if detail:
            st.dataframe(_detail_table_rows(detail), use_container_width=True, hide_index=True)
        else:
            st.info("明细为空 — 可能是表头不匹配或档案格式有变。")
