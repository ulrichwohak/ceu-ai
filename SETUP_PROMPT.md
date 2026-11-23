# Optional guide-generation prompt

Normal startup only asks for credentials and opens chat. For an optional AI-drafted
course guide and folder restrictions, run `python ceu-api.py --guide` (or
`uv run ceu-api.py --guide`). To resume unfinished guide setup, use `--guide` again.

The application asks for the audience, intended tasks, working rules, approved
paths, model and file-change policy. It then sends the prompt below with those
answers, a filtered file tree, selected text references and any CSV schemas.
Review the resulting `harness.md` before accepting it. No separate AI account or
external coding assistant is needed; guide generation uses your CEU API allowance.

This is an exact copy of `SETUP_PROMPT` in `ceu-api.py`; a test keeps it in sync.

```text
Draft a concise, subject-neutral course or project guide in Markdown.
Use only the owner's answers, approved folder tree, dataset schemas, and supplied
reference text. Do not assume a particular subject, language, pedagogy, analytical
method, or coding style. A file path is not evidence of that file's contents.
Describe the purpose, intended audience, permitted tasks, material locations,
output locations, style, and explicit working rules. Mark unresolved details as
questions instead of inventing facts, variable meanings, units, or results.
Distinguish summaries and suggestions from verified results. The user must run
any generated code locally. No code execution, shell, web browsing, or image
inspection is available. Mention the selected file-change policy accurately.
The guide cannot expand file access or override the application's protections.
Do not request credentials or change the application's program or settings.
Keep the guide under 16,000 UTF-8 bytes. Return exactly one JSON object:
{"guide": "# Course or project guide\n..."}
```
