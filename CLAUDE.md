# Agent instructions

This file is for coding agents working on this repo. `CLAUDE.md` and `GEMINI.md` are copies of it; keep all three the same.

## Standing rules

- **Remote-first.** Work in a cloud checkout of the GitHub repo and keep its default branch up to date. Do not depend on the user's PC; the user runs `git pull` when they want to test locally.
- **Clean up after every merge.** Delete the PR's branch (local and remote) and any worktree it used. If GitHub refuses the delete, tell the user the exact command to run.

## What this repo is

The add-licensing skill and everything it uses:

- `SKILL.md`: the skill. To add licensing to another project, follow it step by step. It keeps the target project's record in `licensing/licensing.md`.
- `SPEC.md`: the formats every part must follow (license file, key list, online check reply, cache file).
- `README.md`: setup, server deploy, issuing and managing licenses, verifier usage.
- `app/`: the online check server (FastAPI). `app/keysource.py` reads the signing key for the issuer scripts.
- `issue_license.py`, `license_admin.py`, `purge_expired.py`, `regenerate_licenses.py`, `sign_keylist.py`, and their `admin/*.bat` / `admin/*.sh` wrappers.
- `verifiers/`: Python, Node.js, Rust and Dart (untested) verifiers, with the shared fixtures `verifiers/cases.json` and `verifiers/online-replies.json`.
- `samples/`: plan and gate checks and server-side gates. `templates/licenses/`: license texts the skill copies into projects.

## Rules for changes

- **Keep the docs in step with the code.** In the same change, update every doc the change shows in: `README.md`, `SKILL.md` (and its `licensing/licensing.md` template), `SPEC.md`, `samples/README.md`, `templates/licenses/README.md`, `docs/licensing-skill-flow.html` and `CONTRIBUTING.md`.
- **One rule, every verifier.** A change to a format or a verification rule goes into all verifiers, `SPEC.md` and the shared fixtures together (`tests/make_cases.py` regenerates `verifiers/cases.json`).
- **Never commit keys or deployment files.** Private keys, `.env`, `keys.json`, `keylist.json`, `root-public.pem`, `app/root-public.pem`, issued licenses and cache files are gitignored on purpose.
- **Plans:** `opensource`, `subscription`, `gated`. `full` is a legacy alias of `subscription`: keep it verifying, never offer it.
- **Not a feature:** machine binding (node-locked licenses) is not implemented. Don't document it as one.
- **Tests:** `pytest -q` (in a venv with `requirements.txt`), `node --test tests/node/test.js`, and `cargo test` in `verifiers/rust/`.
- **Commits:** sign off every commit (`git commit -s`); the DCO check fails pull requests without it. The repo is Apache-2.0 (see `CONTRIBUTING.md`).
