const requirementMap = {
  ELSJ: ["ELSJ 152"],
  Diversity: ["Diversity Elective"],
  "Science with Lab": ["PHYS 31L", "CHEM 11L"],
  "Technical Elective": ["CSE 146", "CSE 180", "CSE 183"]
} as const;

export function buildTranscriptSummary(fileName?: string, transcriptText?: string) {
  const source = `${fileName ?? ""} ${transcriptText ?? ""}`.toLowerCase();
  const completedCourses = source.includes("transfer")
    ? ["CSE 30", "CSE 101", "MATH 11", "ENGL 1A"]
    : ["CSE 30", "CSE 101", "MATH 11", "CTW 1", "CTW 2", "COMM 2"];

  const remainingRequirements = Object.entries(requirementMap)
    .filter(([, courses]) => !courses.some((course) => completedCourses.includes(course)))
    .map(([requirement]) => requirement);

  return {
    studentName: source.includes("ismael") ? "Ismael Yepez" : "Sample Student",
    major: "Computer Science",
    unitsCompleted: completedCourses.length * 4,
    completedCourses,
    remainingRequirements,
    source: fileName ?? "mock-upload"
  };
}
