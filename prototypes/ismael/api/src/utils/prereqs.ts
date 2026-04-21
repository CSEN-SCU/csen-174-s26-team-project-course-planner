export function isEligible(completedCourseCodes: string[], prerequisiteCodes: string[]) {
  if (!prerequisiteCodes.length) return true;
  const completed = new Set(completedCourseCodes.map((code) => code.toUpperCase()));
  return prerequisiteCodes.every((code) => completed.has(code.toUpperCase()));
}
