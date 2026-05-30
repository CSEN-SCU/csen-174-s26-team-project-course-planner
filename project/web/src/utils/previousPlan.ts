/** Build the ``previous_plan`` payload sent to ``/api/plan``.

Manual calendar edits live in ``localOverride`` while ``planResult`` may still
reflect the last AI response. Follow-up chat must lock against the courses the
student actually sees on the calendar, not a stale server snapshot.
*/
export function previousPlanFromCalendar(
  effectiveRecommended: Record<string, unknown>[],
  planResult: Record<string, unknown> | null,
): Record<string, unknown> | null {
  if (effectiveRecommended.length > 0) {
    let total = 0;
    for (const row of effectiveRecommended) {
      const units = Number((row as { units?: unknown }).units);
      if (Number.isFinite(units)) total += units;
    }
    return { recommended: effectiveRecommended, total_units: total };
  }
  return planResult;
}
