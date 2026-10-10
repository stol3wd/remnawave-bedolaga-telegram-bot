"""Allow one-time free access sessions without a time deadline.

Revision ID: 0132
Revises: 0131
"""

import sqlalchemy as sa
from alembic import op

revision = '0132'
down_revision = '0131'
branch_labels = None
depends_on = None


def _completion(reasons: str) -> str:
    return (
        f"(state = 'completed' AND completion_reason IS NOT NULL AND completion_reason IN ({reasons}) "
        "AND completed_at IS NOT NULL) OR (state <> 'completed' AND completion_reason IS NULL AND completed_at IS NULL)"
    )


def _alter(*, upgrade: bool) -> None:
    sqlite = op.get_bind().dialect.name == 'sqlite'
    if sqlite:
        # SQLite validates triggers while rebuilding the referenced table.
        op.execute('DROP TRIGGER IF EXISTS trg_guard_open_grace_subscription_delete')
    with op.batch_alter_table('grace_access_sessions') as batch:
        batch.drop_constraint('ck_grace_access_sessions_dates', type_='check')
        batch.drop_constraint('ck_grace_access_sessions_completion', type_='check')
        batch.alter_column('grace_until', existing_type=sa.DateTime(timezone=True), nullable=upgrade)
        batch.create_check_constraint(
            'ck_grace_access_sessions_dates',
            'grace_until IS NULL OR grace_until > started_at' if upgrade else 'grace_until > started_at',
        )
        reasons = "'paid', 'timeout', 'drained', 'conflict', 'revoked'"
        if upgrade:
            reasons += ", 'quota_exhausted'"
        batch.create_check_constraint('ck_grace_access_sessions_completion', _completion(reasons))
    if sqlite:
        op.execute("""
            CREATE TRIGGER trg_guard_open_grace_subscription_delete
            BEFORE DELETE ON subscriptions FOR EACH ROW
            WHEN EXISTS (SELECT 1 FROM grace_access_sessions WHERE subscription_id = OLD.id
                         AND state IN ('pending', 'active', 'restoring'))
            BEGIN SELECT RAISE(ABORT, 'subscription has an open grace-access session'); END
        """)


def upgrade() -> None:
    _alter(upgrade=True)


def downgrade() -> None:
    rows = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM grace_access_sessions WHERE grace_until IS NULL OR completion_reason = 'quota_exhausted'"
            )
        )
        .scalar_one()
    )
    if rows:
        raise RuntimeError('Quota sessions exist: downgrade would lose their history; restore a pre-upgrade DB backup')
    _alter(upgrade=False)
