export interface IcsItem {
  courseCode: string;
  courseName: string;
  days?: string | null;
  startTime?: string | null;
  endTime?: string | null;
  instructor?: string | null;
}

export function buildIcs(items: IcsItem[]) {
  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Bronco Plan//Course Planner Prototype//EN"
  ];

  items.forEach((item, index) => {
    const start = (item.startTime ?? "09:00").replace(":", "") + "00";
    const end = (item.endTime ?? "10:15").replace(":", "") + "00";
    lines.push(
      "BEGIN:VEVENT",
      `UID:bronco-plan-${index}@local`,
      `SUMMARY:${item.courseCode} ${item.courseName}`,
      `DESCRIPTION:Instructor ${item.instructor ?? "TBD"}`,
      `DTSTART:20260105T${start}`,
      `DTEND:20260105T${end}`,
      "END:VEVENT"
    );
  });

  lines.push("END:VCALENDAR");
  return lines.join("\r\n");
}
