# Configuration and API reference

## Defaults and optional public preferences

No settings file or course guide is required. A fresh script uses `gemini-3.1-flash-lite`, permits reads and writes throughout the project, requires confirmation for existing-file changes and disables deletion. Files are inspected on demand, not uploaded in bulk.

`python ceu-api.py --configure` chooses a model and optional instructions, then embeds public preferences in `SHARED_PREFERENCES` near the top of the same script. Share that script with students. Credentials are never embedded; they stay in each user's local `.ceu/config.json`. The previous script is backed up before updating its preferences.

For advanced use, an optional `ceu-ai.json` beside the script overrides its embedded defaults. Omitted fields use the embedded preference or built-in default. This allows existing 0.1.0 settings to keep working. `--configure` updates a pre-existing settings file too, avoiding a stale model override. The optional `--guide` wizard creates a settings file and an AI-drafted `harness.md`.

This example restricts a reading seminar to selected folders. Such restrictions are optional:

```json
{
  "title": "Reading seminar",
  "model": "gemini-3.1-flash-lite",
  "context_paths": ["materials"],
  "data_paths": [],
  "output_paths": ["work"],
  "exclude_paths": ["materials/instructor-notes"],
  "write_mode": "confirm",
  "allow_delete": false,
  "version": 1
}
```

Use a model name returned by your account's API catalogue. The example is not a guarantee of availability, quality or price.

| Setting | Meaning |
| --- | --- |
| `title` | Course/project name displayed in the terminal and sent with requests |
| `model` | Exact CEU `modelName` used for guide generation and chat |
| `instructions` | Optional project instructions, saved in the script by `--configure`; empty by default |
| `context_paths` | Files or folders the model may read; folder permissions include descendants |
| `data_paths` | Approved CSV files whose schemas are supplied automatically on each request |
| `output_paths` | Folders where the model may create and change files; these are also readable |
| `exclude_paths` | Additional files or folders excluded from reading and writing |
| `write_mode` | `confirm` shows diffs before existing-file changes; `automatic` applies them with backups |
| `allow_delete` | Whether individual-file deletion is permitted; the model is instructed to require an explicit user request |
| `version` | Settings format version, currently the integer `1` |

Paths use forward slashes relative to the project root containing `ceu-api.py`, including on Windows. The optional `--guide` wizard accepts comma-separated paths; Enter keeps the displayed default and `-` clears it. `.` permits the whole filtered project and is the default for both context and output paths. Automatically profiled datasets must be inside `context_paths` and outside exclusions.

An optional `harness.md`, if present and not excluded, is supplied with requests. It can add subject, audience and teaching instructions, but cannot expand permissions enforced by the program. It is not needed for startup or model selection. Course rules are guidance for the model, not a guarantee of compliance. Settings and the program are editable by the person running them, so they do not enforce institutional policy or account limits against a determined user.

Only the optional `--guide` wizard sends setup answers to the model. It reads selected `.md` and `.txt` **file paths** as reference text. Selecting a folder supplies its permitted path listing, not all its contents. Selected CSV profiles include column names, inferred types and row counts, without values. Normal startup and `--configure` use the model catalogue but make no chat-generation requests.

## What is sent to CEU

Each chat call sends the application instructions plus a JSON description of:

- The latest request and in-memory conversation history.
- Public course settings and the current guide.
- A filtered tree of permitted paths, capped at 400 entries.
- Automatically selected CSV schemas, without previews.
- Explicitly shared or model-requested file contents. CSVs contribute a schema and up to five preview rows. Notebooks contribute saved text, including outputs. PDFs contribute locally extracted text with page numbers.
- Any previous read errors or the rejected response needed for a correction.

Previously shared files are refreshed from disk on each user request. Successfully generated files join the context for follow-up requests. Long conversations resend history and can increase input-token usage; `/new` starts fresh. Requests stay in memory locally, but this says nothing about CEU/provider retention. Confirm data handling requirements with CEU IT.

The client ID and secret go in authentication headers, not the model prompt. The tool refuses to send the saved credential values if they appear in context and refuses to display or save them if returned by the model. This is not a general detector of every possible secret in a file.

## File protections and recovery

All ordinary project folders and UTF-8 text formats are accessible by default, including `.github`, `.vscode`, files without extensions, and course folders such as `grading` or `exams`. Add optional exclusions if you do not want them available. `AGENTS.md` and `CLAUDE.md` can be read as project text; they do not gain authority to override the user's request or application rules.

The program rejects paths outside the project, traversal, symbolic links, credential-like names, `.env` files, Git internals, its local `.ceu` folder, caches and environment directories. It blocks model changes to the app, guide, settings, `.gitignore` and protected dependency files. PDFs and existing CSV files are read-only. There is no special restriction on a folder simply because it is called `data/raw`. Export Word and other unsupported formats to text.

PDF extraction runs locally with a timeout. Page numbers count from the first page of the file. Images and scans without a text layer require OCR or a text copy. A PDF with both text and image-only pages supplies its available text, with a marker for each page with no extractable text. For encrypted or damaged files, use an unlocked copy or export a fresh PDF.

An existing file must be read before the model can revise or delete it. The application validates the proposed batch before changes, detects editor changes made while the response or confirmation was pending, and saves originals under `.ceu/backups/`. A declined review cancels the whole proposed batch, including any new files. New-file-only proposals are saved without a confirmation.

Backups are local copies, not a substitute for your usual version control. If a disk or permission error occurs during saving, changes already reported can remain applied; a batch is not a filesystem transaction. Restore originals from the backup location printed in the terminal. The application never deletes a whole directory.

## API calls and budgets

This release calls `https://ceu-api.academic-ai.at` directly:

| Request | Use |
| --- | --- |
| `GET /api/v1/llm/models` | Validate access and obtain `data[].modelName` |
| `POST /api/v1/llm/chat` | Send `model` and a `messages` array with one user message containing the application instructions and request context |

Authentication uses `X-Client-ID` and `X-Client-Secret`. Responses use CEU's `data.content`, `data.finishReason` and `data.usage` fields. Usage reporting adds `promptTokens` and `completionTokens` from **every returned response**, including inspection and correction calls. Calls without valid usage are marked as unavailable; displayed totals then cover only the known usage. Model catalogue requests are not counted as chat calls. No assumption is made about whether CEU charges for catalogue requests.

The script does not use OpenAI-compatible endpoints, OAuth, a class proxy, internet-search APIs or Tailored AI document storage. The API URL is fixed in this release to avoid sending saved credentials to an arbitrary host through course configuration. Redirects are refused.

One user prompt makes at most **four chat calls**, allowing up to three inspection rounds and at most one correction within that limit. Each inspection round can request four files. First-time guide drafting uses one call, with one correction call if needed. There are no automatic retries for HTTP errors or timeouts; a timed-out request may still be processed and charged by CEU.

Local usage is informational. It is not a billing statement, course-wide aggregation, a persistent log, or a hard spending cap. Ask CEU IT to set the allowance and account-side limits. Do not treat the Academic AI web allowance as API credit. Model selection and a limited number of calls help control usage, but this release does not set a provider output-token cap or manage model-specific reasoning settings.

### Current local limits

| Limit | Value |
| --- | --- |
| Combined instructions and request context | 200,000 UTF-8 bytes, not tokens |
| Course guide | 16,000 UTF-8 bytes |
| API response body | 500,000 bytes |
| CSV read locally for profiling | 10,000,000 bytes |
| CSV preview | First 5 rows; each text value truncated after 200 characters |
| PDF read locally | 20 MB and 150 pages per PDF |
| PDF extract | 100,000 UTF-8 bytes and a 12-second parser timeout per PDF |
| Proposed writes/deletions in one reply | 12 files |
| Network timeout | 120 seconds |

These are application limits, not statements about CEU's model context windows or account quotas. A response that exceeds a limit is rejected, but it may still incur API usage.

## Credentials and updates

`.ceu/config.json` contains `client_id` and `secret`. It is stored locally, unencrypted. On Unix-like systems the credential file receives mode `0600` and `.ceu` mode `0700`; on Windows protection depends on the user's account and folder permissions. Imported credentials receive the same file-mode treatment where supported. Keep shared credentials on an approved private course platform and never place actual values in the guide, settings, source code or Git history.

`--setup` replaces credentials only after checking the model catalogue. `--credentials PATH` imports the same JSON format and adds an exact ignore rule if the imported file is inside the project. A local import does not remove an earlier Git commit of that file. `--configure` embeds public model/instruction preferences in the script; `--guide` creates the optional guide and advanced settings. Both retain backups when replacing files.

Releases are versioned. `python ceu-api.py --version` prints the installed version. Updating the script is a deliberate instructor action; there is no automatic download during class. A fresh generic script does not retain your embedded preferences: keep the previous script, then reapply the desired public settings before distribution.
