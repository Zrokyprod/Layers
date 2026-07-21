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


def test_applied_mcp_revision_remains_traversable_and_dropped_forward() -> None:
    migration_root = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    tombstone = (migration_root / "0122_mcp_interception.py").read_text(encoding="utf-8")
    final_domain = (migration_root / "0123_create_final_domain_tables.py").read_text(encoding="utf-8")
    drop_mcp = (migration_root / "0129_drop_mcp_interception_tables.py").read_text(encoding="utf-8")

    assert 'revision = "0122_mcp_interception"' in tombstone
    assert 'down_revision = "0121_add_user_totp_mfa"' in tombstone
    assert 'down_revision = "0122_mcp_interception"' in final_domain
    assert "DROP TABLE IF EXISTS mcp_interception_events CASCADE" in drop_mcp
    assert "DROP TABLE IF EXISTS mcp_tool_bindings CASCADE" in drop_mcp
