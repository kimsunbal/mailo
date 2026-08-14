# docs/pypi — packaging and publishing notes

The official documentation needed to put mailo on PyPI.

> **What these are**: summaries of the official documentation. The originals are
> authoritative and these are copies, so where they disagree, follow the original.
> Each file carries its source URL and the date it was checked.
> Checked: **2026-08-13**

## Files

| File | Covers |
|---|---|
| [01-packaging.md](01-packaging.md) | Project layout, `pyproject.toml`, the CLI entry point |
| [02-publishing.md](02-publishing.md) | Building and uploading — `build`+`twine` and `uv`, plus TestPyPI |
| [03-trusted-publishing.md](03-trusted-publishing.md) | Credential-free OIDC publishing, the GitHub Actions workflow |

## Primary sources

| Source | URL | Maintained by |
|---|---|---|
| Python Packaging User Guide | <https://packaging.python.org> | PyPA |
| PyPI operational docs | <https://docs.pypi.org> | PyPI |
| uv documentation | <https://docs.astral.sh/uv> | Astral |

## What this means for mailo

Details are in each file; the decisions are collected here.

1. **`src/` layout**, the structure the official tutorial recommends.
2. **hatchling as the build backend** — the tutorial's default and the least
   configuration.
3. **The CLI is exposed through `[project.scripts]`** — `mailo = "mailo.cli:main"`.
   → `main()` has to **return the exit code**. That differs from the current
   `mailer.py`, which calls `sys.exit()` directly, so watch for it when porting.
   (01 §4)
4. **The licence is an SPDX expression** (`license = "MIT"`). The old
   `license = {text = ...}` table and `License :: OSI Approved ::` classifiers are
   deprecated. Do not follow older tutorials here.
5. **Publishing via Trusted Publishing (GitHub Actions OIDC).** No API token is
   planted in CI. mailo does not exist on PyPI yet, so it starts as a **pending
   publisher**. (03)
6. **Go through TestPyPI first.** Its accounts and tokens are entirely separate from
   the real PyPI.

## Open items (tracked with [DESIGN.md](../../DESIGN.md) §10)

- ~~The value of `requires-python`~~ → **`>=3.11`, settled** (2026-08-13), so the
  config can be TOML via `tomllib`. See [DESIGN.md](../../DESIGN.md) §6.1.
- **Which licence**: MIT was assumed. Still to be decided.
- **Name reservation**: `mailo` is available on PyPI but **not reserved.**
  Registering a pending publisher **does not hold the name until the first upload.**
  (03 §4)
