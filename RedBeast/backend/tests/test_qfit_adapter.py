"""Integration boundaries only; paid APIs and astronomy archives are never contacted."""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from blinkspace.api import RateLimiter
from blinkspace.assistant import ChatInput, build_assistant_router
from blinkspace.assistant_commands import CONFIRM, validate_command
from blinkspace.assistant_qfit import Knowledge, UsageLedger, local_answer, local_sources, make_registry, run_qfit


def client():
    app = FastAPI()
    app.include_router(build_assistant_router(RateLimiter))
    return TestClient(app)


@pytest.mark.parametrize('target_id', ['barnard', 'eps-indi-b', 'wise-0855', 'rw-aur', 'r-dra'])
@pytest.mark.parametrize('question', ['Ne görüyorum?', 'Bu sayı nereden geliyor?'])
def test_five_target_source_cards_without_key(target_id, question, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('BLINKSPACE_ASSISTANT_PROVIDER', raising=False)
    with client() as c:
        response = c.post('/api/assistant/knowledge', json={'message': question, 'context': {'target': {'id': target_id}, 'ui_language': 'tr'}})
        assert response.status_code == 200
        result = response.json()
        assert result['message_source'] == 'system'
        assert result['meta']['ai_model'] is None
        assert result['sources'][0]['id'] == f'target:{target_id}'
        assert 'temsili' in result['uncertainty'][0]
        for source in result['sources']:
            if source['url'].startswith('/api/'):
                assert c.get(source['url']).status_code == 200
            else:
                assert source['url'].startswith('https://')


def test_source_lookup_does_not_accept_paths():
    with client() as c:
        assert c.get('/api/assistant/sources/%2E%2E%2F.env').status_code == 404
        assert c.post('/api/assistant/knowledge', json={'message': 'x', 'context': {'notes': 'private'}}).status_code == 422


def test_qfit_missing_key_and_vendor_do_not_break_status(monkeypatch):
    from blinkspace import assistant_qfit as q
    monkeypatch.setenv('BLINKSPACE_ASSISTANT_PROVIDER', 'qfit')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    with client() as c:
        assert c.get('/api/assistant/status').json()['reason'] == 'missing_key'
        monkeypatch.setattr(q, 'load_vendor', lambda: (_ for _ in ()).throw(ImportError()))
        assert c.get('/api/assistant/status').json()['reason'] == 'qfit_unavailable'
        assert c.post('/api/assistant/chat', json={'message': 'x'}).status_code == 503
        assert c.post('/api/assistant/knowledge', json={'message': 'x'}).status_code == 200


def test_durable_model_budget_is_atomic_and_survives_restart(tmp_path):
    path = tmp_path / 'usage.sqlite'
    with ThreadPoolExecutor(max_workers=8) as pool:
        reservations = list(pool.map(lambda _: UsageLedger(path, clock=lambda: 80000).reserve(6), range(30)))
    assert sum(reservations) == 6
    assert not UsageLedger(path, clock=lambda: 80000).reserve(6)
    assert UsageLedger(path, clock=lambda: 90000).reserve(6)
    assert not UsageLedger(path, clock=lambda: 180000).reserve(0)


@pytest.mark.parametrize('name,args', [('shell', {}), ('set_year', {'year': True}), ('set_year', {'year': float('nan')}), ('set_year', {'year': 2101}), ('save_view', {'path': '/tmp/test'}), ('start_search', {'ra': 1, 'dec': 2, 'ra_unit': 'deg', 'fov_arcmin': 6})])
def test_invalid_proposals_are_rejected(name, args):
    assert not validate_command(name, args)


def test_only_local_knowledge_and_validated_ui_proposals_are_registered():
    proposals = []
    registry = make_registry(Knowledge(), proposals)
    assert set(registry.names()) == {'search_knowledge_base', 'propose_ui_command'}
    async def check():
        assert not (await registry.execute('submit_candidate_for_review', {}))['ok']
        assert not (await registry.execute('propose_ui_command', {'name': 'set_year', 'args': {'year': -1}}))['ok']
        assert not (await registry.execute('propose_ui_command', {'name': 'select_target', 'args': {'target_id': 'fake'}}))['ok']
        for name in CONFIRM:
            args = {} if name == 'save_view' else {'ra': '269.4', 'dec': '4.7', 'ra_unit': 'deg', 'fov_arcmin': 6}
            result = await registry.execute('propose_ui_command', {'name': name, 'args': args})
            assert result['ok'] and result['result']['executed'] is False
            assert result['result']['requires_confirmation'] is True
    asyncio.run(check())
    assert len(proposals) == 2


def completed(text):
    return {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': text}]}]}


def test_original_openai_provider_has_privacy_budget_and_priority_guards(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-not-a-key')
    recorded = []
    def reply(request):
        recorded.append(json.loads(request.content))
        return httpx.Response(200, json=completed('Representative surface [epistemic#labels].'))
    async def check():
        return await run_qfit(ChatInput(message='PRIVATE_FIXTURE', context={'target': {'id': 'barnard'}, 'ui_language': 'en'}), transport=httpx.MockTransport(reply), ledger=UsageLedger(tmp_path / 'usage.sqlite'))
    response, proposals, errors = asyncio.run(check())
    body = recorded[0]
    assert body['model'] == 'gpt-5.4-mini' and body['store'] is False
    assert 128 <= body['max_output_tokens'] <= 4096
    assert body['instructions'].index("You are QFIT, RedBeast's optional assistant") < body['instructions'].index('Q-FIT persona (subordinate)')
    assert 'illustrative_education' in body['instructions']
    assert 'not the selected target' in body['instructions']
    assert {t['name'] for t in body['tools']} == {'search_knowledge_base', 'propose_ui_command'}
    assert response['message_source'] == 'ai_generated' and response['sources']
    assert 'K1' in response['sources'][0]['citation_labels']
    assert any(s['url'].startswith('https://') for s in response['sources'])
    assert not proposals and not errors
    assert 'PRIVATE_FIXTURE' not in caplog.text and 'fixture-not-a-key' not in caplog.text


def test_incomplete_model_response_fails_instead_of_claiming_success(tmp_path):
    async def check():
        with pytest.raises(Exception, match='incomplete'):
            await run_qfit(ChatInput(message='test'), transport=httpx.MockTransport(lambda _: httpx.Response(200, json={'status': 'incomplete', 'output': []})), ledger=UsageLedger(tmp_path / 'usage.sqlite'))
    asyncio.run(check())


def test_browser_cancellation_cancels_pending_model_request(tmp_path):
    async def check():
        entered, cancelled = asyncio.Event(), asyncio.Event()
        async def pending(_):
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
        task = asyncio.create_task(run_qfit(ChatInput(message='test'), transport=httpx.MockTransport(pending), ledger=UsageLedger(tmp_path / 'usage.sqlite')))
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled.is_set()
    asyncio.run(check())


def test_sse_completion_and_fallback_are_truthfully_labelled(monkeypatch):
    from blinkspace import assistant_qfit as q
    monkeypatch.setenv('BLINKSPACE_ASSISTANT_PROVIDER', 'qfit')
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-not-a-key')
    async def fake(body):
        response = {**local_answer(body), 'message_source': 'ai_generated', 'message': 'Fixture answer'}
        return response, [{'tool_use_id': 'p1', 'name': 'save_view', 'args': {}, 'requires_confirmation': True}], []
    monkeypatch.setattr(q, 'run_qfit', fake)
    with client() as c:
        r = c.post('/api/assistant/chat', json={'message': 'test'})
        assert r.status_code == 200
        names = [b.splitlines()[0][7:] for b in r.text.strip().split('\n\n')]
        assert names == ['text', 'command', 'sources', 'done']
        assert '"requires_confirmation":true' in r.text
        async def fail(_):
            raise RuntimeError('PRIVATE_FAILURE')
        monkeypatch.setattr(q, 'run_qfit', fail)
        r = c.post('/api/assistant/chat', json={'message': 'test'})
        assert 'PRIVATE_FAILURE' not in r.text
        assert '"message_source":"system"' in r.text
        assert r.text.strip().split('\n\n')[-1].startswith('event: done')


def test_model_tool_round_trip_is_validated_and_never_executes(tmp_path):
    calls = []
    def reply(request):
        body = json.loads(request.content); calls.append(body)
        if len(calls) == 1:
            return httpx.Response(200, json={'status': 'completed', 'output': [{'type': 'function_call', 'name': 'propose_ui_command', 'call_id': 'call1', 'arguments': json.dumps({'name': 'set_year', 'args': {'year': 2050}})}]})
        assert any(i.get('type') == 'function_call_output' and i['call_id'] == 'call1' for i in body['input'])
        return httpx.Response(200, json=completed('A year change was proposed; awaiting your click.'))
    async def check():
        return await run_qfit(ChatInput(message='Set year'), transport=httpx.MockTransport(reply), ledger=UsageLedger(tmp_path / 'usage.sqlite'))
    response, proposals, errors = asyncio.run(check())
    assert len(proposals) == 1 and proposals[0]['args'] == {'year': 2050}
    assert response['meta']['tools_called'] == ['propose_ui_command'] and not errors
