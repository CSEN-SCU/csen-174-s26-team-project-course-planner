import re
from typing import Any, Optional

from .ai_client import enrich_rationales_with_ai, heuristic_parse_transcript, parse_transcript_with_ai
from .academic_progress import load_academic_progress_xlsx
from .major_requirements import fetch_major_requirements
from .schemas import OfferingOut, ParsedCourse, PlanRequest, RecommendationOut
from .seed import seed_offerings


_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")


def _parse_start_time(schedule: str) -> Optional[int]:
    """
    Best-effort: take earliest HH:MM in the schedule string as start time.
    """
    times = []
    for hh, mm in _TIME_RE.findall(schedule):
        times.append(int(hh) * 60 + int(mm))
    return min(times) if times else None


def _evening_conflict(schedule: str, avoid_evening: bool) -> bool:
    if not avoid_evening:
        return False
    start = _parse_start_time(schedule)
    if start is None:
        return False
    # 17:00 = 1020 minutes from midnight... wait compute: 17*60=1020
    return start >= 17 * 60


def _normalize_code(code: str) -> str:
    return re.sub(r"\s+", " ", code.strip().upper())

def _normalize_term(term: str) -> str:
    return re.sub(r"\s+", " ", term.strip().lower())


def _completed_set(parsed: list[ParsedCourse]) -> set[str]:
    return {_normalize_code(c.code) for c in parsed}


def _code_appears_in_raw_transcript(code: str, transcript_text: str) -> bool:
    """
    Extra safety net: if parsing misses a course code (e.g. user pastes a custom list),
    still avoid recommending anything whose code plainly appears in the raw transcript text.
    """
    c = _normalize_code(code)
    # Normalize unicode dashes and collapse whitespace to improve matching.
    t = transcript_text.upper().replace("–", "-").replace("—", "-")
    t = re.sub(r"\s+", " ", t)
    dept_num = c.split(" ", 1)
    if len(dept_num) != 2:
        return False
    dept, num = dept_num
    # Allow slashes in user input like "ENGR 1 / ENGR 1L".
    pattern = rf"\b{re.escape(dept)}\s+{re.escape(num)}\b"
    return re.search(pattern, t) is not None


_DEMO_EQUIVALENTS: dict[str, set[str]] = {
    # Demo catalog uses CTW, but many transcripts / user lists use ENGL.
    "CTW 1": {"CTW 1", "ENGL 1A"},
    "CTW 2": {"CTW 2", "ENGL 2A"},
    # Demo catalog uses COEN 11; some users paste COEN 10.
    "COEN 11": {"COEN 11", "COEN 10"},
    # COEN was historically CSEN for some cohorts (treat as equivalent for filtering in this demo).
    "COEN 12": {"COEN 12", "CSEN 12"},
    "COEN 19": {"COEN 19", "CSEN 19"},
    "COEN 20": {"COEN 20", "CSEN 20"},
    "COEN 146": {"COEN 146", "CSEN 146"},
    "COEN 171": {"COEN 171", "CSEN 174"},
    # Demo naming mismatch: Data Structures is CSEN 12 on many transcripts.
    "COEN 21": {"COEN 21", "CSEN 12"},
    # Demo catalog uses MATH 51/52/53; many transcripts use MATH 11/12/13/14.
    "MATH 51": {"MATH 51", "MATH 11"},
    "MATH 52": {"MATH 52", "MATH 12"},
    "MATH 53": {"MATH 53", "MATH 13", "MATH 14"},
}


def _is_completed_or_equivalent(offering_code: str, completed: set[str], transcript_text: str) -> bool:
    code = _normalize_code(offering_code)
    eq = _DEMO_EQUIVALENTS.get(code, {code})
    for alt in eq:
        alt_n = _normalize_code(alt)
        if alt_n in completed or _code_appears_in_raw_transcript(alt_n, transcript_text):
            return True
    return False


def _term_offerings(term: str) -> list[dict[str, Any]]:
    req_term_n = _normalize_term(term)
    return [o for o in seed_offerings() if _normalize_term(str(o.get("term", ""))) == req_term_n]


async def build_plan_from_academic_progress(
    *,
    progress_xlsx_path: str,
    major_requirements_url: str,
    term: str,
) -> dict[str, Any]:
    ap = load_academic_progress_xlsx(progress_xlsx_path)
    completed = {_normalize_code(c) for c in ap.completed_codes}

    mr = await fetch_major_requirements(major_requirements_url)
    major_codes_in_order: list[str] = []
    seen: set[str] = set()
    for section, codes in mr.sections.items():
        # Educational Enrichment is not a concrete course requirement list; it contains options.
        if "educational enrichment" in section.lower():
            continue
        for c in codes:
            cn = _normalize_code(c)
            if cn in seen:
                continue
            seen.add(cn)
            major_codes_in_order.append(cn)

    missing_major = [c for c in major_codes_in_order if c not in completed]

    # If an "option group" is already satisfied by any completed course, do not recommend other options.
    satisfied_options: set[str] = set()
    for group in getattr(mr, "option_groups", []) or []:
        group_n = [_normalize_code(x) for x in group]
        if any(x in completed for x in group_n):
            satisfied_options.update(group_n)

    offerings = _term_offerings(term)
    by_code: dict[str, dict[str, Any]] = {_normalize_code(str(o.get("code", ""))): o for o in offerings}

    recs: list[dict[str, Any]] = []
    added: set[str] = set()

    # 1) Missing major requirement courses (in order)
    for code in missing_major:
        if code in satisfied_options:
            continue
        o = by_code.get(code)
        if not o:
            continue
        if _is_completed_or_equivalent(code, completed, " ".join(sorted(completed))):
            continue
        if code in added:
            continue
        added.add(code)
        recs.append(
            {
                "code": code,
                "title": str(o.get("title", "")),
                "term": str(o.get("term", term)),
                "units": int(o.get("units", 4) or 4),
                "schedule": str(o.get("schedule", "")),
                "tags": str(o.get("tags", "")) if o.get("tags") is not None else None,
                "instructors": list(o.get("instructors", []) or []),
                "why": "major_requirement",
            }
        )

    # 2) Tag-based fill: unsatisfied requirements vs Course Tags
    need_keywords: list[str] = []
    for r in ap.unsatisfied_requirements:
        rl = r.lower()
        if "core" in rl or "core curriculum" in rl or "university core" in rl:
            need_keywords.append(r)
    if not need_keywords:
        need_keywords = ap.unsatisfied_requirements[:25]

    def matches_need(o: dict[str, Any]) -> Optional[str]:
        tags = str(o.get("tags", "") or "")
        t_l = tags.lower()
        for kw in need_keywords:
            k = kw.lower()
            tail = k.split(":", 1)[-1].strip()
            if tail and tail in t_l:
                return kw
            if k and k in t_l:
                return kw
        return None

    for o in offerings:
        code = _normalize_code(str(o.get("code", "")))
        if not code or code in added or code in completed:
            continue
        hit = matches_need(o)
        if not hit:
            continue
        added.add(code)
        recs.append(
            {
                "code": code,
                "title": str(o.get("title", "")),
                "term": str(o.get("term", term)),
                "units": int(o.get("units", 4) or 4),
                "schedule": str(o.get("schedule", "")),
                "tags": str(o.get("tags", "")) if o.get("tags") is not None else None,
                "instructors": list(o.get("instructors", []) or []),
                "why": f"course_tag_match: {hit}",
            }
        )

    return {
        "completed_codes": sorted(completed),
        "missing_major_codes": missing_major,
        "unsatisfied_requirements": ap.unsatisfied_requirements,
        "recommendations": recs,
    }


def _prereq_status(course_prereqs: list[str], completed: set[str]) -> tuple[str, list[str]]:
    missing = []
    for p in course_prereqs:
        pn = _normalize_code(p)
        if pn not in completed:
            missing.append(p)
    if missing:
        return "ineligible", missing
    return "eligible", []


def _score_offering(
    offering: dict[str, Any],
    prefs: PlanRequest,
    completed: set[str],
) -> tuple[float, dict[str, Any]]:
    """
    Simple weighted score for demo. Higher is better.
    """
    q = float(offering["quality"])
    w = float(offering["workload"])  # 1..5-ish

    qw = prefs.prefs.quality_weight / 100.0
    ww = prefs.prefs.workload_weight / 100.0
    pw = prefs.prefs.progress_weight / 100.0

    prereq_penalty = 0.0
    status, missing = _prereq_status(offering.get("prereqs", []), completed)
    if status == "ineligible":
        prereq_penalty = 2.0

    # "progress" proxy: more prereqs => more advanced => slightly higher when eligible
    progress_signal = min(1.0, 0.15 * len(offering.get("prereqs", [])))

    schedule_penalty = 0.0
    if prefs.prefs.online_only:
        schedule_penalty += 0.75  # demo catalog doesn't encode modality; penalize uniformly
    if _evening_conflict(str(offering.get("schedule", "")), prefs.prefs.avoid_evening):
        schedule_penalty += 0.75

    # workload preference: higher workload_weight means student tolerates workload better => less penalty
    workload_penalty = max(0.0, (w - 3.0) * (1.1 - 0.35 * ww))

    score = (
        qw * q
        + pw * (5.0 * progress_signal)
        - prereq_penalty * 3.0
        - workload_penalty
        - schedule_penalty
    )

    rationale = {
        "signals": {
            "quality": q,
            "workload": w,
            "prereqs": offering.get("prereqs", []),
            "missing_prereqs": missing,
            "schedule": offering.get("schedule", ""),
        },
        "weights": {
            "quality_weight": prefs.prefs.quality_weight,
            "workload_weight": prefs.prefs.workload_weight,
            "progress_weight": prefs.prefs.progress_weight,
            "avoid_evening": prefs.prefs.avoid_evening,
            "online_only": prefs.prefs.online_only,
        },
        "notes": [],
    }

    if status == "ineligible":
        rationale["notes"].append("Not eligible based on parsed transcript prereqs (demo rules).")
    if prefs.prefs.online_only:
        rationale["notes"].append("Online-only filter is enabled, but this demo catalog does not include modality metadata.")
    if _evening_conflict(str(offering.get("schedule", "")), prefs.prefs.avoid_evening):
        rationale["notes"].append("Filtered/penalized for evening start time preference.")

    return score, rationale


def _fallback_rationales(recs: list[RecommendationOut]) -> dict[str, Any]:
    items = []
    for r in recs:
        bullets = [
            f"综合分约 {r.score:.2f}（演示用启发式评分）。",
            f"教学质量信号 quality={r.course.quality:.1f}，工作量信号 workload={r.course.workload:.1f}。",
        ]
        risks = []
        if r.course.status != "eligible":
            risks.append("先修不满足或不确定：请对照官方 catalog / Workday 二次确认。")
        if r.course.missing_prereqs:
            risks.append(f"缺少先修：{', '.join(r.course.missing_prereqs)}")
        items.append({"code": r.course.code, "bullets": bullets, "risks": risks})
    return {"items": items}


async def build_plan(req: PlanRequest) -> tuple[list[ParsedCourse], list[RecommendationOut]]:
    offerings = _term_offerings(req.term)

    parsed_dicts: list[dict[str, Any]]
    try:
        parsed_dicts = await parse_transcript_with_ai(req.transcript_text)
    except Exception:
        parsed_dicts = heuristic_parse_transcript(req.transcript_text)

    parsed: list[ParsedCourse] = []
    for c in parsed_dicts:
        if not isinstance(c, dict):
            continue
        if not isinstance(c.get("code"), str):
            continue
        try:
            parsed.append(ParsedCourse(**c))
        except Exception:
            continue

    if not parsed:
        parsed_dicts = heuristic_parse_transcript(req.transcript_text)
        for c in parsed_dicts:
            if not isinstance(c, dict):
                continue
            if not isinstance(c.get("code"), str):
                continue
            try:
                parsed.append(ParsedCourse(**c))
            except Exception:
                continue

    completed = _completed_set(parsed)

    recs: list[RecommendationOut] = []
    for o in offerings:
        o_code = _normalize_code(str(o.get("code", "")))
        # Never recommend a course already completed (including demo equivalence mapping).
        if _is_completed_or_equivalent(o_code, completed, req.transcript_text):
            continue
        status, missing = _prereq_status(o.get("prereqs", []), completed)
        offering_out = OfferingOut(
            code=o["code"],
            title=o["title"],
            term=o["term"],
            units=int(o["units"]),
            prereqs=list(o.get("prereqs", [])),
            schedule=str(o.get("schedule", "")),
            instructors=list(o.get("instructors", []) or []),
            quality=float(o["quality"]),
            workload=float(o["workload"]),
            status=status if status == "eligible" else "ineligible",
            missing_prereqs=missing,
        )

        score, rationale = _score_offering(o, req, completed)
        recs.append(RecommendationOut(course=offering_out, score=score, rationale=rationale))

    recs.sort(key=lambda r: r.score, reverse=True)
    top = recs[:5]

    # Optional second AI pass: nicer language (still grounded on our structured rationale)
    try:
        ai_payload = {
            "major": req.major,
            "term": req.term,
            "parsed_course_codes": sorted(list(completed)),
            "top": [
                {
                    "code": r.course.code,
                    "title": r.course.title,
                    "score": r.score,
                    "status": r.course.status,
                    "missing_prereqs": r.course.missing_prereqs,
                    "signals": r.rationale.get("signals", {}),
                    "weights": r.rationale.get("weights", {}),
                }
                for r in top
            ],
        }
        enriched = await enrich_rationales_with_ai(ai_payload)
        by_code = {str(x.get("code")): x for x in enriched.get("items", []) if isinstance(x, dict)}
        for r in top:
            item = by_code.get(r.course.code)
            if not item:
                continue
            bullets = item.get("bullets")
            risks = item.get("risks")
            if isinstance(bullets, list):
                r.rationale["ai_bullets"] = [str(b) for b in bullets]
            if isinstance(risks, list):
                r.rationale["ai_risks"] = [str(x) for x in risks]
    except Exception:
        # keep deterministic demo output
        enriched = _fallback_rationales(top)
        for r in top:
            item = next((x for x in enriched.get("items", []) if x.get("code") == r.course.code), None)
            if not item:
                continue
            r.rationale["ai_bullets"] = item.get("bullets", [])
            r.rationale["ai_risks"] = item.get("risks", [])

    return parsed, top
