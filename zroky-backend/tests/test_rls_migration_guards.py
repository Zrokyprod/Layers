from __future__ import annotations

from pathlib import Path


def test_rls_policies_use_current_tenant_id_setting() -> None:
    migration_root = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    offenders = []
    for path in migration_root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "current_setting('app.current_tenant')" in text:
            offenders.append(path.name)

    assert offenders == []


def test_fix_embeddings_rls_is_forced_and_write_scoped() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0023_add_fix_embeddings.py"
    )
    text = path.read_text(encoding="utf-8")

    assert "ALTER TABLE fix_embeddings FORCE ROW LEVEL SECURITY" in text
    assert "WITH CHECK (project_id = current_setting('app.current_tenant_id', true))" in text


def test_mcp_interception_tables_are_project_rls_scoped() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0122_mcp_interception.py"
    )
    text = path.read_text(encoding="utf-8")

    for table_name in ("mcp_tool_bindings", "mcp_interception_events"):
        assert f'_enable_project_rls("{table_name}")' in text

    assert 'ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY' in text
    assert 'CREATE POLICY {policy_name}' in text
    assert "WITH CHECK (project_id = current_setting('app.current_tenant_id', true))" in text
