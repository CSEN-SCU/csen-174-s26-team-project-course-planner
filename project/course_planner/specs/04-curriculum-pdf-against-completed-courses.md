# Topic statement

A standalone callable sends a major-requirements document as binary content together with a finished-course code list to a hosted language model that returns structured gap fields.

# Scope

- Covers only the module that accepts PDF bytes plus completed course strings; it is not invoked by the main interactive application entrypoint in this repository state.
- Excludes workbook-based gap extraction and schedule generation.

# Data contracts

- **Inputs:** PDF byte sequence; list of strings naming completed courses.
- **Output object (JSON-shaped):**
  - `completed`: array of strings (requirements judged satisfied).
  - `missing`: array of strings (requirements still required).
  - `missing_details`: array of objects each requiring string `course`, string `category`, integer `units`.
- **Model selection:** overridden by an environment variable when set, otherwise a fixed default model id string bundled in code.

# Behaviors (execution order)

1. Lazily construct a default client for the vendor SDK on first use (no explicit API key wiring in this module; relies on ambient SDK configuration).
2. Serialize the completed list as JSON text embedded in the textual instruction.
3. Send multipart content consisting of the PDF as an application/pdf part plus the instruction string.
4. Request generated content constrained to JSON matching the declared response schema, with a large output token budget.
5. Read the first text payload from the response; if empty, raise a value error.
6. Strip optional fenced code-block wrappers then parse as JSON and return the object.

# Error paths

- Empty model text raises a value error.
- Invalid JSON after stripping raises the parser’s error outward.
- Network, quota, or SDK failures propagate uncaught from the generation call.
- Schema violations from the model would surface as parse or validation errors depending on SDK behavior.
