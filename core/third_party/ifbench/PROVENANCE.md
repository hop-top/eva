# Provenance

- Upstream: https://github.com/allenai/IFBench (Apache-2.0)
- Commit: `488918665d53f867fa908a293769ec6e71e74aec` (main, 2026-11-13)
- Files: `ifbench/{instructions,classic_instructions,instructions_util,instructions_registry}.py`
- `classic_instructions.py` carries the IFEval verifiers (originally
  google-research/instruction_following_eval); `instructions.py` carries the
  IFBench out-of-distribution verifiers. `instructions_registry.INSTRUCTION_DICT`
  maps instruction ids (`category:name`) to verifier classes.

## Changes from upstream

1. Absolute imports `from ifbench import ...` became relative imports
   (`from . import ...`) in `instructions.py`, `classic_instructions.py`,
   `instructions_registry.py`.
2. `classic_instructions.py`: `from absl import logging` became stdlib
   `import logging` (only `logging.error` is used; avoids the absl-py dependency).
3. `instructions.py`: removed the import-time creation of a `.nltk_data`
   directory inside the package, the `NLTK_DATA` default and the
   `nltk.data.path.insert`. nltk data location is the caller's choice.
4. `instructions_util.py`: removed `download_nltk_resources()` and its
   import-time call (no implicit downloads). Data is fetched only by the
   explicit `eva data fetch` command.
5. Further edits, if any, are listed below.

## Updating

Replace the four files from a newer upstream commit, reapply the changes
above, update the commit here and in NOTICE.
