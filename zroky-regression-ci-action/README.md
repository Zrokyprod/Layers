# Zroky Regression CI Action

GitHub Action that runs the Zroky **Pre-deploy Replay CI Gate** on every pull request.

## Usage

```yaml
name: Zroky Regression CI
on:
  pull_request:
    branches: [main]

jobs:
  replay-ci:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - name: Collect changed files
        id: files
        run: |
          git fetch origin ${{ github.base_ref }}
          files=$(git diff --name-only origin/${{ github.base_ref }}...HEAD | jq -R -s -c 'split("\n")[:-1] | map({path: .})')
          echo "changed=$files" >> "$GITHUB_OUTPUT"
      - uses: zroky/regression-ci@v1
        with:
          api_key: ${{ secrets.ZROKY_API_KEY }}
          project_id: ${{ vars.ZROKY_PROJECT_ID }}
          post_pr_comment: true
          fail_on_regression: true
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          ZROKY_CHANGED_FILES_JSON: ${{ steps.files.outputs.changed }}
```

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `api_key` | yes | — | Zroky project API key |
| `project_id` | yes | — | Zroky project id |
| `base_url` | no | `https://api.zroky.com` | API base URL |
| `threshold` | no | `0.02` | Regression threshold (0–1) |
| `sample_window_days` | no | `30` | Trace sampling lookback |
| `poll_interval_seconds` | no | `5` | Status poll interval |
| `timeout_seconds` | no | `300` | Max wait for completion |
| `post_pr_comment` | no | `true` | Post/update PR comment |
| `fail_on_regression` | no | `true` | Fail the check on regression |

## Outputs

| Output | Description |
|--------|-------------|
| `run_id` | Replay run id |
| `status` | Terminal status (`pass`, `fail`, `error`) |
| `regression_rate` | Fraction of traces that regressed |
| `pr_comment_markdown` | Rendered markdown body |
