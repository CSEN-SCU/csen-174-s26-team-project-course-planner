const requirementMap = {
  "University Core": ["CTW 1", "CTW 2", "CI 1", "CI 2", "RTC 1"],
  "Science with Lab": ["CHEM 11", "PHYS 31", "PHYS 32", "PHYS 33"],
  "Computer Engineering Major": ["COEN 19", "COEN 10", "COEN 11", "COEN 12"],
  "Computer Engineering Elective": ["COEN 161", "COEN 168", "COEN 181"],
  "Educational Enrichment": ["EE 1", "EE 2", "EE 3"]
} as const;

export function buildTranscriptSummary(fileName?: string, transcriptText?: string) {
  const source = `${fileName ?? ""} ${transcriptText ?? ""}`.toLowerCase();
  const firstYearCompleted = [
    "COEN 19",
    "CTW 1",
    "CTW 2",
    "MATH 11",
    "MATH 12",
    "MATH 13",
    "CHEM 11",
    "PHYS 31",
    "PHYS 32",
    "COEN 10",
    "COEN 11",
    "COEN 12",
    "ENGR 1"
  ];
  const completedCourses = source.includes("transfer")
    ? ["COEN 19", "COEN 10", "COEN 11", "COEN 12", "MATH 11"]
    : firstYearCompleted;

  const remainingRequirements = Object.entries(requirementMap)
    .filter(([, courses]) => !courses.some((course) => completedCourses.includes(course)))
    .map(([requirement]) => requirement);

  return {
    studentName: source.includes("ismael") ? "Ismael Yepez" : "Sample Student",
    major: "Computer Engineering",
    unitsCompleted: completedCourses.length * 4,
    completedCourses,
    remainingRequirements,
    source: fileName ?? "mock-upload"
  };
}
