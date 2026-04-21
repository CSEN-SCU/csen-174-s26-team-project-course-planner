import type { CourseResult } from "../types/domain";

export function CourseTable({
  courses,
  onSelect,
  onRefresh
}: {
  courses: CourseResult[];
  onSelect: (course: CourseResult) => void;
  onRefresh: () => void;
}) {
  return (
    <article className="glass soft-scroll overflow-auto rounded-2xl p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-xl text-white">Eligible courses</h2>
        <button className="rounded-lg border border-slate-400 px-3 py-1 text-xs text-slate-200" onClick={onRefresh}>
          Refresh ranking
        </button>
      </div>
      {courses.length === 0 ? (
        <p className="text-sm text-slate-300">No courses yet. Try adjusting filters and refresh.</p>
      ) : (
        <table className="w-full table-fixed border-collapse text-left text-xs text-slate-100">
          <thead className="text-slate-300">
            <tr>
              <th className="pb-2">Course</th>
              <th className="pb-2">Avg diff</th>
              <th className="pb-2">Quality</th>
              <th className="pb-2">Time</th>
              <th className="pb-2">Coverage</th>
              <th className="pb-2">Fit</th>
            </tr>
          </thead>
          <tbody>
            {courses.map((course) => (
              <tr
                key={course.id}
                onClick={() => onSelect(course)}
                className="cursor-pointer border-t border-slate-800/80 transition hover:bg-slate-900/40"
              >
                <td className="py-2 pr-3">
                  <p className="font-semibold text-sky-100">{course.code}</p>
                  <p className="text-slate-300">{course.name}</p>
                </td>
                <td>{course.avgDifficulty.toFixed(1)}</td>
                <td>{course.quality.toFixed(1)}</td>
                <td>{course.timeWindow}</td>
                <td>
                  <div className="flex flex-wrap gap-1">
                    {course.requirementTags.slice(0, 2).map((tag) => (
                      <span key={tag} className="rounded bg-slate-800 px-2 py-0.5">
                        {tag}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="font-semibold text-mint">{course.fitScore}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </article>
  );
}

