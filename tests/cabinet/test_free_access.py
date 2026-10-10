from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.cabinet.routes.subscription_modules.status import claim_free_access, free_access_info
from app.config import settings
from app.services.grace_access_runtime import grace_access_runtime


@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint', [free_access_info, claim_free_access])
async def test_free_access_uses_subscription_owner_filter(monkeypatch, endpoint):
    monkeypatch.setattr(type(settings), 'is_multi_tariff_enabled', lambda _self: True)
    monkeypatch.setattr(settings, 'GRACE_ACCESS_EXPIRED_UNTIL_QUOTA', True)
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None)))
    consider = AsyncMock()
    monkeypatch.setattr(grace_access_runtime, 'consider_candidate', consider)
    with pytest.raises(HTTPException) as error:
        await endpoint(user=SimpleNamespace(id=7), db=db, subscription_id=99)
    assert error.value.status_code == 404
    params = db.execute.call_args.args[0].compile().params
    assert params['id_1'] == 99 and params['user_id_1'] == 7
    consider.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_free_access_cannot_be_claimed(monkeypatch):
    monkeypatch.setattr(type(settings), 'is_multi_tariff_enabled', lambda _self: True)
    monkeypatch.setattr(settings, 'GRACE_ACCESS_EXPIRED_UNTIL_QUOTA', False)
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(id=99)))
    )
    with pytest.raises(HTTPException) as error:
        await claim_free_access(user=SimpleNamespace(id=7), db=db, subscription_id=99)
    assert error.value.status_code == 409
