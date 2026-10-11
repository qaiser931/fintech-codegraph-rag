"""Documented facts, presentation labels and fabricated-value regressions."""
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.generation.generator import (
    CodeRAGGenerator, _PROVIDERS, _safe_evidence_fallback, _validate_grounding,
)
from src.api.routes.query import _classify_status
from tests.test_phase6_generation import _make_result, _make_mock_retriever


@pytest.fixture
def latency_result():
    result = _make_result(query='What is the expected 1LINK latency during peak traffic?',role='Junior Dev',n_chunks=1)
    chunk = result.items[0].chunk
    chunk.symbol_name = 'OneLinkSwitchClient.verify_switch_transaction'
    chunk.file_path = 'data/sample_codebase/integrations/onelink_client.py'
    chunk.doc_id = chunk.file_path + '::' + chunk.symbol_name
    chunk.content = (Path(__file__).resolve().parents[1] / chunk.file_path).read_text()
    return result


@pytest.mark.parametrize('header',['## Direct answer','**Confirmed evidence**','### Strongest evidence'])
def test_headings_and_status_do_not_reject_a_supported_fact(latency_result,header):
    answer = header + '\n1LINK peak latency fluctuates between 2.0s and 6.0s per request due to inter-member queueing [1].\n\n**Evidence status:** Supported'
    accepted,citations = _validate_grounding(answer,latency_result)
    assert accepted and citations == [latency_result.items[0].chunk.doc_id]
    assert _classify_status(answer,len(citations),1) == 'SUPPORTED'


def test_citation_after_sentence_punctuation_is_attached(latency_result):
    answer = '1LINK peak latency fluctuates between 2.0s and 6.0s per request. [1]'
    assert _validate_grounding(answer,latency_result)[0]


@pytest.mark.parametrize('values',['0.1s and 0.2s','2.0 milliseconds and 6.0 milliseconds','2.5s and 6.0s'])
def test_word_overlap_does_not_accept_invented_values_or_units(latency_result,values):
    answer = f'1LINK peak latency fluctuates between {values} per request due to inter-member queueing [1].'
    assert not _validate_grounding(answer,latency_result)[0]


def test_seconds_spelled_out_match_the_documented_units(latency_result):
    answer = '1LINK peak latency fluctuates between 2.0 seconds and 6.0 seconds per request due to inter-member queueing [1].'
    assert _validate_grounding(answer,latency_result)[0]


@pytest.mark.parametrize('answer',[
    '## The switch latency is 0.1s\nEvidence status: Supported',
    '1LINK peak latency fluctuates between 2.0s and 6.0s per request.\nEvidence status: Supported',
    '1LINK peak latency fluctuates between 2.0s and 6.0s per request [99].\nEvidence status: Supported',
])
def test_headings_status_and_invalid_citations_cannot_replace_factual_support(latency_result,answer):
    assert not _validate_grounding(answer,latency_result)[0]


def test_fallback_quotes_the_retrieved_docstring_for_this_question(latency_result):
    answer = _safe_evidence_fallback(latency_result)
    assert '2.0s and 6.0s' in answer and 'inter-member queueing' in answer
    assert 'database connection-pool' not in answer and 'reported timeout' not in answer
    assert _classify_status(answer,1,1) == 'SUPPORTED'


def test_fallback_values_are_extracted_not_hardcoded(latency_result):
    latency_result.items[0].chunk.content = latency_result.items[0].chunk.content.replace('2.0s and 6.0s','3.5s and 7.5s')
    answer = _safe_evidence_fallback(latency_result)
    assert '3.5s and 7.5s' in answer and '2.0s and 6.0s' not in answer


@pytest.mark.parametrize('question',[
    'Why does peak 1LINK latency cause the callback timeout?',
    'What is the actual measured 1LINK latency during peak traffic?',
    'What is the expected JazzCash latency during peak traffic?',
])
def test_documented_value_does_not_answer_causal_measured_or_other_provider_questions(latency_result,question):
    latency_result.query = question
    answer = _safe_evidence_fallback(latency_result)
    assert answer.startswith('## Evidence-based assessment')
    assert 'database connection-pool' not in answer and 'reported timeout' not in answer
    assert _classify_status(answer,1,1) == 'INSUFFICIENT_EVIDENCE'


def test_conflicting_documented_ranges_keep_cautious_status(latency_result):
    from copy import deepcopy
    other = deepcopy(latency_result.items[0])
    other.chunk.doc_id += '-other'
    other.chunk.content = other.chunk.content.replace('2.0s and 6.0s','3.0s and 9.0s')
    latency_result.items.append(other)
    assert _safe_evidence_fallback(latency_result).startswith('## Evidence-based assessment')


@pytest.mark.parametrize('response',[
    '## Direct answer\n1LINK peak latency fluctuates between 2.0s and 6.0s per request [1].\nEvidence status: Supported',
    '1LINK peak latency fluctuates between 0.1s and 0.2s per request [1].',
    '',
])
def test_generation_preserves_or_quotes_supported_latency_without_retry(latency_result,monkeypatch,response):
    backend = Mock(return_value=(response,100,30))
    monkeypatch.setitem(_PROVIDERS,'groq',backend)
    generator = CodeRAGGenerator(_make_mock_retriever(latency_result),provider='groq',model='openai/gpt-oss-120b',api_key='synthetic-key')
    answer = generator.generate(latency_result.query,role=latency_result.role)
    assert '2.0s' in answer.answer and '6.0s' in answer.answer
    assert '0.1s' not in answer.answer and answer.prompt_tokens == 100
    assert _classify_status(answer.answer,len(answer.citations),1) == 'SUPPORTED'
    backend.assert_called_once()


def test_explicit_partial_and_insufficient_statuses_are_respected():
    assert _classify_status('Evidence status: Partially supported',2,2) == 'PARTIALLY_SUPPORTED'
    assert _classify_status('Evidence status: Insufficient evidence',2,2) == 'INSUFFICIENT_EVIDENCE'
