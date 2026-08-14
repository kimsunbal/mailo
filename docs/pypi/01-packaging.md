# 01 — packaging: layout and pyproject.toml

> Sources: <https://packaging.python.org/en/latest/tutorials/packaging-projects/>
> and <https://packaging.python.org/en/latest/guides/writing-pyproject-toml/>
> Checked: 2026-08-13 · the originals are authoritative

## 1. Project layout

The official tutorial recommends the **`src/` layout**.

```
project-root/
├── LICENSE
├── pyproject.toml
├── README.md
├── src/
│   └── package_name/
│       ├── __init__.py
│       └── module.py
└── tests/
```

Include `__init__.py` even when empty — in the original's words, it *"allows the
directory to be importable as a regular package."*

The reason for the `src/` layout is that it forces tests to import the **installed
package**. With a flat layout the project root lands on `sys.path` and the source
directory gets picked up directly, so packaging mistakes — a file that never made it
into the wheel, say — go undetected by the tests.

## 2. Declaring the build system

`pyproject.toml` must state which build backend to use. `requires` lists build-time
dependencies, and `build-backend` is the Python object the frontend calls.

The options the official tutorial presents:

| Backend | `requires` | `build-backend` |
|---|---|---|
| **Hatchling** (tutorial default) | `hatchling >= 1.26` | `hatchling.build` |
| Setuptools | `setuptools >= 77.0.3` | `setuptools.build_meta` |
| Flit | `flit_core >= 3.12.0, <5` | `flit_core.buildapi` |
| PDM | `pdm-backend >= 2.4.0` | `pdm.backend` |
| uv-build | `uv_build >= 0.12.1, <0.13.0` | `uv_build` |

```toml
[build-system]
requires = ["hatchling >= 1.26"]
build-backend = "hatchling.build"
```

## 3. `[project]` metadata

The main fields:

| Field | Description |
|---|---|
| `name` | distribution name; letters, digits, `.`, `_`, `-` only |
| `version` | version string |
| `description` | one-sentence summary |
| `readme` | path to the long description |
| `requires-python` | supported Python versions |
| `dependencies` | runtime dependencies |
| `license` | **SPDX licence expression** |
| `license-files` | glob patterns for licence files |
| `authors` | names and emails |
| `classifiers` | index classification tags |
| `keywords` | for search |

### 3.1 Licences — what changed (PEP 639)

```toml
license = "MIT"
license-files = ["LICENSE"]
```

Use an **SPDX expression string**. As the original puts it, this is *"an SPDX
license expression, rather than the previous, deprecated table structure."* The
forms below, common on the internet, are **the old way**:

```toml
license = { text = "MIT" }                            # deprecated
classifiers = ["License :: OSI Approved :: MIT ..."]  # deprecated
```

### 3.2 Dependencies

```toml
dependencies = [
  "httpx",
  "gidgethub[httpx]>4.0.0",
  "django>2.1; os_name != 'nt'",
]
```

Everything after a semicolon is an environment marker. **mailo has no dependencies,
so `dependencies = []`.**

## 4. The CLI entry point — the important part for mailo

```toml
[project.scripts]
spam-cli = "spam:main_cli"
```

The original: *"this would create a command `spam-cli` … running this command would
do the equivalent of `import sys; from spam import main_cli; sys.exit(main_cli())`."*

**That gives us a contract.** Since the wrapper calls `sys.exit(main_cli())`, the
function's **return value is the exit code**:

- `return None` → exit code 0
- `return 1` → exit code 1
- `sys.exit("message")` → prints the message to stderr, exit code 1

The current `mailer.py` has a `main()` that returns nothing and calls `sys.exit(...)`
directly on error. Ported as is it **still works** (`sys.exit` raises, which passes
through the wrapper). But returning a non-zero code on the normal path needs a
return value — which is exactly what a runner script doing
`if mailo ...; then` for retries depends on.

Windows GUI apps use `[project.gui-scripts]` (no console window). Not applicable to
mailo.

## 5. Draft pyproject.toml for mailo

> `requires-python = ">=3.11"` is settled ([DESIGN.md](../../DESIGN.md) §6.1).
> The licence is assumed to be MIT and is still undecided.

```toml
[build-system]
requires = ["hatchling >= 1.26"]
build-backend = "hatchling.build"

[project]
name = "mailo"
version = "0.1.0"
description = "Notify yourself when your AI agent gets stuck, fails, or finishes."
readme = "README.md"
requires-python = ">=3.11"
license = "MIT"
license-files = ["LICENSE"]
authors = [{ name = "...", email = "..." }]
keywords = ["notification", "claude-code", "ai-agent", "discord", "hooks"]
dependencies = []

classifiers = [
  "Development Status :: 3 - Alpha",
  "Environment :: Console",
  "Intended Audience :: Developers",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Topic :: Communications",
  "Topic :: Software Development :: Build Tools",
]

[project.urls]
Homepage = "https://github.com/<owner>/mailo"
Issues = "https://github.com/<owner>/mailo/issues"

[project.scripts]
mailo = "mailo.cli:main"
```

The matching source layout:

```
mailo/
├── LICENSE
├── README.md
├── DESIGN.md
├── pyproject.toml
├── docs/
├── src/
│   └── mailo/
│       ├── __init__.py
│       ├── cli.py          # main() — subcommand dispatch
│       ├── config.py       # TOML loading, chmod check, env overrides
│       ├── events.py       # hook JSON -> normalised mailo events
│       ├── hooks.py        # install-hooks / uninstall-hooks
│       ├── state.py        # session cache, cooldown
│       └── channels/
│           ├── __init__.py # registry and delivery orchestration
│           ├── discord.py
│           └── smtp.py
└── tests/
```

## 6. Things to watch

- **`name` must be globally unique on PyPI.** `mailo` is currently free.
- Upload **both an sdist (`.tar.gz`) and a wheel (`.whl`)** — the original advises
  *"always upload a source distribution and provide built distributions for the
  platforms your project is compatible with."* mailo is pure Python, so one wheel
  covers every platform.
- **The config file (`config.toml`) must never end up in the package.** It holds
  secrets. The `src/` layout keeps it outside the source tree naturally, but check
  the actual contents once after building with `tar tzf dist/*.tar.gz`.
