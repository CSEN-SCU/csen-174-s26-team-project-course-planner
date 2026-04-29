export function toMinutes(value: string): number {
  const [hours, minutes] = value.split(":").map(Number);
  return hours * 60 + minutes;
}

export function formatRange(startTime: string, endTime: string): string {
  return `${startTime}-${endTime}`;
}
