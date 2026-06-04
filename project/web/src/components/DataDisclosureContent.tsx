type DataDisclosureContentProps = {
  showDeleteDataLink?: boolean;
};

const DELETE_USER_DATA_HREF = "/?delete-user-data=1";

export function DataDisclosureContent({ showDeleteDataLink = false }: DataDisclosureContentProps) {
  return (
    <div className="mx-auto max-w-prose space-y-6 text-sm leading-relaxed text-neutral-700 sm:text-base sm:leading-7">
      <section>
        <h1 className="mb-2 font-semibold text-[var(--scu-text)]">What Data is Stored</h1>
        <ul className="list-disc space-y-1 pl-5 text-neutral-600">
          <li>
            <strong>Academic Progress Data</strong>  Remaining course requirements parsed
            from uploaded Academic Progress reports. Names and grades are stripped
            before storing.
          </li>
          <li>
            <strong>Course Plan Snapshots</strong>  Generated Schedules are stored for your future reference and use.
          </li>
          <li>
            <strong>Preferences and Notes</strong>  Summaries of scheduling preferences
            you share in the chat are stored for future recommendations.
          </li>
          <li>
            <strong>Google Account Identifier</strong>  Google Account identifier stored for account association.
          </li>
        </ul>
      </section>

      <section>
        <h1 className="mb-2 font-semibold text-[var(--scu-text)]">How your Data is Processed</h1>
        <p className="text-neutral-600">
          Course planning requests, including your remaining requirements and stated preferences,
          are processed using Google's Gemini API to generate recommendations.
        </p>
      </section>

      <section>
        <h2 className="mb-2 font-semibold text-[var(--scu-text)]">Retention and deletion</h2>
        <p className="text-neutral-600">
          Your data is retained on our servers for as long as you use the app. You can
          permanently delete all stored data at any time by clicking{" "}
          {showDeleteDataLink ? (
            <a
              href={DELETE_USER_DATA_HREF}
              className="font-semibold text-[var(--scu-red)] underline-offset-2 hover:underline"
            >
              Delete User Data
            </a>
          ) : (
            <strong>Delete User Data</strong>
          )}
          .
        </p>
      </section>
    </div>
  );
}
