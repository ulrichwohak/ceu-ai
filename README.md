# CEU AI for your project folder

Download one file, run it in a terminal, enter your CEU API credentials and start chatting. The assistant can read project files as needed and create or revise files locally. It works in an ordinary terminal and in editors such as VS Code.

There is no required course wizard, folder selection or separate guide. Project-wide access is the default. An instructor can optionally choose a default model and add instructions; those preferences are saved **inside the script**, so students only need that one file.

This is an independently maintained teaching tool, not an official CEU IT product.

## Start

[One-page getting-started guide (PDF)](docs/CEU-AI-Getting-Started.pdf)

1. Obtain a CEU API client ID, secret and API allowance from CEU IT. The Academic AI website allowance is separate from the API budget.
2. Download **[ceu-api.py](https://github.com/ulrichwohak/ceu-ai/releases/latest/download/ceu-api.py)** into the **root (top-level folder)** of your course or project.
3. Open a terminal in that folder and run the command below.
4. Enter the client ID and secret when prompted. Secret input is hidden. Later runs reuse your locally saved credentials.

Use Python 3.11 or later on Windows, macOS or Linux. If your Python command is `python3` or `py`, use it in place of `python`. An ordinary terminal or VS Code's **Terminal > New Terminal** works.

```sh
python ceu-api.py
```

This command sets up chat, PDF reading and the other file features together. If packages are missing, the script installs them under `.ceu/runtime` and continues automatically. The first package download needs internet access and a Python installation with `venv`.

Now type a request, for example:

```text
Read overview.md and create discussion-questions.md with five questions
grounded in that text.
```

The named source file must exist. You do not need to approve a list of filenames or choose an output folder first. The assistant reads relevant contents on demand; it does not upload the entire project at startup.

## Optional instructor preferences

To choose the model students will use and optionally add project instructions:

```sh
python ceu-api.py --configure
```

This lists the models available to your API account, asks for your choice and offers an optional instructions field. It makes no text-generation request. Press Enter to keep existing instructions or enter `-` to remove them.

The selected preferences are written into the `SHARED_PREFERENCES` block near the top of **that same script**. Your credentials remain separate in `.ceu/config.json`; they are never written into the shared script. A local backup preserves the previous script.

Share your configured `ceu-api.py` with students, either in the course repository or through the course platform. Students place it in the **root of their own project folder** and run it. They enter credentials once and inherit your model and instructions. They do not need to configure the course or download extra settings files.

Without instructor preferences, the default model is `gemini-3.1-flash-lite`. If it is unavailable for the account, the app stops with an explanation; it never silently switches models. Use `--configure` to choose another available model and confirm current rates with IT.

## What the assistant can access

By default, all project folders are in scope, including nested folders and ordinary hidden project files such as `.github/workflows/`.

### Supported file formats

| Format | What the assistant can read | What it can save |
| --- | --- | --- |
| UTF-8 text and source code, such as `.txt`, `.md`, `.py`, `.R`, `.json` and `.html` | File contents | New or revised files |
| Jupyter notebooks (`.ipynb`) | Saved notebook contents, including saved outputs | New or revised Python notebooks |
| CSV tables (`.csv`) | Column names, inferred types, row count and up to five preview rows | New CSVs. Existing CSVs are read-only. |
| PDFs (`.pdf`) | Selectable text with page numbers | Read-only |

To use a PDF, ask the assistant to read it by name or type `/add "readings/week 2.pdf"` in chat. The script extracts selectable text and page numbers locally and sends that text to CEU. Charts and images are outside the extract. For scans, use an OCR version or a text export. If a PDF exceeds the [local limits](docs/configuration.md#current-local-limits), export the pages you need as a smaller PDF.

Credentials, Git internals, virtual environments and caches are excluded. Paths outside the project and symbolic links are blocked. The application, its shared preferences, optional course configuration, `.gitignore` and protected dependency files cannot be overwritten by model replies.

File paths, optional instructions and the current conversation accompany requests. The terminal reports model-requested reads. Only use project material you are allowed to send through the API. The program detects its saved CEU credentials in context, but it is not a general detector of every kind of private information.

New files are saved directly. Replacing existing files requires a diff review by default and keeps originals in `.ceu/backups/`. The model must read an existing file before changing it. Deletion is disabled by default. Export Word, PowerPoint and other unsupported formats to text. Run generated code yourself.

## Useful commands

| Command | Purpose |
| --- | --- |
| `/help` | Show chat commands |
| `/tree` | Preview accessible paths locally |
| `/context` | Preview any optional guide and automatic CSV schemas |
| `/add path/to/file` | Include a file with the next prompt |
| `/drop path/to/file` | Exclude a file or folder for this session |
| `/new` | Clear conversation and shared files, keeping exclusions |
| `/usage` | Show reported token usage for this running session |
| `/quit` | Exit |

Each user request can make up to four model calls to inspect files and correct a response. Usage includes these calls; missing usage is flagged. Local totals are not a shared billing dashboard or a spending cap. Ask CEU IT to set account limits. `/new` and `/drop` cannot recall data already sent, and closing the app clears its local chat history.

## Keep credentials private

The local `.ceu/config.json` is plain text, excluded from Git, with owner-only file permissions on systems that support them. Ignore rules do not remove files that were previously committed.

If IT approves shared class credentials, distribute them through an authenticated course platform. Students who receive shared credentials can read and use them; this direct connection cannot hide credentials from its users or enforce individual budgets.

Optional file import uses a privately supplied `ceu-credentials.json`:

```json
{
  "client_id": "REPLACE_WITH_CLASS_CLIENT_ID",
  "secret": "REPLACE_WITH_CLASS_CLIENT_SECRET"
}
```

```sh
python ceu-api.py --credentials ceu-credentials.json
```

After successful import, delete the downloaded copy if desired; the local credential store remains. Replace expired credentials with `python ceu-api.py --setup`.

## Optional advanced setup

Folder restrictions, CSV profiles and an AI-drafted course guide are available **only if you want them**:

```sh
python ceu-api.py --guide
```

This optional wizard creates `harness.md` and `ceu-ai.json`. If you choose this route, share those files too. Existing files from version 0.1.0 remain supported and their explicit folder restrictions are preserved. An optional `ceu-ai.json` overrides the script's embedded defaults; `--configure` updates an existing settings file as well as the script so the selected model stays consistent.

You can also edit `SHARED_PREFERENCES` or provide an optional `harness.md` manually. See [configuration](docs/configuration.md) and the [optional guide-generation prompt](SETUP_PROMPT.md).

## Updates and development

Updating is deliberate: a fresh generic download does not contain your instructor customisations. Keep the previous script and reapply its public preferences before sharing an update. Version 0.1.0 used the filename `ceu-ai.py`; current releases also include that name as a compatibility download of the same application. Use `ceu-api.py` for new projects.

Activate a development environment and run the following commands from the repository root.

```sh
python -m pip install prompt-toolkit==3.0.52 nbformat==5.10.4 pandas==3.0.3 pypdf==7.1.1
python -m unittest discover -s tests -v
```

Tests use temporary folders and mock API responses; no credentials or paid calls are required. CI covers Linux, macOS and Windows on Python 3.11 and 3.13. MIT licensed; see [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
