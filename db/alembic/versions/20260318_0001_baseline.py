"""Baseline schema managed by Alembic."""

from __future__ import annotations

from pathlib import Path

from alembic import op


revision = "20260318_0001"
down_revision = None
branch_labels = None
depends_on = None


def _read_sql(filename: str) -> str:
    sql_path = Path(__file__).resolve().parents[1] / "sql" / filename
    return sql_path.read_text(encoding="utf-8")


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_read_sql("001_baseline_up.sql"))


def downgrade() -> None:
    op.get_bind().exec_driver_sql(_read_sql("001_baseline_down.sql"))
