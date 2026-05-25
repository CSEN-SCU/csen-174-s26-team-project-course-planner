export function DataDisclosureContent() {
  return (
    <div className="mx-auto max-w-prose space-y-6 text-sm leading-relaxed text-neutral-700 sm:text-base sm:leading-7">
      <section>
        <h2 className="mb-2 font-semibold text-[var(--scu-text)]">What we store</h2>
        <ul className="list-disc space-y-1 pl-5 text-neutral-600">
          <li>
            <strong>Academic Progress data</strong> — the remaining course requirements parsed
            from your uploaded Academic Progress xlsx. Names, grades, and GPA are stripped
            before storage; only course codes and completion status are kept.
          </li>
          <li>
            <strong>Course plan snapshots</strong> — the recommended schedules generated
            during your session, so you can review past plans.
          </li>
          <li>
            <strong>Preferences and notes</strong> — brief summaries of scheduling preferences
            you share in the chat (e.g. "prefer morning classes"), stored to improve follow-up
            recommendations.
          </li>
          <li>
            <strong>Google account identifier</strong> — a numeric user ID derived from your
            Google sign-in, used only to associate the data above with your account. Your
            Google email address is not stored on our servers.
          </li>
        </ul>
      </section>

      <section>
        <h2 className="mb-2 font-semibold text-[var(--scu-text)]">How your data is processed</h2>
        <p className="text-neutral-600">
          Course planning requests, including your remaining requirements and stated preferences,
          are sent to Google's Gemini AI models to generate schedule recommendations. Any
          personally identifiable information (emails, phone numbers, ID numbers) found in
          stored notes is automatically redacted before it reaches the model.
        </p>
      </section>

      <section>
        <h2 className="mb-2 font-semibold text-[var(--scu-text)]">Retention and deletion</h2>
        <p className="text-neutral-600">
          Your data is retained on our servers for as long as you use the app. You can
          permanently delete all stored data at any time — including your plan history,
          uploaded transcript information, and preferences — by clicking{" "}
          <strong>Delete user data</strong> in the footer of the main app. This action
          is immediate and irreversible.
        </p>
      </section>

      <section>
        <h2 className="mb-2 font-semibold text-[var(--scu-text)]">Disclaimer</h2>
        <p className="text-neutral-600">
          This tool is a student project and is not affiliated with or endorsed by Santa Clara
          University. Do not enter sensitive personal information beyond what is necessary for
          course planning.
        </p>
      </section>
    </div>
  );
}
