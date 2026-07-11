from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "zroky-backend-production-deploy.yml"


def test_backend_production_deploy_waits_for_successful_main_ci() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert 'workflows: ["Zroky Backend CI"]' in workflow
    assert "github.event.workflow_run.head_branch == 'main'" in workflow
    assert "github.event.workflow_run.conclusion == 'success'" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "environment: Production" in workflow
    assert "ref: ${{ steps.revision.outputs.sha }}" in workflow


def test_backend_production_deploy_uses_scoped_config_and_strict_smoke() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}" in workflow
    assert "RAILWAY_PROJECT_ID: ${{ vars.RAILWAY_PROJECT_ID }}" in workflow
    assert "RAILWAY_ENVIRONMENT_ID: ${{ vars.RAILWAY_ENVIRONMENT_ID }}" in workflow
    assert "RAILWAY_SERVICE_ID: ${{ vars.RAILWAY_BACKEND_SERVICE_ID }}" in workflow
    assert "@railway/cli@4.33.0" in workflow
    assert "railway up" in workflow
    assert "--path-as-root" not in workflow
    assert '"${CANDIDATE_ID}" != "${BEFORE_ID}"' in workflow
    assert "railway deployment list" in workflow
    assert "FAILED|CRASHED|REMOVED" in workflow
    assert "scripts/railway_smoke_check.py" in workflow
    assert '--base-url "${PRODUCTION_API_URL}"' in workflow
    assert "--expected-unauthorized-status 401" in workflow
