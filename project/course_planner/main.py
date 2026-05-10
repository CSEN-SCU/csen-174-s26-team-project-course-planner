import json
import re
from pathlib import Path
from dotenv import load_dotenv
from openpyxl import load_workbook

load_dotenv(Path(__file__).resolve().parent / ".env")

import streamlit as st

from utils.academic_progress_xlsx import parse_academic_progress_xlsx
from utils.meeting_pattern_parse import parse_schedule
from utils.rmp_display import professors_sorted_by_rating
from utils.scu_theme import inject_scu_brand
from utils.scu_course_schedule_xlsx import (
    _parse_section_subject_number,
    expand_subjects_for_schedule_lookup,
)
from agents.professor_agent import run_professor_agent
from agents.orchestrator import plan_for_user
from agents.requirement_agent import run_requirement_agent
from agents import memory_agent
from auth import streamlit_auth

st.set_page_config(page_title="SCU Course Planner", layout="wide")
inject_scu_brand()

current_user = streamlit_auth.require_login()
if current_user is None:
    st.stop()
USER_ID = int(current_user["id"])


def _schedule_map_keys_for_row(subject: str, number: str) -> list[str]:
    """Course-code keys aligned with the schedule xlsx, with COEN/CSEN and ECEN/ELEN cross-mapping."""
    subj = subject.strip().upper()
    num = number.strip()
    primary = f"{subj} {num}"
    keys = [primary]
    if subj == "COEN":
        keys.append(f"CSEN {num}")
    elif subj == "CSEN":
        keys.append(f"COEN {num}")
    elif subj == "ECEN":
        keys.append(f"ELEN {num}")
    elif subj == "ELEN":
        keys.append(f"ECEN {num}")
    return keys


def _load_schedule_map_base_from_xlsx() -> dict[str, str]:
    """Build course code -> Meeting Patterns from Find Course Sections xlsx only (no enriched overrides)."""
    base = Path(__file__).resolve().parent
    out: dict[str, str] = {}
    for fname in ("SCU_Find_Course_Sections.xlsx", "scu_find_course.xlsx"):
        p = base / fname
        if not p.is_file():
            continue
        wb = load_workbook(p, read_only=True, data_only=True)
        try:
            ws = wb.active
            it = ws.iter_rows(values_only=True)
            header = next(it, None)
            if not header:
                return out
            h = [str(c).strip() if c is not None else "" for c in header]
            try:
                idx_sec = h.index("Course Section")
                idx_mp = h.index("Meeting Patterns")
            except ValueError:
                return out
            for row in it:
                if not row or max(idx_sec, idx_mp) >= len(row):
                    continue
                sec = row[idx_sec]
                mp = row[idx_mp]
                if mp is None:
                    continue
                mp_s = str(mp).strip()
                if not mp_s:
                    continue
                parsed = _parse_section_subject_number(
                    str(sec).strip() if sec is not None else None
                )
                if not parsed:
                    continue
                subj_s, num_s = parsed[0], parsed[1]
                for k in _schedule_map_keys_for_row(subj_s, num_s):
                    if k not in out:
                        out[k] = mp_s
        finally:
            wb.close()
        break
    return out


def extract_course_variants(course_str: str) -> list[str]:
    """
    Input: "CSEN/COEN 194/L", "COEN 146", "ECEN/ELEN 153 & 153L", or "ENGL103"
    Output: all plausible course-code variants
    Example: ["CSEN 194", "COEN 194", "CSEN 194L", "COEN 194L"]
    """
    s = " ".join((course_str or "").split())
    if not s:
        return []
    if " " not in s and "/" not in s and "&" not in s:
        m = re.fullmatch(r"([A-Za-z]{2,8})(\d+[A-Za-z]?)", s, re.I)
        if m:
            s = f"{m.group(1).upper()} {m.group(2).upper()}"
    parts = s.split()
    subjects = expand_subjects_for_schedule_lookup(parts[0].split("/"))
    rest = " ".join(parts[1:])
    numbers = []
    for token in re.split(r"[/&,]", rest):
        token = token.strip()
        if token:
            if token.isalpha() and numbers:
                numbers.append(numbers[-1] + token)
            else:
                numbers.append(token)
    variants = []
    for subj in subjects:
        for num in numbers:
            variants.append(f"{subj} {num}".strip())
    return variants


def _recommended_item_in_find_course_xlsx(item: dict, base_map: dict[str, str]) -> bool:
    """True if the recommendation matches at least one parseable section in Find Course Sections (variant keys)."""
    if not base_map:
        return True
    course_str = (item.get("course") or "").strip()
    if not course_str:
        return False
    variants = extract_course_variants(course_str)
    for v in variants:
        if " ".join(v.split()).upper() in base_map:
            return True
    return False


def load_course_schedule_map_from_xlsx() -> dict[str, str]:
    """Load Find Course Sections xlsx and build course-code string -> raw Meeting Patterns."""
    out = dict(_load_schedule_map_base_from_xlsx())

    enriched = st.session_state.get("enriched_courses")
    if isinstance(enriched, list):
        for item in enriched:
            course_str = item.get("course") or ""
            if not course_str:
                continue
            variants = extract_course_variants(course_str)
            if not variants:
                continue
            sched = None
            for v in variants:
                key = " ".join(v.split()).upper()
                if key in out:
                    sched = out[key]
                    break
            if sched is None:
                continue
            for v in variants:
                key = " ".join(v.split()).upper()
                out[key] = sched
            out[" ".join(course_str.split())] = sched

    return out


st.title("SCU Course Planner")

COL_LABELS = {
    "requirement": "Requirement / item",
    "status": "Status",
    "remaining": "Remaining (gap)",
    "registration": "Registered course",
    "course_code": "Parsed course code",
    "academic_period": "Term",
    "units": "Units",
    "grade": "Grade",
}

with st.sidebar:
    st.markdown(f"Signed in as **{current_user['username']}**")
    streamlit_auth.logout_button()
    st.divider()
    st.markdown(
        "Upload the `.xlsx` exported from **SCU → View My Academic Progress** "
        "(parsed locally; no API calls)."
    )
    xlsx_file = st.file_uploader("Upload Academic Progress (.xlsx)", type=["xlsx"])
    hide_empty = st.checkbox(
        "Hide detail rows that only have status and no registered course", value=False
    )
    run = st.button("Parse")

    st.divider()
    st.markdown("**Curriculum PDF gap analysis** (optional)")
    st.caption(
        "Uses the same **GEMINI_API_KEY** / **GOOGLE_API_KEY** and **GEMINI_MODEL** "
        "as schedule generation. Upload your major-requirements PDF; completed courses "
        "default to codes from your last **Parse** above, plus any you list here."
    )
    pdf_file = st.file_uploader("Major requirements PDF (.pdf)", type=["pdf"])
    pdf_completed_extra = st.text_area(
        "Extra completed course codes (one per line or comma-separated)",
        placeholder="CSEN 174\nCOEN 145",
        key="pdf_completed_extra",
        height=80,
    )
    if st.button("Analyze PDF gaps", type="secondary"):
        if not pdf_file:
            st.warning("Upload a PDF first.")
        else:
            completed = _merge_completed_courses_for_pdf(
                st.session_state.get("parsed_course_codes"), pdf_completed_extra
            )
            if not completed:
                st.warning(
                    "No completed courses to send. Parse Academic Progress above, "
                    "or enter course codes in the extra box."
                )
            else:
                with st.spinner("Analyzing PDF with Gemini…"):
                    try:
                        result = run_requirement_agent(pdf_file.getvalue(), completed)
                    except Exception as e:
                        st.error(f"PDF gap analysis failed: {e}")
                    else:
                        st.session_state["pdf_gap_result"] = result
                        md = _normalize_pdf_missing_details(
                            result.get("missing_details") or []
                        )
                        st.session_state["missing_details"] = md
                        st.success(
                            f"PDF analysis done — {len(md)} gap row(s) ready for Step 2."
                        )
                        st.rerun()

    st.divider()
    with st.expander("My memory", expanded=False):
        st.caption(
            "Past preferences and plans the assistant remembers for *you*. "
            "Delete anything you don't want re-used."
        )
        my_items = memory_agent.list_for_user(USER_ID)
        if not my_items:
            st.info("No memory yet. Generate a recommended schedule to start building one.")
        else:
            for item in my_items:
                with st.container(border=True):
                    st.caption(f"{item['kind']} · {item['created_at']}")
                    st.write(item["content"])
                    if st.button("Delete", key=f"mem_del_{item['id']}"):
                        memory_agent.delete(USER_ID, item["id"])
                        st.rerun()
            if st.button("Delete all my memory", key="mem_del_all"):
                memory_agent.delete_all_for_user(USER_ID)
                st.rerun()


def _detail_table_rows(rows: list[dict]) -> list[dict]:
    return [{COL_LABELS.get(k, k): row.get(k) for k in COL_LABELS if k in row} for row in rows]


def _not_satisfied_table(items: list[dict]) -> list[dict]:
    return [
        {
            "Requirement / item": i.get("requirement"),
            "Remaining (gap)": i.get("remaining"),
        }
        for i in items
    ]


def _recommended_fingerprint(recs: list[dict]) -> str:
    return json.dumps(recs, ensure_ascii=False, sort_keys=True, default=str)


def _merge_completed_courses_for_pdf(
    parsed_codes: list[str] | None, extra_text: str
) -> list[str]:
    """Union of codes from the last Academic Progress parse plus optional sidebar lines."""
    out: list[str] = []
    seen: set[str] = set()
    for c in parsed_codes or []:
        s = str(c).strip()
        if not s:
            continue
        key = s.upper()
        if key not in seen:
            seen.add(key)
            out.append(s)
    for raw in (extra_text or "").replace(",", "\n").split("\n"):
        s = raw.strip()
        if not s:
            continue
        key = s.upper()
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


def _normalize_pdf_missing_details(raw: list) -> list[dict]:
    """Keep only rows usable as planner gap items (non-empty course code)."""
    rows: list[dict] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        course = (item.get("course") or "").strip()
        if not course:
            continue
        u = item.get("units", 0)
        try:
            ui = int(u) if u is not None else 0
        except (TypeError, ValueError):
            ui = 0
        cat = (item.get("category") or "").strip() or "(from PDF)"
        rows.append({"course": course, "category": cat, "units": ui})
    return rows


def _rating_display(rating) -> tuple[str, str]:
    """Return (star markdown, numeric text) for st.markdown."""
    if rating is None:
        return "", "—"
    try:
        r = float(rating)
    except (TypeError, ValueError):
        return "", str(rating)
    filled = max(0, min(5, int(round(r))))
    stars = "★" * filled + "☆" * (5 - filled)
    return stars, f"{r:.1f}/5"


def _planning_warning_messages(planning_result: dict) -> list[str]:
    """Human-readable lines from ``planning_agent`` heuristic ``warnings`` (code + message)."""
    raw = planning_result.get("warnings")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for w in raw:
        if not isinstance(w, dict):
            continue
        m = (w.get("message") or "").strip()
        if m:
            out.append(m)
    return out


if run:
    if not xlsx_file:
        st.warning("Please upload an xlsx file first.")
    else:
        data = parse_academic_progress_xlsx(xlsx_file.getvalue())
        counts = data.get("requirement_status_counts", {})

        st.subheader("Progress overview (one merged status per DegreeWorks requirement block)")
        c1, c2, c3 = st.columns(3)
        c1.metric("Satisfied blocks", counts.get("Satisfied", 0))
        c2.metric("In progress blocks", counts.get("In Progress", 0))
        c3.metric("Not satisfied blocks", counts.get("Not Satisfied", 0))

        st.subheader("Requirements still not satisfied")
        ns = data.get("not_satisfied", [])
        if ns:
            st.dataframe(_not_satisfied_table(ns), use_container_width=True, hide_index=True)
        else:
            st.success("No requirement blocks with status Not Satisfied (per Excel).")

        st.subheader("Parsed course codes from the sheet (unique)")
        codes = data.get("course_codes", [])
        st.session_state["parsed_course_codes"] = list(codes)
        st.write(", ".join(codes) if codes else "(No registration rows with a parseable course code)")

        st.subheader("All detail rows (aligned with Excel)")
        detail = list(data.get("detail_rows", []))
        if hide_empty:
            detail = [r for r in detail if r.get("registration")]
        if detail:
            st.dataframe(_detail_table_rows(detail), use_container_width=True, hide_index=True)
        else:
            st.info("No detail rows — headers may not match or the workbook format changed.")

        parsed_rows = data.get("detail_rows", [])
        st.session_state["missing_details"] = [
            {
                "course": row["course_code"],
                "category": row["requirement"],
                "units": row["units"],
            }
            for row in parsed_rows
            if row["status"] == "Not Satisfied"
        ]
        st.session_state.pop("pdf_gap_result", None)

st.divider()

pdf_gap = st.session_state.get("pdf_gap_result")
if isinstance(pdf_gap, dict):
    st.subheader("Curriculum PDF gap summary (last run)")
    comp = pdf_gap.get("completed") or []
    miss = pdf_gap.get("missing") or []
    if comp:
        st.markdown("**Satisfied (per PDF + your completed list)**")
        st.write(", ".join(str(x) for x in comp) if comp else "—")
    if miss:
        st.markdown("**Still required (per PDF)**")
        st.write(", ".join(str(x) for x in miss))
    md_show = pdf_gap.get("missing_details") or []
    if md_show:
        st.dataframe(
            [
                {
                    "Course": (i or {}).get("course"),
                    "Category": (i or {}).get("category"),
                    "Units": (i or {}).get("units"),
                }
                for i in md_show
                if isinstance(i, dict)
            ],
            use_container_width=True,
            hide_index=True,
        )

st.divider()
st.subheader("Step 2: Generate a recommended schedule (missing_details + your preferences)")

missing_details = st.session_state.get("missing_details")
if isinstance(missing_details, list) and missing_details:
    user_preference = st.text_area(
        "Describe your preferences (target units, time of day, which areas to prioritize…)",
        placeholder="e.g. at most 12 units, finish core first, no classes before 9am",
        key="planning_user_preference",
    )

    if st.button("Generate recommended schedule"):
        if not (user_preference or "").strip():
            st.warning("Please enter your preferences first.")
        else:
            with st.spinner("Generating recommended schedule…"):
                try:
                    previous_plan = st.session_state.get("planning_result")
                    planning_result = plan_for_user(
                        USER_ID,
                        missing_details,
                        user_preference,
                        previous_plan=previous_plan if isinstance(previous_plan, dict) else None,
                    )
                    st.session_state["planning_result"] = planning_result
                    # Remember the preference text so the chat bubble can
                    # render the user side of the conversation alongside
                    # the AI's assistant_reply.
                    st.session_state["last_planning_message"] = (user_preference or "").strip()
                except Exception as e:
                    st.error(f"Generation failed: {e}")

    planning_result = st.session_state.get("planning_result")
    if isinstance(planning_result, dict):
        plan_warning_msgs = _planning_warning_messages(planning_result)
        raw_recs = planning_result.get("recommended") or []
        base_schedule_map = _load_schedule_map_base_from_xlsx()
        if base_schedule_map:
            recs = [r for r in raw_recs if _recommended_item_in_find_course_xlsx(r, base_schedule_map)]
        else:
            recs = list(raw_recs)

        if recs:
            fp = _recommended_fingerprint(recs)
            if st.session_state.get("_recommended_enrichment_fp") != fp:
                with st.spinner("Fetching ratings from RateMyProfessor…"):
                    st.session_state["enriched_courses"] = run_professor_agent(recs)
                    st.session_state["_recommended_enrichment_fp"] = fp
        else:
            st.session_state.pop("enriched_courses", None)
            st.session_state.pop("_recommended_enrichment_fp", None)

        enriched = st.session_state.get("enriched_courses")

        assistant_reply = (planning_result.get("assistant_reply") or "").strip()
        last_user_msg = st.session_state.get("last_planning_message") or ""
        if assistant_reply or last_user_msg:
            if last_user_msg:
                with st.chat_message("user"):
                    st.write(last_user_msg)
            with st.chat_message("assistant"):
                if assistant_reply:
                    st.write(assistant_reply)
                else:
                    # Fallback when the model only filled `advice` (older
                    # mocks / response paths). Still better than silence.
                    fallback = (planning_result.get("advice") or "").strip()
                    st.write(fallback or "Updated the plan based on your preferences.")

        if plan_warning_msgs:
            st.markdown("##### Plan notices")
            for m in plan_warning_msgs:
                st.warning(m)

        if recs:
            st.subheader("Professor ratings (RateMyProfessor)")
            st.caption(
                "After a successful **Generate recommended schedule**, ratings load automatically. "
                "Each **left** card lists **all instructors returned for that course**, sorted by **rating high → low** "
                "(rating, difficulty, would-take-again). The row aligned to **Top pick** is the schedule/heuristic choice when present."
            )

        left, right = st.columns(2)

        with left:
            st.markdown("#### Recommended courses")
            if not recs:
                st.info("(Model returned no recommended list)")
            elif not isinstance(enriched, list):
                st.info("(No professor enrichment loaded)")
            else:
                for item in enriched:
                    with st.container(border=True):
                        course = item.get("course", "(Unknown course)")
                        category = item.get("category", "(Unknown category)")
                        units = item.get("units", "(Unknown units)")
                        reason = item.get("reason", "")

                        st.markdown(f"**{course}**  ·  {category}")
                        st.metric("Units", units)
                        sched = item.get("scheduled_instructors")
                        if isinstance(sched, list) and sched:
                            st.caption("Find Course instructors: " + ", ".join(sched))
                        if reason:
                            st.info(reason)

                        profs = item.get("professors") or []
                        err_msg = item.get("error")
                        rmp_note = item.get("rmp_note")

                        if err_msg:
                            st.warning(err_msg)
                        if rmp_note:
                            st.caption(rmp_note)

                        if not profs:
                            if not err_msg:
                                st.warning("No rating data")
                            continue

                        best_name = (item.get("best_professor") or "").strip()
                        ranked = professors_sorted_by_rating(profs)
                        st.markdown("**Instructors (rating high → low)**")
                        table_rows = []
                        for i, p in enumerate(ranked, start=1):
                            nm = (p.get("name") or "").strip() or "—"
                            note = ""
                            if best_name and nm == best_name:
                                note = "Top pick"
                            stars, numeric = _rating_display(p.get("rating"))
                            rating_cell = f"{stars} {numeric}".strip() if stars else numeric
                            diff = p.get("difficulty")
                            diff_txt = (
                                f"{diff:.1f}"
                                if isinstance(diff, (int, float))
                                else (str(diff) if diff is not None else "—")
                            )
                            wta = p.get("would_take_again") or "N/A"
                            table_rows.append(
                                {
                                    "#": i,
                                    "Instructor": nm,
                                    "Rating": rating_cell,
                                    "Difficulty": diff_txt,
                                    "Would take again": wta,
                                    "Note": note,
                                }
                            )
                        st.dataframe(table_rows, use_container_width=True, hide_index=True)

        with right:
            st.markdown("#### Summary")
            _tu = planning_result.get("total_units")
            if recs:
                su = 0.0
                any_u = False
                for r in recs:
                    try:
                        su += float(r.get("units"))
                        any_u = True
                    except (TypeError, ValueError):
                        pass
                if any_u:
                    st.metric("Total units (courses in schedule file only)", int(su) if su == int(su) else su)
                else:
                    st.metric("Total units", _tu if _tu is not None else "—")
            else:
                st.metric("Total units", _tu if _tu is not None else "—")
            advice = (planning_result.get("advice") or "").strip()
            if advice:
                st.write(advice)
            else:
                st.info("(Model returned no advice)")
            if plan_warning_msgs:
                st.markdown("**Plan notices**")
                for m in plan_warning_msgs:
                    st.warning(m)

        if recs and isinstance(enriched, list) and enriched:
            st.session_state["course_schedule_map"] = load_course_schedule_map_from_xlsx()
            schedule_map = st.session_state["course_schedule_map"]

            st.divider()
            st.subheader("Step 3 · Schedule preview")
            if plan_warning_msgs:
                for m in plan_warning_msgs:
                    st.warning(m)
            st.caption(
                "Times come from the Find Course Sections workbook (Meeting Patterns) in this folder; "
                "if a course has no matching section, it is listed under **Time TBD**."
            )

            day_map = {"M": 0, "T": 1, "W": 2, "Th": 3, "R": 3, "F": 4}
            day_headers = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
            buckets: list[list[tuple[dict, dict]]] = [[] for _ in range(5)]
            pending_cal: list[dict] = []

            for item in enriched:
                code = (item.get("course") or "").strip()
                raw = schedule_map.get(code) if code else None
                parsed = parse_schedule(raw) if raw else None
                if not parsed:
                    pending_cal.append(item)
                    continue
                placed = False
                for d in parsed["days"]:
                    idx = day_map.get(d)
                    if idx is not None:
                        buckets[idx].append((item, parsed))
                        placed = True
                if not placed:
                    pending_cal.append(item)

            header_cols = st.columns(5)
            for i, hc in enumerate(header_cols):
                with hc:
                    st.markdown(f"**{day_headers[i]}**")

            body_cols = st.columns(5)
            for col_i, bc in enumerate(body_cols):
                with bc:
                    for item, parsed in buckets[col_i]:
                        with st.container(border=True):
                            st.markdown(f"**{item.get('course', '(Unknown course)')}**")
                            st.caption(f"{parsed['start']} – {parsed['end']}")
                            st.write(item.get("best_professor") or "—")

            if pending_cal:
                st.markdown("##### Time TBD")
                for item in pending_cal:
                    with st.container(border=True):
                        st.markdown(f"**{item.get('course', '(Unknown course)')}**")
                        st.caption("No Meeting Patterns or no match in schedule xlsx")
                        st.write(item.get("best_professor") or "—")
else:
    st.info(
        "(No `missing_details` yet: run Step 1 requirement analysis and set "
        "`st.session_state['missing_details']`.)"
    )
