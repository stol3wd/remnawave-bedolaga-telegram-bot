import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def migration():
    path = Path('migrations/alembic/versions/0132_free_access_until_quota.py')
    spec = importlib.util.spec_from_file_location('m0132', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_preserves_history_indexes_and_delete_guard():
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE subscriptions (id INTEGER PRIMARY KEY)')
        connection.exec_driver_sql("""CREATE TABLE grace_access_sessions (
            id TEXT PRIMARY KEY, subscription_id INTEGER REFERENCES subscriptions(id) ON DELETE CASCADE,
            state TEXT NOT NULL, started_at DATETIME NOT NULL, grace_until DATETIME NOT NULL,
            completed_at DATETIME, completion_reason VARCHAR(16),
            CONSTRAINT ck_grace_access_sessions_dates CHECK (grace_until > started_at),
            CONSTRAINT ck_grace_access_sessions_completion CHECK (
                (state = 'completed' AND completion_reason IN ('paid','timeout','drained','conflict','revoked')
                 AND completed_at IS NOT NULL) OR (state <> 'completed' AND completion_reason IS NULL AND completed_at IS NULL))
        )""")
        connection.exec_driver_sql('CREATE UNIQUE INDEX incident_test ON grace_access_sessions(subscription_id, id)')
        connection.exec_driver_sql('INSERT INTO subscriptions VALUES (1), (2)')
        connection.exec_driver_sql(
            "INSERT INTO grace_access_sessions VALUES ('old',1,'completed','2026-01-01','2026-01-02','2026-01-02','paid')"
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration().upgrade()
        assert (
            connection.exec_driver_sql(
                "SELECT completion_reason FROM grace_access_sessions WHERE id='old'"
            ).scalar_one()
            == 'paid'
        )
        assert any(
            index['name'] == 'incident_test' for index in sa.inspect(connection).get_indexes('grace_access_sessions')
        )
        connection.exec_driver_sql(
            "INSERT INTO grace_access_sessions VALUES ('quota',2,'active','2026-01-01',NULL,NULL,NULL)"
        )
        with pytest.raises(sa.exc.IntegrityError, match='open grace-access session'):
            connection.exec_driver_sql('DELETE FROM subscriptions WHERE id=2')
        with Operations.context(MigrationContext.configure(connection)), pytest.raises(RuntimeError, match='history'):
            migration().downgrade()
        connection.exec_driver_sql(
            "UPDATE grace_access_sessions SET state='completed', completed_at='2026-01-02', completion_reason='quota_exhausted' WHERE id='quota'"
        )
        connection.exec_driver_sql('DELETE FROM subscriptions WHERE id=2')
        connection.exec_driver_sql("DELETE FROM grace_access_sessions WHERE id='quota'")
        with Operations.context(MigrationContext.configure(connection)):
            migration().downgrade()
        column = next(
            item
            for item in sa.inspect(connection).get_columns('grace_access_sessions')
            if item['name'] == 'grace_until'
        )
        assert column['nullable'] is False
