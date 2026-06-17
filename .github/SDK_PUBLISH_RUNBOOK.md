# SDK Public Publish Runbook

This repo can build and verify both SDK packages, but public registry publishing
requires credentials owned by the Zroky npm and PyPI accounts. Do not commit
registry tokens.

## Packages

- JavaScript: `@zroky/sdk`
- Python: `zroky`

## npm publish

1. Create or confirm the npm scope/organization `@zroky`.
2. Create an npm automation token with permission to publish `@zroky/sdk`.
3. Add the token to GitHub repository secrets as `NPM_TOKEN`.
4. Run GitHub Actions workflow `Zroky JS SDK Publish`.
5. Choose:
   - `target_registry`: `npm`
   - `expected_version`: the version in `zroky-sdk-js/package.json`
6. Wait for both jobs to pass:
   - `publish-npm`
   - `verify-npm-registry`

The publish job uses `npm publish --access public --provenance`. The verify job
waits for the package to appear in npm, installs the exact version into a clean
temporary project, and checks the expected SDK exports.

## PyPI publish

Preferred auth method: PyPI Trusted Publisher.

1. Configure a PyPI Trusted Publisher, or a pending publisher for first publish:
   - Project: `zroky`
   - Owner/repository: this GitHub repository
   - Workflow: `.github/workflows/zroky-sdk-publish.yml`
   - Environment: leave empty unless you intentionally add a matching GitHub
     environment to the workflow.
2. Run GitHub Actions workflow `Zroky SDK Publish`.
3. First publish to TestPyPI:
   - `target_repository`: `testpypi`
   - `auth_method`: `trusted-publisher`
   - `expected_version`: the version in `zroky-sdk/pyproject.toml`
4. Confirm `verify-testpypi-registry` passes.
5. Publish to PyPI:
   - `target_repository`: `pypi`
   - `auth_method`: `trusted-publisher`
   - `expected_version`: the version in `zroky-sdk/pyproject.toml`
6. Confirm `verify-pypi-registry` passes.

Token fallback:

- Add `TEST_PYPI_API_TOKEN` for TestPyPI.
- Add `PYPI_API_TOKEN` for PyPI.
- Run the same workflow with `auth_method: token`.
- For a first-time PyPI project, use Trusted Publisher or an account-level token
  that can create the project. After first publish, rotate to project-scoped
  tokens if token auth remains necessary.

## Tag publish

Manual workflow dispatch is preferred for the first release. For later releases,
these tag names trigger publish automatically:

- Python: `zroky-sdk-vX.Y.Z`
- JavaScript: `zroky-sdk-js-vX.Y.Z`

The tag version must exactly match the package version, or the workflow fails.
Do not run manual publish and tag publish for the same immutable registry version.

## Post-publish smoke

After both public registry publishes pass, verify from a clean machine or temp
directory:

```bash
npm install @zroky/sdk@0.1.0
python -m pip install zroky==0.1.0
```

Then send one real capture through the SDK and confirm the trace appears in the
Zroky dashboard.

## Failure policy

Registry versions are immutable. If a publish partially succeeds and then fails
verification, fix forward by bumping the package version before publishing again.
