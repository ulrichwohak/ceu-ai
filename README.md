# CEU AI for course and project folders

Ask questions in your terminal and let CEU's AI read selected materials and create or revise files in your project. Works from the VS Code terminal or another terminal, with one Python file and no class server to maintain.

The first run helps the instructor create a course guide and choose the model, permitted folders and file-change policy. Students receive that setup with the course and enter their credentials once. The guide can describe any subject: a reading seminar, a research project, a programming class, or another course.

This is an independently maintained teaching tool, not an official CEU IT product.

## Start a course or project

1. Obtain a CEU **API** client ID and secret, permission to use the chosen model, and an API allowance from CEU IT. Confirm any campus Wi-Fi or VPN requirements for your account. An Academic AI website allowance is separate from an API budget.
2. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) once, then reopen your terminal. If `uv --version` already works, skip this step.
3. Download **[ceu-ai.py from the latest release](https://github.com/ulrichwohak/ceu-ai/releases/latest/download/ceu-ai.py)** into the top level of your existing course or project folder. You do not need to clone this tool's repository into the course.
4. Open that folder in VS Code, open **Terminal → New Terminal**, and run:

   ```sh
   uv run ceu-ai.py
   ```

5. Choose **1** to set up a course/project. Enter the client ID and secret; secret input is hidden. Answer the setup questions about your audience, tasks, materials, output folders and model. Review the generated guide before accepting it.

uv manages the script's Python dependencies in its own environment. The first launch needs internet access to download them; it can also download a suitable Python version. Python 3.11 or later is required. See [uv's script guide](https://docs.astral.sh/uv/guides/scripts/) for how this works.

For example, approve `materials` for reading and `work` for writing. Then ask:

```text
Read materials/overview.md and create work/discussion-questions.md
with five questions grounded in that text.
```

Or, in a course using data:

```text
Inspect materials/survey.csv and create work/exploration.ipynb
with documented Python code for exploring it. Do not invent results.
```

The assistant saves files locally. It does **not** execute generated code. Review and run code yourself using the course's normal environment.

## Share it with students

Commit these three files to the course repository, along with the updated `.gitignore`:

| File | Purpose |
| --- | --- |
| `ceu-ai.py` | The reusable terminal application |
| `ceu-ai.json` | Course title, model, permitted paths and file-change policy |
| `harness.md` | Editable instructions describing the course and its working rules |

After students pull the course repository, they run the same command:

```sh
uv run ceu-ai.py
```

On their first run they enter the credentials supplied privately by the instructor; later runs reuse them. They do not need to create their own course guide. If the course files are missing, choosing the student option explains which files to obtain instead of starting the instructor wizard.

Keep **`.ceu/` and downloaded credential files out of Git**. The application adds ignore rules before saving credentials. It stores credentials in `.ceu/config.json` locally, in plain text, with owner-only permissions on systems that support them. Git ignore rules do not remove files that have already been committed.

For a class using shared credentials, distribute a file called **`ceu-credentials.json`** through an authenticated course platform, using a method approved by CEU. Its format is:

```json
{
  "client_id": "REPLACE_WITH_CLASS_CLIENT_ID",
  "secret": "REPLACE_WITH_CLASS_CLIENT_SECRET"
}
```

Students can download it into the course folder and import it once:

```sh
uv run ceu-ai.py --credentials ceu-credentials.json
```

After successful import, they can delete the downloaded copy. The local `.ceu/config.json` remains. This keeps credentials out of the public repository; students receiving them can still read and use them. A direct-to-CEU tool cannot conceal shared credentials from its users or enforce individual account budgets. Arrange sharing, limits, expiry and replacement with CEU IT.

## Everyday use

Type a request and press Enter. Pasted multiline prompts are accepted as one input. Each completed request reports the tokens returned by CEU, including additional inspection or correction calls.

| Command | What it does |
| --- | --- |
| `/context` | Preview the guide and automatic CSV schemas locally, without an AI request |
| `/tree` | Show the permitted file paths |
| `/add materials/reading.md` | Include a permitted file with the next request |
| `/drop materials/reading.md` | Exclude a file or folder for the rest of this session |
| `/new` | Clear conversation and shared files, keeping session exclusions |
| `/usage` | Show reported tokens for this running session |
| `/quit` | Exit |

The model can request relevant files from the permitted folders; the terminal reports each read. The course guide, permitted paths and selected CSV schemas accompany requests automatically. CSV reads supply a schema and at most five preview rows, not the whole dataset. Text and notebook reads include their saved contents, including any saved notebook outputs. Only approve materials you are allowed to send through the API. `/new` and `/drop` cannot recall data already sent.

New files are saved directly in the configured output folders. By default, replacing or deleting an existing file requires reviewing a diff. An instructor can choose automatic changes instead. Both modes back up originals under `.ceu/backups/`; deletion is disabled unless explicitly enabled. Restore a file by copying the original from the reported backup folder to its previous location.

## Adapt the course setup

Edit `harness.md` directly for changes to subject, style or teaching rules. Edit `ceu-ai.json` for paths and policy, then restart the assistant. For guided reconfiguration or to resume an unfinished setup:

```sh
uv run ceu-ai.py --configure
```

The setup prompt is built into the program; colleagues do not need another AI subscription or coding assistant to generate the guide. A readable copy is in [SETUP_PROMPT.md](SETUP_PROMPT.md). If you decline the draft, edit `.ceu/harness-draft.md` and run `--configure` again to resume. Previous accepted setup files are backed up when replaced.

Model choices come from the authenticated CEU API catalogue. Setup offers `gemini-3.1-flash-lite` as a default **only when that exact model is available**; check suitability and current rates with CEU IT. The selected model is recorded explicitly and unavailable models are never silently substituted. See the [configuration and API reference](docs/configuration.md) for settings, capabilities and usage limits.

## Scope of this first release

Supported reading formats are UTF-8 text, Markdown, CSV, Python notebooks and source files (`.py`, `.r`, `.sql`, `.tex`, `.jl`, `.js`, `.ts`, `.html`, `.css`), plus `pyproject.toml`. The assistant writes text files and Python notebooks. Python syntax and notebook structure are checked before saving; other languages are saved as text without syntax validation.

There is no shell, code execution, package installation by the model, web search, image inspection, or PDF/Word/PowerPoint conversion. Export relevant document passages to text or Markdown first. Notebook code must be ordinary Python; notebook-specific magic commands are not supported by the syntax checker.

The tool is a small folder assistant, not a full coding agent. Prompts can request up to four model calls to inspect files and correct a response. It does not persist chat history between runs, provide central usage accounting, or guarantee the accuracy of generated material.

## Troubleshooting and updates

- **`uv` not found:** finish the uv installation and reopen the terminal.
- **Wrong working folder:** run from the directory containing `ceu-ai.py`.
- **Credentials expired or rejected:** run `uv run ceu-ai.py --setup` with new credentials. A failed credential check preserves the previous local credential file.
- **Cannot connect:** check the API address/network requirements with CEU IT, including campus Wi-Fi/VPN where required.
- **Model unavailable:** the instructor should run `--configure` and select an available model.
- **Context or response too large:** use `/new`, `/drop`, or a more focused request.
- **Invalid response:** the app can make one correction attempt within the four-call limit. If that fails, nothing from that proposal is saved.

To update, replace `ceu-ai.py` with a reviewed release, keeping the course's guide and settings. There is no automatic update during class. Check the [changelog](CHANGELOG.md) before distributing an update. Do not overwrite a locally customised script without retaining your changes.

## Development

Clone this repository, then run:

```sh
uv sync --locked
uv run python -m unittest discover -s tests -v
```

The automated tests use temporary folders and mock API responses; they require no credentials and make no paid requests. CI runs on Linux, macOS and Windows with Python 3.11 and 3.13. Direct script dependencies are pinned; `uv.lock` also locks the development environment. Course users only need the single script, whose transitive dependencies are resolved by uv.

MIT licensed. See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
