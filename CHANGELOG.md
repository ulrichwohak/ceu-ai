# Changelog

## 0.2.2 - 2026-11-23

- Running the script sets up missing Python packages in a local environment on first use.

## 0.2.1 - 2026-11-23

- Setup instructions and automated checks use standard Python and pip on Windows, macOS and Linux.
- The startup message gives a pip command when required packages cannot be imported.

## 0.2.0 - 2026-11-23

- Normal startup asks for credentials and opens chat; no role prompt, course guide or settings file is required.
- Project-wide file access by default, including ordinary hidden project folders and UTF-8 files with any extension. Credentials, Git internals, environments and caches remain excluded.
- Optional `--configure` saves a default model and instructions inside the single distributable script. Credentials stay in the local `.ceu` folder.
- The old guide/folder wizard is optional under `--guide`; existing explicit course settings remain supported.
- Main download renamed to `ceu-api.py`, with `ceu-ai.py` retained as an identical compatibility release asset.
- Setup supports plain Python and ordinary terminals.

## 0.1.0 — 2026-11-20

- Single-file terminal assistant for any course or project using CEU's AI API.
- Built-in instructor setup prompt, editable course guide, explicit model and folder permissions.
- Student startup reuses the shared course setup and saves credentials locally.
- Direct and private JSON credential import; hidden secret input and Git ignore rules.
- Bounded model-requested file reads, CSV profiles and notebook generation.
- Review or automatic file changes, backups, disabled-by-default deletion, and Python/notebook validation.
- Per-request and session usage reporting, including inspection and correction calls.
- Offline tests and Linux, macOS and Windows CI.
