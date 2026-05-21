# OSS Repo Publish Runbook

Step-by-step guide to publish each OSS component as an independent public
GitHub repo with a fresh git history.

**Prerequisites:**
- GitHub org `zroky-ai` created (or your chosen org name)
- `gh` CLI authenticated (`gh auth login`)
- `git` available
- You have run through `OSS-LICENSING.md` and understand the boundary

**One-time setup only.** After initial publish, ongoing releases are just
`git push` from each standalone repo.

---

## 0. Confirm all 4 OSS dirs are publish-ready

```powershell
# From D:\Zroky AI
Get-ChildItem -Path zroky-sdk,zroky-sdk-js,zroky-gateway,zroky-replay-worker `
  -Filter LICENSE -Recurse | Select-Object FullName
# Should show 4 LICENSE files.

Get-ChildItem -Path zroky-sdk,zroky-sdk-js,zroky-gateway,zroky-replay-worker `
  -Filter README.md | Select-Object FullName
# Should show 4 README.md files.
```

---

## 1. Create the 4 public repos on GitHub

```bash
gh repo create zroky-ai/zroky-sdk            --public --description "Zroky Python SDK — AI agent observability"
gh repo create zroky-ai/zroky-sdk-js         --public --description "Zroky JS/TS SDK — AI agent observability"
gh repo create zroky-ai/zroky-gateway        --public --description "Zroky Gateway — LLM reverse proxy with telemetry"
gh repo create zroky-ai/zroky-replay-worker  --public --description "Zroky Replay Worker — self-hostable replay executor"
```

---

## 2. Publish each component (fresh history, one by one)

Each block below:
1. Copies the OSS dir to a temp location outside the private monorepo
2. Inits a fresh git repo (zero history from the private monorepo)
3. Makes a single clean "initial public release" commit
4. Pushes to the public GitHub repo

Run these from a **temp working dir** (e.g. `C:\zroky-publish\` or `/tmp/zroky-publish/`).

### 2a. zroky-sdk (Python)

```powershell
# Windows PowerShell
$src = "D:\Zroky AI\zroky-sdk"
$dst = "C:\zroky-publish\zroky-sdk"

Copy-Item -Recurse -Force $src $dst
Set-Location $dst

# Remove any internal-only artifacts that should not be published
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue `
  .pytest_cache, .pytest_basetemp, .pytest_run_temp_payload, `
  .pytest_tmp_privacy, .ruff_cache, __pycache__

git init -b main
git add .
git commit -m "chore: initial public release v0.1.0"
git remote add origin git@github.com:zroky-ai/zroky-sdk.git
git push -u origin main

# Tag the release
git tag v0.1.0
git push origin v0.1.0
```

### 2b. zroky-sdk-js (TypeScript)

```powershell
$src = "D:\Zroky AI\zroky-sdk-js"
$dst = "C:\zroky-publish\zroky-sdk-js"

Copy-Item -Recurse -Force $src $dst
Set-Location $dst

Remove-Item -Recurse -Force -ErrorAction SilentlyContinue `
  node_modules, dist, .turbo

git init -b main
git add .
git commit -m "chore: initial public release v0.1.0"
git remote add origin git@github.com:zroky-ai/zroky-sdk-js.git
git push -u origin main

git tag v0.1.0
git push origin v0.1.0
```

### 2c. zroky-gateway (Go)

```powershell
$src = "D:\Zroky AI\zroky-gateway"
$dst = "C:\zroky-publish\zroky-gateway"

Copy-Item -Recurse -Force $src $dst
Set-Location $dst

git init -b main
git add .
git commit -m "chore: initial public release v0.1.0"
git remote add origin git@github.com:zroky-ai/zroky-gateway.git
git push -u origin main

git tag v0.1.0
git push origin v0.1.0
```

### 2d. zroky-replay-worker (Python)

```powershell
$src = "D:\Zroky AI\zroky-replay-worker"
$dst = "C:\zroky-publish\zroky-replay-worker"

Copy-Item -Recurse -Force $src $dst
Set-Location $dst

Remove-Item -Recurse -Force -ErrorAction SilentlyContinue `
  .pytest_cache, __pycache__

git init -b main
git add .
git commit -m "chore: initial public release v0.1.0"
git remote add origin git@github.com:zroky-ai/zroky-replay-worker.git
git push -u origin main

git tag v0.1.0
git push origin v0.1.0
```

---

## 3. Configure each public repo on GitHub (post-push)

For **each** of the 4 public repos, go to GitHub → Settings and:

```
Branch protection → main:
  ✅ Require pull request reviews before merging (1 approval)
  ✅ Require status checks to pass → CI workflow
  ✅ Restrict who can push → only you initially

GitHub Actions → Secrets:
  (sdk only)    TEST_PYPI_API_TOKEN   ← from pypi.org
  (sdk only)    PYPI_API_TOKEN        ← from pypi.org
  (sdk-js only) NPM_TOKEN             ← from npmjs.com

Security → Code scanning:
  ✅ Enable Dependabot alerts
  ✅ Enable Dependabot security updates
```

---

## 4. After publishing — ongoing release workflow

### For code changes to an OSS component

1. Make the change in `D:\Zroky AI\<component>\` as normal.
2. `git commit` + `git push` to the private monorepo (`zroky-cloud`) — keeps
   internal history in sync.
3. Separately, in `C:\zroky-publish\<component>\`, apply the same change,
   commit, and push to the public repo:

```bash
# In C:\zroky-publish\zroky-sdk
git add .
git commit -m "fix: <short description>"
git push origin main
```

Or use `git cherry-pick` if you track both remotes on the same working dir.

### For version releases

```bash
# 1. Bump version in pyproject.toml / package.json
# 2. Commit
git commit -m "chore: release v0.1.1"
git push origin main
# 3. Tag
git tag v0.1.1
git push origin v0.1.1
# → GitHub Actions publishes to PyPI / npm automatically (for sdk / sdk-js)
# → Docker image built and pushed for gateway / replay-worker
```

---

## 5. Private monorepo push (also create this if not done yet)

```bash
# From D:\Zroky AI
# First time: create private repo on GitHub
gh repo create zroky-ai/zroky-cloud --private --description "Zroky platform (private)"

git remote add origin git@github.com:zroky-ai/zroky-cloud.git
git push -u origin main
```

All future `git push` from `D:\Zroky AI` goes here. This repo stays private
forever — backend, dashboard, internal plans, progress notes.

---

## Checklist before first public push

- [ ] All 4 OSS dirs have `LICENSE` file (FSL-1.1-MIT)
- [ ] All 4 OSS dirs have `README.md` (public-quality)
- [ ] All 4 OSS dirs have `.github/workflows/ci.yml`
- [ ] `pyproject.toml` / `package.json` license fields updated to FSL-1.1-MIT
- [ ] `.env` files are NOT present (only `.env.example`)
- [ ] `OSS-LICENSING.md` reviewed and signed off
- [ ] `legal@zroky.com` email address placeholder replaced with real address
- [ ] GitHub org `zroky-ai` created
- [ ] Private monorepo `zroky-cloud` created and pushed
