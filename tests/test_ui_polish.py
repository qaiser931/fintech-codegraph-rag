"""Verify changed investigation controls and honest result presentation."""
from pathlib import Path
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest
from ui import api_client

APP = Path(__file__).resolve().parents[1] / 'ui/app.py'


def button(at, label):
    next(x for x in at.button if x.label == label).click().run()
    assert not at.exception


@pytest.fixture
def investigation(monkeypatch):
    data = {'role': 'Senior Dev', 'latency_ms': 20, 'sources': [
        {'symbol_name': 'payment', 'file_path': 'services/payment.py', 'start_line': 1}],
        'call_path': ['callback', 'payment', 'settlement'], 'retrieved_items': []}
    retrieve = Mock(return_value=data)
    generate = Mock(return_value=dict(data, answer='Insufficient evidence to conclude.',
                                     status='INSUFFICIENT_EVIDENCE', citations=data['sources']))
    source = Mock(return_value='PRIVATE_SOURCE_CONTENT')
    monkeypatch.setattr(api_client, 'retrieve_api', retrieve)
    monkeypatch.setattr(api_client, 'query_api', generate)
    monkeypatch.setattr(api_client, 'fetch_source', source)
    at = AppTest.from_file(str(APP), default_timeout=10).run()
    at.selectbox[0].set_value('Senior Dev').run()
    assert not at.exception
    return at, retrieve, generate, source


def test_sample_selection_clears_source_and_waits_for_explicit_request(investigation):
    at, retrieve, generate, _ = investigation
    button(at, '🔍 Explore code')
    button(at, 'Open source')
    button(at, 'Webhook verification')
    assert at.text_area[0].value == 'Which function verifies the JazzCash webhook signature?'
    assert at.text_area[1].value == ''
    with pytest.raises(KeyError):
        at.session_state['last_result']
    assert not any('PRIVATE_SOURCE_CONTENT' in x.value for x in at.code)
    assert retrieve.call_count == 1
    generate.assert_not_called()
    button(at, '🔍 Explore code')
    assert retrieve.call_args.kwargs['query'] == at.text_area[0].value
    assert retrieve.call_args.kwargs['role'] == 'Senior Dev'


@pytest.mark.parametrize('field', [0, 1])
def test_editing_question_or_trace_removes_stale_result_and_source(investigation, field):
    at, *_ = investigation
    button(at, '🔍 Explore code')
    button(at, 'Open source')
    at.text_area[field].set_value('New investigation context').run()
    assert not at.exception
    with pytest.raises(KeyError):
        at.session_state['last_result']
    assert not any('PRIVATE_SOURCE_CONTENT' in x.value for x in at.code)


def test_insufficient_evidence_keeps_warning_status_and_inspectable_citations(investigation):
    at, _, generate, _ = investigation
    at.radio[0].set_value('Generate answer').run()
    button(at, '🚀 Generate answer')
    generate.assert_called_once()
    assert any('INSUFFICIENT EVIDENCE' in x.value for x in at.error)
    assert not at.success
    assert any(x.value == 'Insufficient evidence to conclude.' for x in at.markdown)
    button(at, 'Open source')
    assert any('PRIVATE_SOURCE_CONTENT' in x.value for x in at.code)


def test_one_returned_path_is_not_counted_as_multiple_paths(investigation):
    at, *_ = investigation
    button(at, '🔍 Explore code')
    metric = next(x for x in at.metric if x.label == 'Call paths')
    assert metric.value == '1'


def test_health_is_manual_and_cleared_when_api_changes(monkeypatch):
    response = Mock()
    response.json.return_value = {'status': 'healthy'}
    request = Mock(return_value=response)
    monkeypatch.setattr(api_client.requests, 'get', request)
    at = AppTest.from_file(str(APP), default_timeout=10).run()
    request.assert_not_called()
    button(at, 'Check API Health')
    request.assert_called_once()
    assert any('API responded healthy' in x.value for x in at.markdown)
    at.text_input[0].set_value('http://127.0.0.1:9000').run()
    assert any('API connection not checked' in x.value for x in at.markdown)
    assert not any('API responded healthy' in x.value for x in at.markdown)


def test_nonhealthy_response_is_not_shown_as_healthy(monkeypatch):
    response = Mock()
    response.json.return_value = {'status': 'unhealthy'}
    monkeypatch.setattr(api_client.requests, 'get', Mock(return_value=response))
    at = AppTest.from_file(str(APP), default_timeout=10).run()
    button(at, 'Check API Health')
    assert any('API unavailable or not healthy' in x.value for x in at.markdown)
    assert not any('API responded healthy' in x.value for x in at.markdown)


def test_new_html_cards_escape_api_supplied_symbol_and_path(investigation):
    at, retrieve, *_ = investigation
    retrieve.return_value['sources'][0]['symbol_name'] = '<script>private()</script>'
    retrieve.return_value['call_path'] = ['<img src=x onerror=private()>']
    button(at, '🔍 Explore code')
    custom = '\n'.join(x.value for x in at.markdown if x.allow_html)
    assert '&lt;script&gt;private()&lt;/script&gt;' in custom
    assert '&lt;img src=x onerror=private()&gt;' in custom
    assert '<script>private()' not in custom and '<img src=x' not in custom
