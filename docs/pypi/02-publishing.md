# 02 — building and uploading

> Sources: <https://packaging.python.org/en/latest/tutorials/packaging-projects/>
> and <https://docs.astral.sh/uv/guides/package/>
> Checked: 2026-08-13 · the originals are authoritative

There are two paths and **both are official.** The artefacts are identical.

| | PyPA standard | uv |
|---|---|---|
| Build | `python3 -m build` | `uv build` |
| Upload | `python3 -m twine upload dist/*` | `uv publish` |
| Tooling | `pip install build twine` | uv alone |

In CI neither is used directly; `pypa/gh-action-pypi-publish` is (see 03). What
follows is the manual local procedure.

## 1. The PyPA standard path

### 1.1 Build

```bash
python3 -m pip install --upgrade build
python3 -m build          # from the project root
```

Two files appear in `dist/`:

- `*.whl` — the built distribution (wheel)
- `*.tar.gz` — the source distribution (sdist)

### 1.2 Upload to TestPyPI (do this first)

1. Register at <https://test.pypi.org/account/register/>
2. Create an API token at <https://test.pypi.org/manage/account/#api-tokens>
3. Upload:

```bash
python3 -m pip install --upgrade twine
python3 -m twine upload --repository testpypi dist/*
```

Enter the **whole token including the `pypi-` prefix**. The input is not echoed.

> The original warns: *"don't close the page until you have copied and saved the
> token — you won't see that token again."*

### 1.3 Verify the install

```bash
python3 -m venv /tmp/mailo-test && /tmp/mailo-test/bin/pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  mailo
/tmp/mailo-test/bin/mailo --help
```

`--extra-index-url` is needed because dependencies may not exist on TestPyPI. mailo
has none, so it is unnecessary here, but keeping the habit is safe.

### 1.4 Upload to the real PyPI

Accounts and tokens are **entirely separate** from TestPyPI. Register separately and
create a separate token.

```bash
python3 -m twine upload dist/*      # without --repository this is the real PyPI
```

## 2. The uv path

```bash
uv build --no-sources
uv publish
```

`--no-sources` is uv's own recommendation — the intent is to **guarantee the build
reproduces under other build tools.** It ignores `tool.uv.sources` (local paths, git
dependencies, and so on), which prevents publishing a package that only builds on
your machine.

Authentication:

```bash
uv publish --token <TOKEN>       # or the UV_PUBLISH_TOKEN environment variable
```

To target TestPyPI, define the index and select it:

```toml
# pyproject.toml
[[tool.uv.index]]
name = "testpypi"
url = "https://test.pypi.org/simple/"
publish-url = "https://test.pypi.org/legacy/"
explicit = true
```

```bash
uv publish --index testpypi
```

## 3. An important fact about authentication

**PyPI no longer accepts username/password uploads.** uv's documentation marks
`--username` / `--password` as *legacy, no longer supported by PyPI*.

Only two methods remain:

1. **API tokens** — long-lived credentials, for manual local uploads.
2. **Trusted Publishing (OIDC)** — short-lived tokens, for CI, and **recommended.**
   → see 03

Planting an API token as a CI secret is the outdated arrangement. mailo goes with
option 2 from the start.

## 4. Release checklist (for mailo)

Before building:

- [ ] `version` bumped
- [ ] `README.md` current (it renders as the PyPI project page verbatim)
- [ ] a `LICENSE` file exists and matches `license` / `license-files`

After building, before uploading:

- [ ] `tar tzf dist/*.tar.gz` — **confirm no config file or secret got in**
- [ ] `unzip -l dist/*.whl` — the entry point is present
- [ ] install into a clean venv and check `mailo --help` and `mailo test` run

Uploading:

- [ ] TestPyPI first
- [ ] verify the install from TestPyPI
- [ ] then the real PyPI

> **It cannot be undone.** PyPI does not allow re-uploading the same version number.
> Deleting the files still burns that version number permanently; a mistake means
> shipping `0.1.1`. That is the practical reason for the TestPyPI-first advice.
