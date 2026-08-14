# mailo

## Language

**Everything inside this project is written in English.** Source code, comments,
docstrings, user-facing CLI output, log messages, error messages and their
remedies, the config template and its comments, notification metadata keys, tests,
`README.md`, `DESIGN.md`, `docs/`, and commit messages.

mailo is a public package. Its output is read by users who do not share the
maintainer's language, and `README.md` renders as the PyPI project page.

**Talk to the user in Korean.** Session replies only — chat messages, explanations,
questions. Nothing that lands in a file.

The dividing line: **if it ends up in a file or in the tool's output, it is
English. If it is a message to the user in this session, it is Korean.**

### Not affected

- Non-English *data*, as opposed to prose. The SMTP domain presets for
  `naver.com` / `kakao.com` / `daum.net` in `src/mailo/channels/smtp.py` are server
  addresses, not language, and stay as they are.
- Direct quotations from source documents in `docs/`, which keep their original
  wording.
- Non-ASCII characters used as test fixtures — for example the multi-byte string in
  `tests/test_channels.py` that proves Discord counts characters rather than bytes.
  Replacing it with ASCII would silently gut the test.

## Documentation

**A change to behaviour, config keys, the CLI surface, or a design decision is not
finished until `docs/` matches it.** Update them in the same change, not later.

- **`docs/mailo/`** — the design. Its section numbers are cited from code
  (`DESIGN.md §5.1`), so keep them stable; adding a section means adding a row to
  the map in `DESIGN.md`.
- **`docs/channels/`, `docs/pypi/`** — notes on other people's documentation. When a
  decision changes, update the "what this means for mailo" part; leave the summary
  of the original alone, and keep its source URL and checked date.
- **`README.md`** renders as the PyPI project page. It must not promise anything the
  code does not do.

**Never let the docs describe behaviour the code lacks.** This has already
happened once: the Discord notes specified `?wait=true` while the implementation
posted without it, so a documented delivery guarantee did not exist.
