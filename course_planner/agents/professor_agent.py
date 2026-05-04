"""
SCU professor ratings via the unofficial RateMyProfessors GraphQL client.

If ``SCU_Find_Course_Sections.xlsx`` / ``scu_find_course.xlsx`` exists under the project root
(next-term schedule and instructors), RMP results are aligned to **scheduled instructors** first,
then refined with course-code hits in reviews and overall ratings.

Each recommended course uses **its own paginated search** filtered by department; courses run
**in parallel** across a thread pool (one ``RMPClient()`` per thread).
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any

from rmp_client import RMPClient

from utils.scu_course_schedule_xlsx import (
    load_schedule_section_index,
    scheduled_instructors_for_course,
)

# Santa Clara University school id on RMP (fallback if search_schools fails)
SCU_RMP_SCHOOL_ID = 882

# Parallel course cap (avoid bursty concurrency against RMP)
_MAX_PARALLEL_COURSES = 6

_NUM_TOKEN_RE = re.compile(r"\b(\d{2,4}[A-Z]?)\b", re.IGNORECASE)


def _subject_prefix(course_code: str) -> str:
    cleaned = course_code.replace("&", " ").replace("/", " ").replace(",", " ")
    parts = [p for p in cleaned.split() if p and p not in ("-", "and", "AND", "L", "l")]
    return parts[0].upper() if parts else ""


def _dept_keywords(course_code: str, category: str | None) -> set[str]:
    """Infer department keywords (lowercase) from course prefix + requirement text for department matching."""
    cat = (category or "").lower()
    sub0 = _subject_prefix(course_code)
    keys: set[str] = set()

    prefix_map: dict[str, frozenset[str]] = {
        "COEN": frozenset({"computer"}),
        "CSEN": frozenset({"computer"}),
        "CSCI": frozenset({"computer"}),
        "ECEN": frozenset({"electrical"}),
        "ELEN": frozenset({"electrical"}),
        "ENGR": frozenset({"engineering"}),
        "MATH": frozenset({"mathematics", "math"}),
        "AMTH": frozenset({"mathematics", "math", "applied"}),
        "PHYS": frozenset({"physics"}),
        "CHEM": frozenset({"chemistry"}),
        "BIOL": frozenset({"biology"}),
        "ECON": frozenset({"economics"}),
        "POLI": frozenset({"political"}),
        "PSYC": frozenset({"psychology"}),
        "PHIL": frozenset({"philosophy"}),
        "ENGL": frozenset({"english"}),
        "ARTH": frozenset({"art", "history"}),
        "TESP": frozenset({"religion", "religious", "theolog", "jesuit"}),
        "RELI": frozenset({"religion", "religious", "theolog", "jesuit"}),
        "RSOC": frozenset({"religion", "religious", "theolog", "jesuit"}),
    }
    if sub0 in prefix_map:
        keys |= set(prefix_map[sub0])

    if "computer" in cat or "coen" in cat or "csen" in cat:
        keys.add("computer")
    if "electrical" in cat or "ecen" in cat or "elen" in cat:
        keys.add("electrical")
    if "math" in cat or "mathematics" in cat or "amth" in cat:
        keys.update({"mathematics", "math"})
    if "physics" in cat:
        keys.add("physics")
    if "chemistry" in cat:
        keys.add("chemistry")
    if "biology" in cat:
        keys.add("biology")
    if "economics" in cat:
        keys.add("economics")
    if "english" in cat or "writing" in cat:
        keys.add("english")
    if "art" in cat and "history" in cat:
        keys.update({"art", "history"})
    elif "art" in cat:
        keys.add("art")
    if "rtc" in cat or "tesp" in cat or "religious" in cat or "religion" in cat or "theolog" in cat:
        keys.update({"religion", "religious", "theolog", "jesuit"})
    if "ethic" in cat and ("tech" in cat or "engr" in cat or "engineering" in cat):
        keys.update({"religion", "philosophy"})

    return keys


def _expected_course_numbers(course_code: str) -> set[str]:
    """Extract number tokens (e.g. 122 / 122L) from the course string for RMP course_raw matching."""
    nums: set[str] = set()
    for m in _NUM_TOKEN_RE.finditer(course_code.upper()):
        n = m.group(1).upper()
        nums.add(n)
        if n.endswith("L") and len(n) > 1:
            nums.add(n[:-1])
        elif re.fullmatch(r"\d+[A-Z]?", n) and not n.endswith("L"):
            nums.add(n + "L")
    return {x for x in nums if x and not x.isalpha()}


def _expected_subjects_for_raw(course_code: str) -> set[str]:
    """Subject abbreviations that may appear in RMP course_raw; COEN/CSEN are often cross-listed."""
    found = set(re.findall(r"\b(COEN|CSEN|CSCI|ECEN|ELEN|MATH|AMTH|PHYS|CHEM|BIOL)\b", course_code.upper()))
    p = _subject_prefix(course_code)
    if p:
        found.add(p)
    if "COEN" in found:
        found.add("CSEN")
    if "CSEN" in found:
        found.add("COEN")
    return found


def _course_raw_relevance(course_code: str, course_raw: str | None) -> int:
    """How well a review's course_raw matches the recommended course (higher = prefer showing)."""
    if not course_raw:
        return 0
    raw = course_raw.upper().replace(" ", "").replace("-", "")
    nums = _expected_course_numbers(course_code)
    if not nums or not any(n in raw for n in nums):
        return 0
    subs = _expected_subjects_for_raw(course_code)
    if subs and any(s in raw for s in subs):
        return 10
    return 3


def _professor_course_evidence_score(
    client: RMPClient, professor_id: str, course_code: str, *, max_pages: int = 2
) -> int:
    """Fetch recent rating pages for a professor; sum course_raw relevance scores for this course."""
    total = 0
    cursor: str | None = None
    for _ in range(max_pages):
        try:
            page = client.get_professor_ratings_page(
                professor_id, page_size=25, cursor=cursor
            )
        except Exception:
            break
        for rt in page.ratings or []:
            total += _course_raw_relevance(course_code, getattr(rt, "course_raw", None))
        if not page.has_next_page or not page.next_cursor:
            break
        cursor = page.next_cursor
    return total


def _resolve_school_id(client: RMPClient) -> int:
    try:
        res = client.search_schools("Santa Clara University", page_size=5)
        if res.schools:
            return int(res.schools[0].id)
    except Exception:
        pass
    return SCU_RMP_SCHOOL_ID


def _paginate_collect_matches(
    client: RMPClient,
    school_id: int,
    keywords: set[str],
    abbr: str | None,
    *,
    max_pages: int = 25,
    page_size: int = 25,
) -> list[Any]:
    """
    Per-course: paginate from page 1 and collect professors whose department matches keywords or subject prefix (dedupe by id).
    """
    matched: list[Any] = []
    seen: set[tuple[Any, str, str | None]] = set()
    cursor: str | None = None

    for _ in range(max_pages):
        r = client.list_professors_for_school(
            school_id, query=None, page_size=page_size, cursor=cursor
        )
        for p in r.professors or []:
            key = (getattr(p, "id", None), p.name, getattr(p, "department", None))
            if key in seen:
                continue
            dept = (p.department or "").lower()
            ok = False
            if keywords and any(k in dept for k in keywords):
                ok = True
            elif abbr and abbr.lower() in dept:
                ok = True
            if ok:
                seen.add(key)
                matched.append(p)

        if not r.has_next_page or not r.next_cursor:
            break
        cursor = r.next_cursor

    return matched


def _prof_to_dict(p: Any) -> dict[str, Any]:
    wta = getattr(p, "percent_take_again", None)
    wta_str = f"{round(float(wta))}%" if wta is not None else "N/A"
    return {
        "name": p.name,
        "rating": p.overall_rating,
        "difficulty": p.level_of_difficulty,
        "would_take_again": wta_str,
    }


def _names_same_person(rmp_name: str, schedule_name: str) -> bool:
    """Loose match: full name equal, or same last name and same first initial (Joe / Joseph)."""
    a = " ".join(rmp_name.lower().split())
    b = " ".join(schedule_name.lower().split())
    if a == b:
        return True
    ap, bp = a.split(), b.split()
    if not ap or not bp:
        return False
    if ap[-1] != bp[-1]:
        return False
    return ap[0][0] == bp[0][0]


def _lookup_scheduled_professor(
    client: RMPClient, school_id: int, schedule_name: str
) -> Any | None:
    """Look up a professor on RMP by schedule-listed name (display only; does not widen the candidate set)."""
    query = schedule_name.split()[-1]
    if len(query) < 2:
        return None
    try:
        r = client.list_professors_for_school(school_id, query=query, page_size=20)
    except Exception:
        return None
    for p in r.professors or []:
        if _names_same_person(p.name, schedule_name):
            return p
    return None


def _professors_strictly_from_schedule(
    client: RMPClient,
    school_id: int,
    scheduled_names: list[str],
    course_code: str,
) -> list[dict[str, Any]]:
    """
    Return only schedule-listed instructors with RMP data when found; otherwise keep the name only—no other-department mix-in.
    """
    uniq: list[str] = []
    for nm in scheduled_names:
        if nm not in uniq:
            uniq.append(nm)

    scored: list[tuple[int, float, dict[str, Any]]] = []
    for nm in uniq:
        p = _lookup_scheduled_professor(client, school_id, nm)
        if p is not None:
            pid = str(getattr(p, "id", "") or "")
            ev = _professor_course_evidence_score(client, pid, course_code) if pid else 0
            rating = float(p.overall_rating) if p.overall_rating is not None else 0.0
            scored.append((ev, rating, _prof_to_dict(p)))
        else:
            scored.append(
                (
                    0,
                    0.0,
                    {
                        "name": nm,
                        "rating": None,
                        "difficulty": None,
                        "would_take_again": "N/A",
                    },
                )
            )

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [t[2] for t in scored]


def _enrich_one_course(course: dict, *, schedule_index: dict[tuple[str, str], list[str]]) -> dict:
    """One course: own client + paginated search + top professors by rating within the department."""
    enriched = dict(course)
    enriched["professors"] = []
    enriched["best_professor"] = None

    course_code = course.get("course") or ""
    category = course.get("category")
    scheduled_names = scheduled_instructors_for_course(course_code, schedule_index)

    try:
        with RMPClient() as client:
            school_id = _resolve_school_id(client)

            # Schedule hit: show only scheduled instructors (optionally with RMP), never department-page extras
            if scheduled_names:
                enriched["scheduled_instructors"] = scheduled_names
                prof_list = _professors_strictly_from_schedule(
                    client, school_id, scheduled_names, course_code
                )
                enriched["professors"] = prof_list
                if prof_list:
                    enriched["best_professor"] = prof_list[0]["name"]
                    if any(x.get("rating") is None for x in prof_list):
                        enriched["rmp_note"] = (
                            "Some scheduled instructors have no RMP profile; the UI keeps schedule names only."
                        )
                    else:
                        top_p = _lookup_scheduled_professor(
                            client, school_id, prof_list[0]["name"]
                        )
                        if top_p is not None and _professor_course_evidence_score(
                            client, str(top_p.id), course_code
                        ) == 0:
                            enriched["rmp_note"] = (
                                "Aligned to scheduled instructors; sampled reviews did not tag this course code—see the professor page on RMP for more."
                            )
                return enriched

            keywords = _dept_keywords(course_code, category)
            pref = _subject_prefix(course_code)
            abbr = pref.lower() if pref else None

            if not keywords and not abbr:
                enriched["rmp_note"] = (
                    "Could not infer department from course/requirement; skipped RMP search. "
                    "Try RateMyProfessors manually for this course."
                )
                return enriched

            matched = _paginate_collect_matches(client, school_id, keywords, abbr)

            if not matched:
                enriched["rmp_note"] = (
                    "No professors matched this course’s department/type in paginated search; "
                    "check the university site or RMP by course code or title."
                )
                return enriched

            # No schedule row: department pagination + course evidence + score (may include non-instructors—reference only)
            prelim_n = 70 if _NUM_TOKEN_RE.search(course_code) else 45
            prelim = sorted(
                matched,
                key=lambda p: (p.overall_rating is not None, p.overall_rating or 0.0),
                reverse=True,
            )[: min(prelim_n, len(matched))]

            scored: list[tuple[int, float, Any]] = []
            for p in prelim:
                pid = str(getattr(p, "id", "") or "")
                if not pid:
                    continue
                ev = _professor_course_evidence_score(client, pid, course_code)
                rating = float(p.overall_rating) if p.overall_rating is not None else 0.0
                scored.append((ev, rating, p))

            if not scored:
                ranked = sorted(
                    prelim,
                    key=lambda p: (p.overall_rating is not None, p.overall_rating or 0.0),
                    reverse=True,
                )[:5]
                top_ev = 0
            else:
                scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
                ranked = [t[2] for t in scored[:5]]
                top_ev = scored[0][0]

            prof_list = [_prof_to_dict(p) for p in ranked]
            enriched["professors"] = prof_list
            if prof_list:
                enriched["best_professor"] = prof_list[0]["name"]
                if top_ev == 0:
                    enriched["rmp_note"] = (
                        "No schedule xlsx or no match for this course; sampled reviews had no clear course code; "
                        "list below is **same-department reference, not the official instructor list**."
                    )

    except Exception as e:
        enriched["error"] = str(e)
        return enriched

    return enriched


def run_professor_agent(recommended_courses: list[dict]) -> list[dict]:
    """
    Input: recommended list from planning_agent.
    Output: per-course professor enrichment in the same order as input.
    """
    if not recommended_courses:
        return []

    schedule_index = load_schedule_section_index()
    workers = max(1, min(_MAX_PARALLEL_COURSES, len(recommended_courses)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(
            executor.map(
                partial(_enrich_one_course, schedule_index=schedule_index),
                recommended_courses,
            )
        )
