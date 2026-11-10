# Notes for AI assistants (Claude Code and similar)

People using this project are often designers, not developers. Keep
explanations plain and avoid jargon.

- **Setup:** run `venv/bin/python engine/setup_wizard.py` (interactive), or
  edit the "YOUR SEARCH" section of `config.yaml` for them. If `venv/` is
  missing, run `bash install.sh` with `JOBSEARCH_SOURCE_DIR=.` set to install
  from this folder.
- **Run:** `venv/bin/python engine/main.py --dry-run` previews and changes
  nothing; without `--dry-run` it adds new jobs to the tracker.
- **Personal files** (`config.yaml`, `portfolio_notes.md`, `.env`,
  `applications.csv`, `drafts/`) are gitignored. Never commit them or paste
  their contents anywhere outside this computer.
- **Tests:** `venv/bin/pip install pytest` (once), then `venv/bin/python -m pytest -q`. If you change filter rules,
  add a test in `tests/test_sources.py`.
- **Company lists:** `venv/bin/python engine/check_boards.py` checks every
  company in `config.yaml` and says which ones are on the wrong list or
  have the wrong name.
