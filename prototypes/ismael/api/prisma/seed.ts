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
  { name: "Elective", category: "Elective" },
  { name: "University Core", category: "Core" },
  { name: "Computer Engineering Elective", category: "Major" },
  { name: "Educational Enrichment", category: "Elective" }
];

const courses = [
  ["COEN 19","Discrete Math","major","lower",[],"Morning",["Major"]],
  ["CTW 1","Critical Thinking & Writing 1","core","lower",[],"Morning",["University Core","Core"]],
  ["CTW 2","Critical Thinking & Writing 2","core","lower",["CTW 1"],"Midday",["University Core","Core"]],
  ["MATH 11","Calculus I","major","lower",[],"Morning",["Major"]],
  ["MATH 12","Calculus II","major","lower",["MATH 11"],"Morning",["Major"]],
  ["MATH 13","Calculus III","major","lower",["MATH 12"],"Morning",["Major"]],
  ["CHEM 11","Chemistry I","core","lower",[],"Afternoon",["Science with Lab","Core"]],
  ["PHYS 31","Physics I","major","lower",["MATH 11"],"Afternoon",["Major"]],
  ["PHYS 32","Physics II","major","lower",["PHYS 31","MATH 12"],"Afternoon",["Major"]],
  ["COEN 10","Introduction to Programming","major","lower",[],"Morning",["Major"]],
  ["COEN 11","Advanced Programming","major","lower",["COEN 10"],"Midday",["Major"]],
  ["COEN 12","Data Structures","major","lower",["COEN 11"],"Midday",["Major"]],
  ["ENGR 1","Introduction to Engineering","core","lower",[],"Afternoon",["University Core","Core"]],

  ["CI 1","Cultures & Ideas 1","core","lower",[],"Morning",["University Core","Core"]],
  ["CI 2","Cultures & Ideas 2","core","lower",["CI 1"],"Morning",["University Core","Core"]],
  ["RTC 1","Religion, Theology & Culture 1","core","lower",[],"Midday",["University Core","Core"]],
  ["MATH 14","Calculus IV","major","upper",["MATH 13"],"Morning",["Major"]],
  ["AMTH 106","Differential Equations","major","upper",["MATH 14"],"Midday",["Major"]],
  ["MATH 53","Linear Algebra","major","upper",["MATH 13"],"Morning",["Major"]],
  ["PHYS 33","Physics III","major","upper",["PHYS 32"],"Afternoon",["Major"]],
  ["AMTH 108","Probability and Statistics","major","upper",["MATH 53"],"Midday",["Major"]],
  ["ELEN 50","Electric Circuits","major","upper",["PHYS 32"],"Afternoon",["Major"]],
  ["COEN 21","Logic Design","major","upper",["COEN 12"],"Morning",["Major"]],
  ["COEN 79","OO Programming and Advanced Data Structures","major","upper",["COEN 12"],"Midday",["Major"]],
  ["COEN 20","Embedded Systems","major","upper",["COEN 21","COEN 79"],"Afternoon",["Major"]],

  ["ELEN 153","Digital IC Design","major","upper",["ELEN 50"],"Morning",["Major"]],
  ["COEN 171","Programming Languages","major","upper",["COEN 79"],"Midday",["Major"]],
  ["ENGL 181","Engineering Communications","core","upper",["CTW 2"],"Afternoon",["University Core","Core"]],
  ["COEN 177","Operating Systems","major","upper",["COEN 79"],"Morning",["Major"]],
  ["COEN 146","Computer Networks","major","upper",["COEN 79"],"Midday",["Major"]],
  ["COEN 179","Algorithms","major","upper",["COEN 79","COEN 19"],"Afternoon",["Major"]],
  ["COEN 161","Computer Engineering Elective I","elective","upper",["COEN 20"],"Afternoon",["Computer Engineering Elective","Elective"]],
  ["COEN 168","Computer Engineering Elective II","elective","upper",["COEN 20"],"Morning",["Computer Engineering Elective","Elective"]],
  ["COEN 181","Computer Engineering Elective III","elective","upper",["COEN 20"],"Midday",["Computer Engineering Elective","Elective"]],

  ["COEN 174","Software Engineering","major","upper",["COEN 79"],"Morning",["Major"]],
  ["COEN 175","Compilers","major","upper",["COEN 171"],"Midday",["Major"]],
  ["COEN 122","Computer Architecture","major","upper",["COEN 20"],"Afternoon",["Major"]],
  ["COEN 194","Senior Design I","major","upper",["COEN 174"],"Morning",["Major"]],
  ["COEN 195","Senior Design II","major","upper",["COEN 194"],"Midday",["Major"]],
  ["COEN 196","Senior Design III","major","upper",["COEN 195"],"Afternoon",["Major"]],
  ["UNIV 201","University Core Upper","core","upper",[],"Morning",["University Core","Core"]],
  ["UNIV 202","University Core Upper II","core","upper",[],"Midday",["University Core","Core"]],
  ["EE 1","Educational Enrichment Elective I","elective","upper",[],"Evening",["Educational Enrichment","Elective"]],
  ["EE 2","Educational Enrichment Elective II","elective","upper",[],"Evening",["Educational Enrichment","Elective"]],
  ["EE 3","Educational Enrichment Elective III","elective","upper",[],"Evening",["Educational Enrichment","Elective"]]
];

function makeSections(code: string, timeWindow: string) {
  const windows = {
    Morning: [["TR","09:00","10:40"],["MW","10:15","11:55"]],
    Midday: [["MW","12:00","13:40"],["TR","13:30","15:10"]],
    Afternoon: [["TR","15:15","16:55"],["MW","16:00","17:40"]],
    Evening: [["T","18:00","20:30"],["R","18:00","20:30"]]
  } as const;
  const instructors = ["Dr. Li","Prof. Nguyen","Dr. Morales","Prof. Allen","Dr. Yu","Prof. Kim"];
  return (windows[timeWindow as keyof typeof windows] ?? windows.Morning).map((slot, index) => ({
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
          create: (tagNames as string[]).map((tagName) => ({ requirementTagId: tagMap[tagName] }))
        },
        sections: {
          create: makeSections(code as string, timeWindow as string)
        }
      }
    });
  }

  await prisma.completedCourse.createMany({
    data: [
      { studentKey: "sample-student", code: "COEN 19", title: "Discrete Math", term: "Fall 2024", grade: "A" },
      { studentKey: "sample-student", code: "CTW 1", title: "Critical Thinking & Writing 1", term: "Fall 2024", grade: "A-" },
      { studentKey: "sample-student", code: "CTW 2", title: "Critical Thinking & Writing 2", term: "Winter 2025", grade: "A-" },
      { studentKey: "sample-student", code: "MATH 11", title: "Calculus I", term: "Fall 2024", grade: "A" },
      { studentKey: "sample-student", code: "MATH 12", title: "Calculus II", term: "Winter 2025", grade: "B+" },
      { studentKey: "sample-student", code: "MATH 13", title: "Calculus III", term: "Spring 2025", grade: "B+" },
      { studentKey: "sample-student", code: "CHEM 11", title: "Chemistry I", term: "Fall 2024", grade: "B" },
      { studentKey: "sample-student", code: "PHYS 31", title: "Physics I", term: "Winter 2025", grade: "B+" },
      { studentKey: "sample-student", code: "PHYS 32", title: "Physics II", term: "Spring 2025", grade: "B" },
      { studentKey: "sample-student", code: "COEN 10", title: "Introduction to Programming", term: "Fall 2024", grade: "A" },
      { studentKey: "sample-student", code: "COEN 11", title: "Advanced Programming", term: "Winter 2025", grade: "A-" },
      { studentKey: "sample-student", code: "COEN 12", title: "Data Structures", term: "Spring 2025", grade: "B+" },
      { studentKey: "sample-student", code: "ENGR 1", title: "Introduction to Engineering", term: "Fall 2024", grade: "A" }
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
