# 03 — Trusted Publishing (credential-free OIDC)

> Sources: <https://docs.pypi.org/trusted-publishers/>
> · <https://docs.pypi.org/trusted-publishers/adding-a-publisher/>
> · <https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/>
> · <https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/>
> Checked: 2026-08-13 · the originals are authoritative

## 1. What it is

**Exchanging short-lived identity tokens between CI and PyPI over OpenID Connect
(OIDC).** The original: *"uses the OIDC standard to exchange short-lived identity
tokens between a trusted third-party service and PyPI."*

Two advantages over API tokens:

- **Usability** — no token to create and paste into CI. One-time setup is all of it.
- **Security** — an OIDC token is **valid for 15 minutes** after issuance. Unlike a
  long-lived API token, a leak is bounded in time.

Supported providers: GitHub Actions, GitLab CI/CD, Google Cloud, ActiveState.
mailo assumes GitHub Actions.

## 2. Setup on the PyPI side

### 2.1 Adding it to a project that already exists

Add a publisher in the project settings. GitHub Actions takes **three required
fields plus one optional**:

| Field | Required | Example |
|---|---|---|
| Repository owner | ✅ | `octo-org` |
| Repository name | ✅ | `sampleproject` |
| Workflow filename | ✅ | `release.yml` |
| GitHub Actions environment name | optional (**strongly recommended**) | `pypi` |

Once registered, *"the `release.yml` workflow in `octo-org/sampleproject` will be
able to generate short-lived API tokens from PyPI for the registered project."*

### 2.2 Always configure an environment

The original recommends this **in bold**:

> *"configuring an environment is optional, but **strongly** recommended: an
> environment allows you to place additional restrictions on the trusted workflow —
> for example, requiring manual approval on each run by a trusted subset of
> maintainers."*

With an environment in place, **push access to the repository alone is not enough to
publish**; an approval step stands in the way. It is the last line of defence
against arbitrary releases if the repository is compromised. Worth enabling even on
a personal project.

### 2.3 For mailo: a "pending publisher"

**mailo does not exist on PyPI yet.** A publisher cannot be attached to a
nonexistent project, so it starts as a **pending publisher**.

- Where: not under a project, but under **"Publishing" in the account sidebar**
- Fields: repository URL, workflow file path, environment name, **and the desired
  PyPI project name**
- Transition: *"a 'pending' publisher will convert into a 'normal' publisher on
  first use, with no additional configuration needed."*

> **The thing to watch** — emphasised in the original:
> *"a 'pending' publisher does **not** create a project or reserve the project name
> until it is actually used to publish."*
>
> So registering a pending publisher leaves **the name `mailo` still unclaimed.**
> If someone else takes it before the first upload, the pending publisher becomes
> void. **The only way to secure a name is to actually publish once.**

TestPyPI is a separate system, so a pending publisher has to be registered there too,
at <https://test.pypi.org/manage/account/publishing/>.

## 3. The GitHub Actions workflow

It lives at **[`.github/workflows/release.yml`](../../.github/workflows/release.yml)**.
The filename must **exactly match** the workflow filename registered with PyPI, so
renaming it breaks publishing quietly.

It is the official guide's workflow with four deviations, each for a reason:

| Deviation | Why |
|---|---|
| A `test` job gates `build` | Publishing untested code to an index that cannot be undone is not a trade worth making. Two Python versions, 3.11 (our minimum) and the newest; with no dependencies it costs seconds |
| The tag must match `__version__` | Tagging `v0.2.0` on a tree that still says `0.1.0` publishes the wrong version number and burns it forever. Checked in `build`, which has the checkout, not in the publish jobs, which deliberately do not |
| The sdist is scanned for config files | The config file holds credentials. The `src/` layout keeps it out naturally, but "naturally" is not a guarantee worth shipping on |
| PyPI needs TestPyPI, and TestPyPI does not run on pushes to main | On a tag the rehearsal happens first and the real upload second, rather than both at once. Publishing to TestPyPI on every push would also fail until a publisher is registered, and afterwards would upload releases nobody asked for. `skip-existing: true` keeps a re-run from failing on an unbumped version |

### 3.1 What matters in this structure

- **Building and publishing are separate jobs.** `build` uploads the artefacts and
  the publish jobs pull them down. The publish jobs do not even check out the
  source — the point is to minimise the attack surface of a job holding
  `id-token: write`.
- **Without `permissions: id-token: write`** the OIDC token cannot be obtained and
  authentication fails.
- **Both publish jobs are tag-gated** (`if: startsWith(github.ref, 'refs/tags/')`),
  with TestPyPI also reachable through `workflow_dispatch` for a manual rehearsal.
- **`persist-credentials: false`** clears the credentials checkout would leave behind.

What a push to `main` runs, then, is `test` and `build` only — enough to catch a
broken tree without touching either index.

### 3.2 Signing and attestations (PEP 740)

Nothing extra to do. The original:

> *"starting with v1.11.0, `pypa/gh-action-pypi-publish` generates and uploads
> PEP 740-compatible attestations for each distribution by default. No additional
> manual signing step is required."*

## 4. Order of operations for mailo

1. Create the GitHub repository
2. In repository settings, **create two environments**: `pypi` and `testpypi`
   (put a manual approval rule on `pypi` if wanted — §2.2)
3. TestPyPI account → Publishing → **register a pending publisher**
   (repository URL, `release.yml`, environment `testpypi`, project name `mailo`)
4. PyPI account → Publishing → **register a pending publisher**
   (the same, with environment `pypi`)
5. Commit `.github/workflows/release.yml`, push, confirm it reaches TestPyPI
6. Once verified, `git tag v0.1.0 && git push --tags` → the first release to PyPI
   → at this point **the name `mailo` is secured** and the pending publisher becomes
   a normal one

## 5. Remaining risks

- **The name-claiming window**: between steps 3 and 6, `mailo` is still unclaimed
  (§2.3). If losing the name is unacceptable, publishing even a `0.0.1` early
  secures it.
- **Renaming the workflow file**: renaming `release.yml` later puts it out of step
  with the PyPI publisher configuration and publishing fails quietly. Update the
  PyPI setting at the same time.
