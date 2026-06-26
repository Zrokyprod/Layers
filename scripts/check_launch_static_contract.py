"""Static launch contract checks for Zroky.

These checks guard product invariants that are easy to regress during wiring:

- production URLs must use the current launch domain, not retired domains
- the paid dashboard stays light-only
- deleted legacy dashboard route directories stay deleted
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_DOMAIN_PATTERNS = {
    "old_api_domain": re.compile(r"api\.zroky\.ai", re.IGNORECASE),
    "old_zroky_ai_domain": re.compile(r"zroky\.ai", re.IGNORECASE),
    "old_app_subdomain": re.compile(r"app\.zroky\.", re.IGNORECASE),
    "placeholder_staging_api_domain": re.compile(
        r"api-staging\." + r"example\.com", re.IGNORECASE
    ),
}

FORBIDDEN_THEME_PATTERNS = {
    "theme_toggle": re.compile(r"theme-toggle|ThemeToggle"),
    "theme_mutation": re.compile(r"\bsetTheme\b|\bresolvedTheme\b|\buseTheme\s*\("),
    "dark_forced_theme": re.compile(r'forcedTheme\s*=\s*["{]dark["}]'),
    "dark_default_theme": re.compile(r'defaultTheme\s*=\s*["{]dark["}]'),
    "system_theme_enabled": re.compile(r"enableSystem\s*=\s*\{\s*true\s*\}"),
}

RETIRED_DASHBOARD_PATHS = [
    "/alerts",
    "/calls",
    "/ci-gates",
    "/contracts",
    "/cost",
    "/goldens",
    "/issues",
    "/replay",
    "/trace",
    "/drift",
    "/labs",
]
_RETIRED_DASHBOARD_ROUTE_PATTERN = "|".join(
    re.escape(path.lstrip("/")) for path in RETIRED_DASHBOARD_PATHS
)
RETIRED_DASHBOARD_LINK_PATTERN = re.compile(
    rf"https://zroky\.com/(?:{_RETIRED_DASHBOARD_ROUTE_PATTERN})(?:[/?#\"'<\s]|\b)"
    rf"|\bhref\s*=\s*[{{]?[\"'`]/(?:{_RETIRED_DASHBOARD_ROUTE_PATTERN})(?:[/?#\"'`<\s]|\b)"
    rf"|\brouter\.(?:push|replace)\(\s*[\"'`]/(?:{_RETIRED_DASHBOARD_ROUTE_PATTERN})(?:[/?#\"'`<\s]|\b)"
    rf"|\bdestination\s*:\s*[\"'`]/(?:{_RETIRED_DASHBOARD_ROUTE_PATTERN})(?:[/?#\"'`<\s]|\b)"
)

SOURCE_EXTENSIONS = {
    ".css",
    ".env",
    ".go",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".ps1",
    ".py",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}

EXCLUDED_DIRS = {
    ".git",
    ".next",
    ".tmp",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}

SCAN_ROOTS = [
    ".github",
    "README.md",
    "api-contracts",
    "chaos-tests",
    "clickhouse",
    "demos",
    "eval",
    "grafana",
    "prometheus",
    "scripts",
    "zroky-admin",
    "zroky-backend",
    "zroky-dashboard",
    "zroky-gateway",
    "zroky-landing",
    "zroky-regression-ci-action",
    "zroky-replay-worker",
    "zroky-sdk",
    "zroky-sdk-js",
]

EXPECTED_DASHBOARD_ROUTE_DIRS = [
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
]

REQUIRED_OPENAPI_SURFACES = {
    "/v1/action-packs": {"get"},
    "/v1/action-packs/{pack_id}": {"get"},
    "/v1/action-packs/{pack_id}/install": {"post"},
    "/v1/action-contracts": {"post"},
    "/v1/action-intents": {"post"},
    "/v1/action-intents/{action_id}": {"get"},
    "/v1/action-intents/{action_id}/decide": {"post"},
    "/v1/agents": {"get", "post"},
    "/v1/agents/{agent_id}": {"get", "patch", "delete"},
    "/v1/tools/registry": {"get"},
}

REQUIRED_OPENAPI_SCHEMAS = {
    "ActionPackInstallResponse",
    "ActionPackListResponse",
    "ActionPackResponse",
    "ActionContractRegisterRequest",
    "ActionContractResponse",
    "ActionIntentCreateRequest",
    "ActionIntentDecisionResponse",
    "ActionIntentResponse",
    "AgentProfileCreateRequest",
    "AgentProfileResponse",
    "ToolRegistryResponse",
}

RETIRED_DASHBOARD_LINK_ALLOWED_FILES = {
    "zroky-dashboard/src/lib/dashboard-route-contract.ts",
    "zroky-dashboard/src/lib/dashboard-route-contract.test.ts",
    "zroky-dashboard/src/lib/route-auth-guard.test.ts",
    "zroky-dashboard/e2e/dashboard-modules.spec.ts",
    "zroky-dashboard/e2e/money-path.spec.ts",
    "zroky-dashboard/e2e/reliability-ux.spec.ts",
}


@dataclass(frozen=True)
class Violation:
    rule: str
    path: Path
    detail: str
    line: int | None = None

    def format(self, root: Path) -> str:
        try:
            relative = self.path.relative_to(root).as_posix()
        except ValueError:
            relative = self.path.as_posix()
        suffix = f":{self.line}" if self.line is not None else ""
        return f"[{self.rule}] {relative}{suffix}: {self.detail}"


def _is_source_file(path: Path) -> bool:
    return (
        path.suffix in SOURCE_EXTENSIONS
        or path.name.startswith(".env")
        or ".env." in path.name
    )


def _iter_source_files(root: Path, scan_roots: Iterable[str]) -> Iterable[Path]:
    for entry in scan_roots:
        path = root / entry
        if not path.exists():
            continue
        if path.is_file():
            if _is_source_file(path):
                yield path
            continue
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [name for name in dirnames if name not in EXCLUDED_DIRS]
            current = Path(dirpath)
            for filename in filenames:
                child = current / filename
                if _is_source_file(child):
                    yield child


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def _line_number(text: str, start_index: int) -> int:
    return text.count("\n", 0, start_index) + 1


def _relative_posix(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def check_forbidden_domains(root: Path) -> list[Violation]:
    violations: list[Violation] = []
    checker_path = Path(__file__).resolve()
    for path in _iter_source_files(root, SCAN_ROOTS):
        if path.resolve() == checker_path:
            continue
        text = _read_text(path)
        for rule, pattern in FORBIDDEN_DOMAIN_PATTERNS.items():
            for match in pattern.finditer(text):
                violations.append(
                    Violation(
                        rule=rule,
                        path=path,
                        line=_line_number(text, match.start()),
                        detail=(
                            "production launch references must use zroky.com "
                            "or api.zroky.com"
                        ),
                    )
                )
    return violations


def check_retired_dashboard_links(root: Path) -> list[Violation]:
    violations: list[Violation] = []
    checker_path = Path(__file__).resolve()
    for path in _iter_source_files(root, SCAN_ROOTS):
        if path.resolve() == checker_path:
            continue
        if _relative_posix(path, root) in RETIRED_DASHBOARD_LINK_ALLOWED_FILES:
            continue
        text = _read_text(path)
        for match in RETIRED_DASHBOARD_LINK_PATTERN.finditer(text):
            violations.append(
                Violation(
                    rule="retired_dashboard_link",
                    path=path,
                    line=_line_number(text, match.start()),
                    detail=(
                        "retired dashboard links must route through active "
                        "surfaces such as /home, /approvals, /evidence, or /policies"
                    ),
                )
            )
    return violations


def check_dashboard_route_directories(root: Path) -> list[Violation]:
    dashboard_root = root / "zroky-dashboard" / "src" / "app" / "(dashboard)"
    if not dashboard_root.exists():
        return [
            Violation(
                rule="dashboard_route_dirs",
                path=dashboard_root,
                detail="dashboard app directory is missing",
            )
        ]

    actual = sorted(path.name for path in dashboard_root.iterdir() if path.is_dir())
    if actual == EXPECTED_DASHBOARD_ROUTE_DIRS:
        return []

    return [
        Violation(
            rule="dashboard_route_dirs",
            path=dashboard_root,
            detail=(
                "dashboard route directories must match paid IA exactly; "
                f"expected {EXPECTED_DASHBOARD_ROUTE_DIRS}, got {actual}"
            ),
        )
    ]


def check_dashboard_theme_policy(root: Path) -> list[Violation]:
    violations: list[Violation] = []
    dashboard_src = root / "zroky-dashboard" / "src"
    providers = dashboard_src / "components" / "providers.tsx"

    if not providers.exists():
        violations.append(
            Violation(
                rule="light_theme_provider",
                path=providers,
                detail="Providers component is missing",
            )
        )
    else:
        text = _read_text(providers)
        required_fragments = {
            'defaultTheme="light"': "ThemeProvider must default to light",
            'forcedTheme="light"': "ThemeProvider must force light",
            "enableSystem={false}": "ThemeProvider must disable system theme",
        }
        for fragment, detail in required_fragments.items():
            if fragment not in text:
                violations.append(
                    Violation(
                        rule="light_theme_provider",
                        path=providers,
                        detail=detail,
                    )
                )

    for path in _iter_source_files(root, ["zroky-dashboard/src"]):
        text = _read_text(path)
        for rule, pattern in FORBIDDEN_THEME_PATTERNS.items():
            for match in pattern.finditer(text):
                if path.name == "providers.test.tsx":
                    continue
                violations.append(
                    Violation(
                        rule=rule,
                        path=path,
                        line=_line_number(text, match.start()),
                        detail="paid dashboard is light-only; remove theme switching",
                    )
                )

    return violations


def check_openapi_verified_action_surface(root: Path) -> list[Violation]:
    openapi_path = root / "api-contracts" / "zroky-api-v1.openapi.json"
    if not openapi_path.exists():
        return [
            Violation(
                rule="openapi_verified_action_surface",
                path=openapi_path,
                detail="frozen OpenAPI contract is missing",
            )
        ]

    try:
        document = json.loads(_read_text(openapi_path))
    except json.JSONDecodeError as exc:
        return [
            Violation(
                rule="openapi_verified_action_surface",
                path=openapi_path,
                line=exc.lineno,
                detail=f"frozen OpenAPI contract is not valid JSON: {exc.msg}",
            )
        ]

    violations: list[Violation] = []
    paths = document.get("paths")
    if not isinstance(paths, dict):
        return [
            Violation(
                rule="openapi_verified_action_surface",
                path=openapi_path,
                detail="frozen OpenAPI contract does not contain a paths object",
            )
        ]

    for route, expected_methods in REQUIRED_OPENAPI_SURFACES.items():
        operations = paths.get(route)
        if not isinstance(operations, dict):
            violations.append(
                Violation(
                    rule="openapi_verified_action_surface",
                    path=openapi_path,
                    detail=f"frozen OpenAPI contract is missing required route {route}",
                )
            )
            continue
        missing_methods = sorted(
            method for method in expected_methods if method not in operations
        )
        if missing_methods:
            violations.append(
                Violation(
                    rule="openapi_verified_action_surface",
                    path=openapi_path,
                    detail=(
                        f"frozen OpenAPI route {route} is missing "
                        f"method(s): {', '.join(missing_methods)}"
                    ),
                )
            )

    schemas = document.get("components", {}).get("schemas", {})
    if not isinstance(schemas, dict):
        schemas = {}
    missing_schemas = sorted(REQUIRED_OPENAPI_SCHEMAS - set(schemas))
    if missing_schemas:
        violations.append(
            Violation(
                rule="openapi_verified_action_surface",
                path=openapi_path,
                detail=(
                    "frozen OpenAPI contract is missing verified-action "
                    f"schema(s): {', '.join(missing_schemas)}"
                ),
            )
        )

    return violations


def check_static_contract(root: Path) -> list[Violation]:
    return [
        *check_forbidden_domains(root),
        *check_retired_dashboard_links(root),
        *check_dashboard_route_directories(root),
        *check_dashboard_theme_policy(root),
        *check_openapi_verified_action_surface(root),
    ]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Zroky static launch contract.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="Repository root.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    root = args.root.resolve()
    print("Static launch contract check")
    print(f"  Root: {root}")

    violations = check_static_contract(root)
    if violations:
        print(f"\n::error::Static launch contract violations ({len(violations)}):")
        for violation in violations:
            print("  " + violation.format(root))
        return 1

    print("OK - static launch contract passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
