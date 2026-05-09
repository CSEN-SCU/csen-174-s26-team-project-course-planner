# Topic statement

Signed-in users are identified through a cookie-backed login flow backed by a local relational store holding usernames, emails, password hashes.

# Scope

- Covers account creation, password validation, login rendering, session cookie handling, logout, and clearing planner-related transient state on logout.
- Excludes schedule generation, file uploads, and any per-user memory beyond the keys explicitly cleared at logout.

# Data contracts

- **User record:** numeric identifier, non-empty username, email-shaped string, stored password verifier string, creation timestamp string.
- **Credentials bundle consumed by the login component:** mapping from username to display name, email, stored verifier (pre-hashed form accepted by that component).
- **Browser session fields after success:** authentication outcome flag, username string, numeric user identifier mirrored into the interactive session for downstream scoping.
- **Environment:** optional secret used to sign the session cookie; when unset, a fixed placeholder string is used.

# Behaviors (execution order)

1. On each protected view entry, the persistence layer is brought up to date (tables created or altered idempotently) before any credential read.
2. A single login component instance is reused for the whole browser session to avoid duplicate embedded components that would crash the runtime.
3. Login and registration appear as two peer tabs; until authentication succeeds, the registration tab can submit a new account form.
4. Registration validates username pattern length and character set, email shape, minimum password length, password confirmation match, then inserts a row; on success the cached login component is discarded so the next run reloads credentials.
5. The login tab delegates username and password checking to the login component; certain component-level login failures surface as an error line.
6. When the component reports failure, an incorrect-credentials message is shown in the login tab.
7. When the component reports unknown state, an informational prompt appears on the login tab and the registration tab remains available; the rest of the application does not render.
8. When the component reports success, the username from session is resolved to a full user row; numeric id and username are written into the interactive session and the user record is returned to the host view.
9. If the username no longer exists in the store (for example the account was removed while a cookie remained), the session is logged out silently, user-scoped keys are cleared, and the flow returns to unauthenticated.
10. The sidebar shows the signed-in username and a logout control that reuses the same cached login component instance.

# Error paths

- Registration with mismatched passwords shows an error and stops without writing.
- Registration violating username, email, or password rules shows the validation message from the store layer.
- Registration colliding on username or email uniqueness shows a taken-account message.
- Component-level login errors show the exception text.
- Failed login shows a generic incorrect-credentials message (distinct from component-level errors).
- Logout invokes the component logout hook inside a broad catch; failures there are ignored and local session keys are still cleared, then the cached component is discarded and the page reloads.
