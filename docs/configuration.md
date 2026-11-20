# Configuration and API reference

## Public course settings

The instructor wizard creates `ceu-ai.json` beside the script. This example describes a reading seminar; change the paths and model for your own project:

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
| `context_paths` | Files or folders the model may read; folder permissions include descendants |
| `data_paths` | Approved CSV files whose schemas are supplied automatically on each request |
| `output_paths` | Folders where the model may create and change files; these are also readable |
| `exclude_paths` | Additional files or folders excluded from reading and writing |
| `write_mode` | `confirm` shows diffs before existing-file changes; `automatic` applies them with backups |
| `allow_delete` | Whether individual-file deletion is permitted; the model is instructed to require an explicit user request |
| `version` | Settings format version, currently the integer `1` |

Paths use forward slashes relative to the folder containing `ceu-ai.py`, including on Windows. The wizard accepts comma-separated paths; Enter keeps the displayed default and `-` clears it. Paths containing commas can be entered later by editing the JSON. `.` explicitly permits the whole filtered project for that setting; choosing specific folders gives more control. Automatically profiled datasets must be inside `context_paths` and outside exclusions.

`harness.md` is always supplied unless excluded. It contains the subject, audience and teaching instructions. It cannot expand permissions enforced by the program. Course rules are guidance for the model, not a guarantee of compliance. Settings and the program are editable by the person running them, so they do not enforce institutional policy or account limits against a determined user.

During setup, selected `.md` and `.txt` **file paths** are read as reference text. Selecting a folder supplies its permitted path listing, not all its contents. Selected CSV profiles include column names, inferred types and row counts, without values. After setup, the model can request relevant files within the permitted scope.

## What is sent to CEU

Each chat call sends the application instructions plus a JSON description of:

- The latest request and in-memory conversation history.
- Public course settings and the current guide.
- A filtered tree of permitted paths, capped at 400 entries.
- Automatically selected CSV schemas, without previews.
- Explicitly shared or model-requested file contents. CSVs contribute a schema and up to five preview rows; notebooks contribute their saved text, including outputs.
- Any previous read errors or the rejected response needed for a correction.

Previously shared files are refreshed from disk on each user request. Successfully generated files join the context for follow-up requests. Long conversations resend history and can increase input-token usage; `/new` starts fresh. Requests stay in memory locally, but this says nothing about CEU/provider retention. Confirm data handling requirements with CEU IT.

The client ID and secret go in authentication headers, not the model prompt. The tool refuses to send the saved credential values if they appear in context and refuses to display or save them if returned by the model. This is not a general detector of every possible secret in a file.

## File protections and recovery

The program rejects paths outside the project, traversal, symbolic links, hidden files/folders, credential-like names, common private/grading/exam folders and environment directories. It blocks changes to the app, guide, settings and protected dependency files. Existing CSV files and `data/raw` are read-only; raw data reads are limited to CSV summaries. `AGENTS.md` and `CLAUDE.md` are local-only and are not supplied as model instructions.

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
| Proposed writes/deletions in one reply | 12 files |
| Network timeout | 120 seconds |

These are application limits, not statements about CEU's model context windows or account quotas. A response that exceeds a limit is rejected, but it may still incur API usage.

## Credentials and updates

`.ceu/config.json` contains `client_id` and `secret`. It is stored locally, unencrypted. On Unix-like systems the credential file receives mode `0600` and `.ceu` mode `0700`; on Windows protection depends on the user's account and folder permissions. Imported credentials receive the same file-mode treatment where supported. Keep shared credentials on an approved private course platform and never place actual values in the guide, settings, source code or Git history.

`--setup` replaces credentials only after checking the model catalogue. `--credentials PATH` imports the same JSON format and adds an exact ignore rule if the imported file is inside the project. A local import does not remove an earlier Git commit of that file. `--configure` changes public course setup and keeps previous setup files in local backups.

Releases are versioned. `uv run ceu-ai.py --version` prints the installed version. Updating the script is a deliberate instructor action; there is no automatic download during class.
