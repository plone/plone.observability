# Releasing plone.observability

This package is released to PyPI via **GitHub Actions Trusted Publishing**
(OIDC, no API tokens). The workflow lives in `.github/workflows/release.yaml`.

## How publishing works

- **Every push to `main`** builds the package and uploads an **in-dev** build to
  **TestPyPI**, versioned `X.Y.Zsuffix.dev<run-number>` (the `release-test-pypi`
  job appends `.dev<github.run_number>` so each upload is unique — TestPyPI
  rejects duplicate versions and forbids local `+hash` segments).
- **Publishing a GitHub Release** (a `release: published` event) builds the
  package with the **clean** version from `pyproject.toml` and uploads it to
  **PyPI** (the `release-pypi` job).

Trusted publishers are configured on both PyPI and TestPyPI for the `plone` org
(owner `plone`, repo `plone.observability`, workflow `release.yaml`, environments
`release-pypi` / `release-test-pypi`). No secrets are stored in the repo.

## Cutting a release

All work lands on `main` via PRs with green CI first. Then:

1. **Branch** for the release bump:
   ```bash
   git checkout main && git pull
   git checkout -b release-X.Y.Z
   ```
2. **Bump the version** in `pyproject.toml` (`version = "X.Y.Z"`). For the final
   `1.0.0`, also set the `Development Status` classifier to `5 - Production/Stable`.
3. **Build the changelog** from the `news/` fragments:
   ```bash
   .venv/bin/python -m towncrier build --yes --version X.Y.Z
   ```
   This writes the `X.Y.Z` section into `CHANGES.md` and removes the consumed
   fragments. Sanity-check `CHANGES.md` (e.g. for duplicate issue links).
4. **Commit, push, open a PR**, wait for **green CI**, then **merge**.
   > After saying "merged", verify it actually merged:
   > `gh pr view <N> --json state,mergedAt` — a missed merge click has bitten us
   > before.
5. **Sync `main`** and confirm the version:
   ```bash
   git checkout main && git pull
   grep '^version' pyproject.toml
   ```
6. **Create the GitHub Release** (this triggers the PyPI upload):
   ```bash
   gh release create X.Y.Z --title "X.Y.Z" --notes-file <notes.md>
   ```
   Use the new `CHANGES.md` section as the notes.
7. **Verify** the `release-pypi` job is green and the version is live:
   ```bash
   gh run watch <run-id> --exit-status
   curl -s -o /dev/null -w '%{http_code}\n' \
     https://pypi.org/pypi/plone.observability/X.Y.Z/json   # expect 200
   ```
   The PyPI JSON index is cached briefly; the per-version page (above) updates
   first.

## News fragments (towncrier)

Every user-facing change ships a fragment in `news/`, named `<issue>.<type>` (or
`+slug.<type>` when there is no issue). Configured types: `breaking`, `feature`,
`bugfix`, `internal`, `documentation`. They are assembled into `CHANGES.md` at
release time (step 3) — do not hand-edit `CHANGES.md` for unreleased changes.

## Versioning

Pre-1.0 betas use `1.0.0bN`. Keep `requires-python` and the Python classifiers in
sync with the Plone version the release targets.
