"""Merge agent runtime migration heads.

This revision reconciles the branch introduced by the structured run result
contract migration with the main agent runtime migration chain so
``alembic upgrade head`` resolves to a single target.
"""

from __future__ import annotations


revision = "20260331_0006"
down_revision = ("20260326_0007", "20260331_0005")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
