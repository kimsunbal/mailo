# docs — mailo documentation

The project overview is in [README.md](../README.md).

| Directory | Contents | Kind |
|---|---|---|
| [mailo/](mailo/) | The design: event model, hooks, configuration, onboarding, channels | ours |
| [channels/](channels/) | Per-channel protocols, APIs, and constraints | reference |
| [pypi/](pypi/) | Packaging and publishing to PyPI | reference |

**The two kinds are different and should not be confused.** `mailo/` is what we
decided and why; the other two are notes on documentation other people own.
[../DESIGN.md](../DESIGN.md) maps the design's section numbers — which the code
cites — to the files under `mailo/`.

> **About the reference notes**: they are summaries of external official docs. The
> originals are authoritative and these are copies, so where they disagree, follow
> the original. Each file carries its source URL and the date it was checked.

## Why write the reference notes at all

mailo takes **zero dependencies**. With no library wrapping anything, the
protocols and APIs have to be dealt with directly, and their constraints — size
limits, authentication, rate limits, conditions under which credentials cannot be
issued at all — become design constraints. Working through them changed the design
several times.

The **"applies to mailo"** section in each file is where that connection is made.
For a summary of the original, read the original; what is worth reading here is
that section.
