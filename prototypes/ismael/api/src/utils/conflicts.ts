import { toMinutes } from "./time.js";

export interface ConflictCandidate {
  courseCode: string;
  days: string;
  startTime: string;
  endTime: string;
}

function sameDay(a: string, b: string) {
  return a === b;
}

export function rangesOverlap(aStart: string, aEnd: string, bStart: string, bEnd: string) {
  return toMinutes(aStart) < toMinutes(bEnd) && toMinutes(bStart) < toMinutes(aEnd);
}

export function findConflicts(items: ConflictCandidate[]) {
  const warnings: Array<{ courseCode: string; conflictsWith: string }> = [];
  for (let i = 0; i < items.length; i += 1) {
    for (let j = i + 1; j < items.length; j += 1) {
      if (sameDay(items[i].days, items[j].days) && rangesOverlap(items[i].startTime, items[i].endTime, items[j].startTime, items[j].endTime)) {
        warnings.push({ courseCode: items[i].courseCode, conflictsWith: items[j].courseCode });
      }
    }
  }
  return warnings;
}
