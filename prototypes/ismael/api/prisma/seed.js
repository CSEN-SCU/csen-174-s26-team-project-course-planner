import { PrismaClient } from "@prisma/client";
const prisma = new PrismaClient();
const tags = [
    { name: "ELSJ", category: "Core" },
    { name: "Diversity", category: "Core" },
    { name: "Social Science", category: "Core" },
    { name: "Science with Lab", category: "Core" },
    { name: "Technical Elective", category: "Major" },
    { name: "Major", category: "Major" },
    { name: "Core", category: "Core" },
    { name: "Elective", category: "Elective" }
];
const courses = [
    ["CSE 146", "Database Systems", "major", "upper", ["CSE 101"], "Midday", ["Major", "Technical Elective"]],
    ["CSE 180", "Machine Learning", "major", "upper", ["CSE 101", "MATH 11"], "Afternoon", ["Major", "Technical Elective"]],
    ["CSE 183", "Web Programming", "major", "upper", ["CSE 101"], "Morning", ["Major", "Technical Elective"]],
    ["CSE 160", "Operating Systems", "major", "upper", ["CSE 101"], "Morning", ["Major"]],
    ["CSE 174", "Software Engineering", "major", "upper", ["CSE 101"], "Afternoon", ["Major"]],
    ["CSE 175", "Human Computer Interaction", "major", "upper", ["CSE 101"], "Midday", ["Major"]],
    ["MATH 122", "Probability", "major", "upper", ["MATH 11"], "Morning", ["Major"]],
    ["PHIL 25", "Ethics and Technology", "core", "lower", [], "Afternoon", ["Core", "Diversity"]],
    ["ELSJ 152", "Ethics in Technology", "core", "upper", [], "Morning", ["ELSJ", "Diversity"]],
    ["ANTH 50", "Global Cultures", "core", "lower", [], "Midday", ["Social Science", "Diversity"]],
    ["PSYC 1", "General Psychology", "elective", "lower", [], "Morning", ["Social Science", "Elective"]],
    ["SOCI 30", "Social Inequality", "elective", "lower", [], "Afternoon", ["Social Science", "Diversity"]],
    ["BIOL 21L", "Biology Lab", "core", "lower", [], "Afternoon", ["Science with Lab"]],
    ["CHEM 11L", "Chemistry Lab", "core", "lower", [], "Morning", ["Science with Lab"]],
    ["PHYS 31L", "Physics Lab", "core", "lower", [], "Afternoon", ["Science with Lab"]],
    ["COMM 130", "Public Advocacy", "elective", "upper", ["COMM 2"], "Midday", ["Elective"]],
    ["ECON 1", "Microeconomics", "elective", "lower", [], "Midday", ["Elective", "Social Science"]],
    ["ENGL 106", "Writing in the Public Sphere", "elective", "upper", ["CTW 2"], "Morning", ["Elective"]],
    ["MUSC 20", "Music and Society", "elective", "lower", [], "Afternoon", ["Elective", "Diversity"]],
    ["THEA 14", "Stagecraft", "elective", "lower", [], "Evening", ["Elective"]]
];
function makeSections(code, timeWindow) {
    const windows = {
        Morning: [["TR", "09:00", "10:40"], ["MW", "10:15", "11:55"]],
        Midday: [["MW", "12:00", "13:40"], ["TR", "13:30", "15:10"]],
        Afternoon: [["TR", "15:15", "16:55"], ["MW", "16:00", "17:40"]],
        Evening: [["T", "18:00", "20:30"], ["R", "18:00", "20:30"]]
    };
    const instructors = ["Dr. Li", "Prof. Nguyen", "Dr. Morales", "Prof. Allen", "Dr. Yu", "Prof. Kim"];
    return (windows[timeWindow] ?? windows.Morning).map((slot, index) => ({
        sectionCode: `${code.split(' ')[1]}-${String.fromCharCode(65 + index)}`,
        instructor: instructors[(code.length + index) % instructors.length],
        days: slot[0],
        startTime: slot[1],
        endTime: slot[2],
        seatsAvailable: 8 + ((code.length + index * 3) % 24),
        professorRating: {
            create: {
                instructor: instructors[(code.length + index) % instructors.length],
                source: index % 2 === 0 ? "SCU Eval" : "RateMyProfessor",
                qualityScore: 3.8 + (((code.length + index) % 10) / 10),
                difficultyScore: 2.2 + (((code.length + index * 2) % 15) / 10),
                wouldTakeAgain: 68 + ((code.length + index * 5) % 25)
            }
        }
    }));
}
async function main() {
    await prisma.planItem.deleteMany();
    await prisma.plan.deleteMany();
    await prisma.professorRating.deleteMany();
    await prisma.section.deleteMany();
    await prisma.courseRequirementTag.deleteMany();
    await prisma.requirementTag.deleteMany();
    await prisma.completedCourse.deleteMany();
    await prisma.course.deleteMany();
    for (const tag of tags) {
        await prisma.requirementTag.create({ data: tag });
    }
    const tagMap = Object.fromEntries((await prisma.requirementTag.findMany()).map((tag) => [tag.name, tag.id]));
    for (const [code, name, type, division, prerequisites, timeWindow, tagNames] of courses) {
        await prisma.course.create({
            data: {
                code,
                name,
                type,
                division,
                prerequisiteCodes: prerequisites,
                timeWindow,
                description: `${name} helps students compare quality, workload, and schedule fit.`,
                requirementLinks: {
                    create: tagNames.map((tagName) => ({ requirementTagId: tagMap[tagName] }))
                },
                sections: {
                    create: makeSections(code, timeWindow)
                }
            }
        });
    }
    await prisma.completedCourse.createMany({
        data: [
            { studentKey: "sample-student", code: "CSE 30", title: "Intro to Programming", term: "Fall 2024", grade: "A" },
            { studentKey: "sample-student", code: "CSE 101", title: "Algorithms", term: "Winter 2025", grade: "B+" },
            { studentKey: "sample-student", code: "MATH 11", title: "Calculus", term: "Spring 2025", grade: "A-" },
            { studentKey: "sample-student", code: "CTW 1", title: "Critical Thinking 1", term: "Fall 2024", grade: "A" },
            { studentKey: "sample-student", code: "CTW 2", title: "Critical Thinking 2", term: "Winter 2025", grade: "A-" },
            { studentKey: "sample-student", code: "COMM 2", title: "Public Speaking", term: "Spring 2025", grade: "B" }
        ]
    });
    console.log(`Seeded ${courses.length} courses.`);
}
main()
    .catch((error) => {
    console.error(error);
    process.exit(1);
})
    .finally(async () => {
    await prisma.$disconnect();
});
