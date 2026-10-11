"""Mocked cloud adapter checks; no real key, cloud request or model load."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock
import sys
from types import SimpleNamespace

import httpx
import pytest

from src.generation.generator import _call_groq
mod = SimpleNamespace(_call_groq=_call_groq)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setitem(sys.modules, 'src.config', SimpleNamespace(
        settings=SimpleNamespace(groq_api_key='synthetic-test-key')))
    post = Mock(return_value=httpx.Response(200, json={
        'choices':[{'message':{'content':'Grounded answer [1].'},'finish_reason':'stop'}],
        'usage':{'prompt_tokens':123,'completion_tokens':45},
    },request=httpx.Request('POST','https://api.groq.com/openai/v1/chat/completions')))
    instance=Mock(post=post)
    context=Mock()
    context.__enter__=Mock(return_value=instance)
    context.__exit__=Mock(return_value=False)
    factory=Mock(return_value=context)
    monkeypatch.setattr(httpx,'Client',factory)
    return factory,context,post


def test_request_is_bounded_single_attempt_and_final_answer_only(client):
    factory,context,post=client
    assert mod._call_groq('system','question','openai/gpt-oss-120b',0,'') == (
        'Grounded answer [1].',123,45)
    factory.assert_called_once()
    timeout=factory.call_args.kwargs['timeout']
    assert timeout.read==90 and timeout.connect==5
    assert factory.call_args.kwargs['follow_redirects'] is False
    post.assert_called_once()
    assert post.call_args.args[0]=='https://api.groq.com/openai/v1/chat/completions'
    payload=post.call_args.kwargs['json']
    assert payload['max_completion_tokens']==2048
    assert payload['reasoning_effort']=='low' and payload['include_reasoning'] is False
    assert 'synthetic-test-key' not in str(payload)
    context.__exit__.assert_called_once()


def test_length_stop_rejects_partial_text_but_retains_usage(client):
    _,_,post=client
    post.return_value=httpx.Response(200,json={
        'choices':[{'message':{'content':'Partial answer [1].'},'finish_reason':'length'}],
        'usage':{'prompt_tokens':123,'completion_tokens':2048},
    },request=httpx.Request('POST','https://api.groq.com/openai/v1/chat/completions'))
    assert mod._call_groq('system','question','openai/gpt-oss-120b',0,'') == ('',123,2048)


@pytest.mark.parametrize('failure',[httpx.ReadTimeout('private-provider-detail'),
    httpx.HTTPStatusError('private-provider-detail',request=httpx.Request('POST','https://api.groq.com/openai/v1/chat/completions'),response=httpx.Response(429))])
def test_errors_close_client_without_retry(client,failure):
    _,context,post=client
    post.side_effect=failure
    with pytest.raises(type(failure)):
        mod._call_groq('system','question','openai/gpt-oss-120b',0,'')
    post.assert_called_once()
    context.__exit__.assert_called_once()


def test_non_reasoning_model_does_not_receive_gpt_oss_parameters(client):
    _,_,post=client
    mod._call_groq('system','question','other-model',0,'')
    assert 'reasoning_effort' not in post.call_args.kwargs['json']
    assert 'include_reasoning' not in post.call_args.kwargs['json']


@pytest.mark.asyncio
@pytest.mark.parametrize('upstream,expected,detail',[
    (429,429,'Cloud generation rate limit reached.'),
    (401,503,'Cloud generation credentials were rejected.'),
    (403,503,'Cloud generation credentials were rejected.'),
    (400,502,'Cloud generation request failed.'),
    (500,502,'Cloud generation request failed.'),
])
async def test_cloud_errors_are_sanitized_and_not_cached(upstream,expected,detail,caplog):
    from src.api.main import app
    from src.api.dependencies import get_generator,get_authenticated_role
    from src.telemetry import query_result_cache,metrics_store
    request=httpx.Request('POST','https://api.groq.com/openai/v1/chat/completions',headers={'Authorization':'Bearer synthetic-private-key'})
    failure=httpx.HTTPStatusError('synthetic-private-key',request=request,response=httpx.Response(upstream,json={'error':'private-source'}))
    generator=Mock(provider='groq')
    generator.generate.side_effect=failure
    app.dependency_overrides[get_generator]=lambda:generator
    app.dependency_overrides[get_authenticated_role]=lambda:'Junior Dev'
    query_result_cache.reset();metrics_store.reset()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as caller:
            response=await caller.post('/query',json={'query':'Groq error regression','role':'Junior Dev'})
        assert response.status_code==expected
        assert response.json()=={'detail':detail}
        assert 'synthetic-private-key' not in caplog.text and 'private-source' not in caplog.text
        assert len(query_result_cache)==0 and metrics_store.summary()['total_queries']==0
        generator.generate.assert_called_once()
    finally:
        app.dependency_overrides.pop(get_generator,None)
        app.dependency_overrides.pop(get_authenticated_role,None)
        query_result_cache.reset();metrics_store.reset()


def test_settings_do_not_serialize_or_display_groq_key():
    from src.config import Settings
    settings=Settings(_env_file=None,GROQ_API_KEY='synthetic-private-key')
    assert 'synthetic-private-key' not in repr(settings)
    assert 'groq_api_key' not in settings.model_dump()


@pytest.mark.parametrize('code,detail,expected',[
    (429,'private-source','rate limit'),
    (504,'private-source','timed out'),
    (503,'Cloud generation credentials were rejected.','credentials'),
])
def test_ui_cloud_errors_are_clear_without_exposing_body(code,detail,expected):
    import requests,json
    from ui.api_client import describe_query_error
    response=requests.Response();response.status_code=code
    response._content=json.dumps({'detail':detail}).encode()
    severity,message=describe_query_error(requests.HTTPError(response=response))
    assert expected in message and str(code) in message
    assert 'private-source' not in message
    if code in (429,504):
        assert severity=='warning' and 'No automatic retry' in message


def test_groq_cost_uses_separate_input_and_output_list_prices():
    from src.api.routes.query import _estimate_answer_cost
    answer=SimpleNamespace(provider='groq',model='openai/gpt-oss-120b',
                           prompt_tokens=1_000_000,completion_tokens=1_000_000,total_tokens=2_000_000)
    assert _estimate_answer_cost(answer)==0.75


def test_truncated_cloud_completion_becomes_insufficient_evidence(monkeypatch):
    from tests.test_phase6_generation import _make_result, _make_mock_retriever
    from src.generation.generator import CodeRAGGenerator, _PROVIDERS
    from src.api.routes.query import _classify_status
    result=_make_result(query='What does this function do?',role='Junior Dev')
    backend=Mock(return_value=('',123,2048))
    monkeypatch.setitem(_PROVIDERS,'groq',backend)
    generator=CodeRAGGenerator(_make_mock_retriever(result),provider='groq',
                               model='openai/gpt-oss-120b',api_key='synthetic-key')
    answer=generator.generate(result.query,role=result.role)
    assert answer.answer.strip() and 'Evidence-based assessment' in answer.answer
    assert answer.citations and answer.completion_tokens==2048
    assert _classify_status(answer.answer,len(answer.citations),len(result.items))=='INSUFFICIENT_EVIDENCE'
    backend.assert_called_once()
