# Project knowledge for the ci-green loop

## How to run / verify
- Install: `pip install -e ".[dev]"`
- Test (this is the verify step): `pytest -q`

## Conventions
- Keep changes minimal; one fix per iteration.
- Match the existing style; do not reformat untouched files.

## Do NOT touch
- `dist/`, `build/`, anything generated.
- CI credentials or workflow secrets.

## Known landmines
- The lowest CI Python version is the real gate — don't use syntax newer than it.
