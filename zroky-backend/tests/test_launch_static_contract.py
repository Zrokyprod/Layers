from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "check_launch_static_contract.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_launch_static_contract", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_minimal_repo(root: Path) -> None:
    dashboard_root = root / "zroky-dashboard" / "src" / "app" / "(dashboard)"
    for route in [
        "actions",
        "agents",
        "approvals",
        "evidence",
        "home",
        "integrations",
        "outcomes",
        "policies",
        "projects",
        "settings",
    ]:
        (dashboard_root / route).mkdir(parents=True, exist_ok=True)

    components = root / "zroky-dashboard" / "src" / "components"
    components.mkdir(parents=True, exist_ok=True)
    (components / "providers.tsx").write_text(
        '<ThemeProvider attribute="class" defaultTheme="light" '
        'forcedTheme="light" enableSystem={false}>children</ThemeProvider>',
        encoding="utf-8",
    )
    (root / "README.md").write_text("https://zroky.com\n", encoding="utf-8")

    openapi_path = root / "api-contracts" / "zroky-api-v1.openapi.json"
    openapi_path.parent.mkdir(parents=True, exist_ok=True)
    openapi_path.write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "info": {"title": "zroky-test", "version": "0.1.0"},
                "paths": {
                    "/v1/action-packs": {"get": {}},
                    "/v1/action-packs/{pack_id}": {"get": {}},
                    "/v1/action-packs/{pack_id}/install": {"post": {}},
                    "/v1/action-contracts": {"post": {}},
                    "/v1/action-intents": {"post": {}},
                    "/v1/action-intents/{action_id}": {"get": {}},
                    "/v1/action-intents/{action_id}/decide": {"post": {}},
                    "/v1/agents": {"get": {}, "post": {}},
                    "/v1/agents/{agent_id}": {
                        "get": {},
                        "patch": {},
                        "delete": {},
                    },
                    "/v1/tools/registry": {"get": {}},
                },
                "components": {
                    "schemas": {
                        "ActionPackInstallResponse": {},
                        "ActionPackListResponse": {},
                        "ActionPackResponse": {},
                        "ActionContractRegisterRequest": {},
                        "ActionContractResponse": {},
                        "ActionIntentCreateRequest": {},
                        "ActionIntentDecisionResponse": {},
                        "ActionIntentResponse": {},
                        "AgentProfileCreateRequest": {},
                        "AgentProfileResponse": {},
                        "ToolRegistryResponse": {},
                    }
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def test_current_repo_passes_static_launch_contract() -> None:
    module = _load_script()

    violations = module.check_static_contract(ROOT)

    assert violations == []


def test_static_launch_contract_rejects_old_domains_and_legacy_routes(
    tmp_path: Path,
) -> None:
    module = _load_script()
    _write_minimal_repo(tmp_path)
    (tmp_path / "README.md").write_text(
        "Old launch URL: "
        + "https://app."
        + "zroky"
        + ".com and https://api."
        + "zroky"
        + ".ai and https://api-staging."
        + "example"
        + ".com\n",
        encoding="utf-8",
    )
    (tmp_path / "zroky-dashboard" / "src" / "app" / "(dashboard)" / "calls").mkdir()

    violations = module.check_static_contract(tmp_path)
    rules = {violation.rule for violation in violations}

    assert "old_api_domain" in rules
    assert "old_zroky_ai_domain" in rules
    assert "old_app_subdomain" in rules
    assert "placeholder_staging_api_domain" in rules
    assert "dashboard_route_dirs" in rules


def test_static_launch_contract_scans_launch_package_roots(tmp_path: Path) -> None:
    module = _load_script()
    _write_minimal_repo(tmp_path)
    sdk_source = tmp_path / "zroky-sdk-js" / "src"
    sdk_source.mkdir(parents=True)
    old_api_url = "https://api." + "zroky" + ".ai"
    sdk_source.joinpath("index.ts").write_text(
        f"export const API_URL = '{old_api_url}';\n",
        encoding="utf-8",
    )

    violations = module.check_static_contract(tmp_path)

    assert any(
        violation.rule == "old_api_domain"
        and violation.path.as_posix().endswith("zroky-sdk-js/src/index.ts")
        for violation in violations
    )


def test_static_launch_contract_rejects_retired_dashboard_links(tmp_path: Path) -> None:
    module = _load_script()
    _write_minimal_repo(tmp_path)
    active_source = tmp_path / "zroky-backend" / "app" / "api" / "routes"
    active_source.mkdir(parents=True)
    retired_url = "https://zroky.com/" + "issues/issue_123"
    active_source.joinpath("notifications.py").write_text(
        f'body = "Open {retired_url}"\n',
        encoding="utf-8",
    )
    next_config = tmp_path / "zroky-dashboard" / "next.config.ts"
    retired_destination = "/" + "issues"
    next_config.write_text(
        "export default { async redirects(){ return [{ source: "
        f'"/legacy", destination: "{retired_destination}"'
        " }] } }\n",
        encoding="utf-8",
    )
    allowed_contract = tmp_path / "zroky-dashboard" / "src" / "lib"
    allowed_contract.mkdir(parents=True)
    allowed_contract.joinpath("dashboard-route-contract.ts").write_text(
        'export const retired = [{ href: "/issues" }];\n',
        encoding="utf-8",
    )

    violations = module.check_static_contract(tmp_path)

    assert any(
        violation.rule == "retired_dashboard_link"
        and violation.path.as_posix().endswith("zroky-backend/app/api/routes/notifications.py")
        for violation in violations
    )
    assert any(
        violation.rule == "retired_dashboard_link"
        and violation.path.as_posix().endswith("zroky-dashboard/next.config.ts")
        for violation in violations
    )
    assert not any(
        violation.rule == "retired_dashboard_link"
        and violation.path.as_posix().endswith("dashboard-route-contract.ts")
        for violation in violations
    )


def test_static_launch_contract_rejects_theme_switching(tmp_path: Path) -> None:
    module = _load_script()
    _write_minimal_repo(tmp_path)
    providers = tmp_path / "zroky-dashboard" / "src" / "components" / "providers.tsx"
    providers.write_text(
        '<ThemeProvider attribute="class" defaultTheme="dark" enableSystem={true}>'
        "children</ThemeProvider>",
        encoding="utf-8",
    )
    (tmp_path / "zroky-dashboard" / "src" / "components" / "theme-toggle.tsx").write_text(
        "export function ThemeToggle(){ setTheme('dark') }\n",
        encoding="utf-8",
    )

    violations = module.check_static_contract(tmp_path)
    rules = {violation.rule for violation in violations}

    assert "light_theme_provider" in rules
    assert "dark_default_theme" in rules
    assert "system_theme_enabled" in rules
    assert "theme_toggle" in rules
    assert "theme_mutation" in rules


def test_static_launch_contract_rejects_stale_openapi_verified_action_surface(
    tmp_path: Path,
) -> None:
    module = _load_script()
    _write_minimal_repo(tmp_path)
    openapi_path = tmp_path / "api-contracts" / "zroky-api-v1.openapi.json"
    document = json.loads(openapi_path.read_text(encoding="utf-8"))
    del document["paths"]["/v1/action-intents"]
    del document["components"]["schemas"]["ActionIntentResponse"]
    openapi_path.write_text(json.dumps(document), encoding="utf-8")

    violations = module.check_static_contract(tmp_path)

    assert any(
        violation.rule == "openapi_verified_action_surface"
        and "missing required route /v1/action-intents" in violation.detail
        for violation in violations
    )
    assert any(
        violation.rule == "openapi_verified_action_surface"
        and "ActionIntentResponse" in violation.detail
        for violation in violations
    )
