from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.external.remnawave_api import RemnaWaveAPI, RemnaWaveFreeHostError


def api_fixture():
    RemnaWaveAPI._free_host_checks.clear()
    api = RemnaWaveAPI('https://panel.example', 'test-key')
    host = {
        'isDisabled': False,
        'isHidden': False,
        'inbound': {'configProfileUuid': 'profile', 'configProfileInboundUuid': 'inbound-uuid'},
        'internalSquads': {'mode': 'ALLOW_ONLY', 'squads': ['free-squad']},
        'nodes': [],
    }
    squad = {'inbounds': [{'uuid': 'inbound-uuid', 'tag': 'free-vless'}]}
    nodes = {'accessibleNodes': [{'uuid': 'node', 'configProfileUuid': 'profile', 'activeInbounds': ['free-vless']}]}
    responses = {
        '/api/hosts/host': host,
        '/api/internal-squads/free-squad': squad,
        '/api/config-profiles/profile': {'config': {'inbounds': [{'tag': 'free-vless', 'protocol': 'vless'}]}},
        '/api/internal-squads/free-squad/accessible-nodes': nodes,
    }

    async def request(_method, path):
        return {'response': responses[path]}

    api._make_request = request
    node = SimpleNamespace(uuid='node', is_disabled=False, is_connected=True)
    api.get_all_nodes = AsyncMock(return_value=[node])
    return api, host, squad, nodes, node


@pytest.mark.asyncio
async def test_accessible_nodes_returns_tags_and_disconnect_does_not_cancel_a_grant():
    api, _, _, nodes, node = api_fixture()
    await api.validate_free_access_host('host', 'free-squad')
    node.is_connected = False
    with pytest.raises(RemnaWaveFreeHostError):
        await api.validate_free_access_host('host', 'free-squad')
    await api.validate_free_access_host('host', 'free-squad', require_connected=False)
    nodes['accessibleNodes'][0]['activeInbounds'] = []
    RemnaWaveAPI._free_host_checks.clear()
    with pytest.raises(RemnaWaveFreeHostError):
        await api.validate_free_access_host('host', 'free-squad', require_connected=False)


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['isDisabled', 'isHidden'])
async def test_hidden_or_disabled_host_cannot_grant_access(field):
    api, host, _, _, _ = api_fixture()
    host[field] = True
    with pytest.raises(RemnaWaveFreeHostError):
        await api.validate_free_access_host('host', 'free-squad')


@pytest.mark.asyncio
async def test_free_squad_cannot_include_a_paid_inbound():
    api, _, squad, _, _ = api_fixture()
    squad['inbounds'].append({'uuid': 'paid-inbound', 'tag': 'paid'})
    with pytest.raises(RemnaWaveFreeHostError, match='only'):
        await api.validate_free_access_host('host', 'free-squad')


@pytest.mark.asyncio
async def test_metadata_write_requires_expected_value():
    api, _, _, _, _ = api_fixture()
    api._make_request = AsyncMock()
    await api.update_user_metadata(42, {'selectedHosts': ['host'], 'adminNote': 'keep'}, expected={'adminNote': 'keep'})
    api._make_request.assert_awaited_once_with(
        'PUT',
        '/api/metadata/user/42',
        {
            'metadata': {'selectedHosts': ['host'], 'adminNote': 'keep'},
            'expectedMetadata': {'adminNote': 'keep'},
        },
    )


@pytest.mark.asyncio
async def test_only_reconciliation_reuses_host_validation():
    api, host, _, _, _ = api_fixture()
    await api.validate_free_access_host('host', 'free-squad', require_connected=False)
    await api.validate_free_access_host('host', 'free-squad', require_connected=False)
    assert api.get_all_nodes.await_count == 1
    host['isDisabled'] = True
    with pytest.raises(RemnaWaveFreeHostError):
        await api.validate_free_access_host('host', 'free-squad')
