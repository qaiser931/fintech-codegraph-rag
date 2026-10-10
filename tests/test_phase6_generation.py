"""Phase 6 tests: Answer Generation (prompt builder + CodeRAGGenerator).

These tests run fully offline — the LLM backend is replaced with a
``unittest.mock`` stub, so no API key or network access is required.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from typing import List, Optional
from unittest.mock import MagicMock, patch, patch as _patch

import pytest

from src.generation.generator import (
    CodeRAGGenerator,
    GeneratedAnswer,
    _extract_citations,
    _negated_grounding_terms,
    _validate_grounding,
)
from src.generation.prompt_builder import build_prompts
from src.ingestion.chunker import CodeChunk
from src.retrieval.hybrid import RetrievalResult, RetrievedChunk


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_chunk(
    symbol: str,
    file_path: str = "services/payment.py",
    start: int = 1,
    end: int = 10,
    security: str = "internal",
    content: str = "def foo(): pass",
) -> CodeChunk:
    return CodeChunk(
        doc_id=f"{file_path}::{symbol}",
        symbol_name=symbol,
        symbol_type="function",
        file_path=file_path,
        start_line=start,
        end_line=end,
        security_level=security,
        content=content,
        search_text=content,
    )


def _make_result(
    query: str = "Why does JazzCash callback timeout?",
    role: str = "Senior Dev",
    n_chunks: int = 3,
    with_paths: bool = False,
) -> RetrievalResult:
    chunks = [_make_chunk(f"func_{i}", start=i * 10, end=i * 10 + 9) for i in range(n_chunks)]
    items = [
        RetrievedChunk(chunk=c, source="hybrid", rrf_score=0.9 - i * 0.1, rerank_score=-0.5 * i)
        for i, c in enumerate(chunks)
    ]
    paths = [["services/payment.py::func_0", "services/payment.py::func_1"]] if with_paths else []
    return RetrievalResult(
        query=query,
        role=role,
        items=items,
        execution_paths=paths,
    )


# ---------------------------------------------------------------------------
# Prompt builder tests
# ---------------------------------------------------------------------------

class TestBuildPrompts:
    def test_returns_two_nonempty_strings(self):
        result = _make_result()
        sys_p, user_p = build_prompts(result, [])
        assert isinstance(sys_p, str) and len(sys_p) > 50
        assert isinstance(user_p, str) and len(user_p) > 50

    def test_system_prompt_contains_role(self):
        for role in ["Junior Dev", "Senior Dev", "Security Lead"]:
            result = _make_result(role=role)
            sys_p, _ = build_prompts(result, [])
            assert role in sys_p

    def test_user_prompt_contains_query(self):
        query = "What is the signing key rotation policy?"
        result = _make_result(query=query)
        _, user_p = build_prompts(result, [])
        assert query in user_p

    def test_context_blocks_numbered(self):
        result = _make_result(n_chunks=3)
        _, user_p = build_prompts(result, [])
        assert "[1]" in user_p
        assert "[2]" in user_p
        assert "[3]" in user_p

    def test_execution_paths_section_present_when_given(self):
        paths = ["func_0 → func_1 → func_2"]
        result = _make_result()
        _, user_p = build_prompts(result, paths)
        assert "Execution Paths" in user_p
        assert "func_0 → func_1 → func_2" in user_p

    def test_execution_paths_section_absent_when_empty(self):
        result = _make_result()
        _, user_p = build_prompts(result, [])
        assert "Execution Paths" not in user_p

    def test_security_lead_persona_mentions_security(self):
        result = _make_result(role="Security Lead")
        sys_p, _ = build_prompts(result, [])
        assert any(w in sys_p.lower() for w in ["security", "attack", "secret", "hmac"])

    def test_symbol_names_appear_in_context(self):
        result = _make_result(n_chunks=2)
        _, user_p = build_prompts(result, [])
        for item in result.items:
            assert item.chunk.symbol_name in user_p


# ---------------------------------------------------------------------------
# Citation extraction tests
# ---------------------------------------------------------------------------

class TestExtractCitations:
    def test_basic_citation(self):
        result = _make_result(n_chunks=3)
        cited = _extract_citations("See [1] and [3] for details.", result)
        assert result.items[0].chunk.doc_id in cited
        assert result.items[2].chunk.doc_id in cited

    def test_out_of_range_citation_ignored(self):
        result = _make_result(n_chunks=2)
        cited = _extract_citations("As shown in [99].", result)
        assert cited == []

    def test_no_citations(self):
        result = _make_result(n_chunks=2)
        cited = _extract_citations("No references here.", result)
        assert cited == []

    def test_duplicate_citations_deduped(self):
        result = _make_result(n_chunks=3)
        cited = _extract_citations("See [1] again [1] and [2].", result)
        assert len(cited) == 2


class TestClaimLevelGrounding:
    @staticmethod
    def _result_with_evidence() -> RetrievalResult:
        result = _make_result(n_chunks=2)
        result.items[0].chunk.symbol_name = "verify_signature"
        result.items[0].chunk.content = (
            "def verify_signature(payload):\n"
            "    return validate_signature(payload)"
        )
        result.items[1].chunk.symbol_name = "acquire_lock"
        result.items[1].chunk.content = (
            "def acquire_lock(account):\n"
            "    return lock_account(account)"
        )
        return result

    def test_cited_claim_supported_by_evidence_is_accepted(self):
        result = self._result_with_evidence()

        accepted, citations = _validate_grounding(
            "verify_signature validates the payload [1].",
            result,
        )

        assert accepted is True
        assert citations == [result.items[0].chunk.doc_id]

    def test_valid_citation_with_unsupported_claim_is_rejected(self):
        result = self._result_with_evidence()

        accepted, citations = _validate_grounding(
            "The payment service sends signing secrets to an attacker "
            "during every callback request [1].",
            result,
        )

        assert accepted is False
        assert citations == [result.items[0].chunk.doc_id]

    def test_negative_claim_against_positive_evidence_is_rejected(self):
        result = self._result_with_evidence()

        accepted, _ = _validate_grounding(
            "verify_signature does not validate the payload [1].",
            result,
        )

        assert accepted is False

    def test_positive_claim_against_negative_evidence_is_rejected(self):
        result = self._result_with_evidence()
        result.items[0].chunk.content = (
            "# does not validate the payload\n"
            + result.items[0].chunk.content
        )

        accepted, _ = _validate_grounding(
            "verify_signature validates the payload [1].",
            result,
        )

        assert accepted is False

    def test_matching_negative_claim_and_evidence_are_accepted(self):
        result = self._result_with_evidence()
        result.items[0].chunk.content = (
            "def verify_signature(payload):\n"
            "    # does not validate the payload\n"
            "    return payload"
        )

        accepted, citations = _validate_grounding(
            "verify_signature does not validate the payload [1].",
            result,
        )

        assert accepted is True
        assert citations == [result.items[0].chunk.doc_id]

    def test_multiple_supported_claims_with_valid_citations_are_accepted(self):
        result = self._result_with_evidence()

        accepted, citations = _validate_grounding(
            "verify_signature validates the payload [1]. "
            "acquire_lock locks the account [2].",
            result,
        )

        assert accepted is True
        assert citations == [
            result.items[0].chunk.doc_id,
            result.items[1].chunk.doc_id,
        ]

    def test_compound_claim_with_opposite_polarity_clause_is_rejected(self):
        result = self._result_with_evidence()

        accepted, _ = _validate_grounding(
            "verify_signature validates the payload and does not validate "
            "the payload [1].",
            result,
        )

        assert accepted is False

    @pytest.mark.parametrize(
        ("phrase", "target"),
        [
            ("not validate", "validate"),
            ("no authentication", "authentication"),
            ("never validate", "validate"),
            ("without validation", "validation"),
            ("cannot validate", "validate"),
            ("can't validate", "validate"),
            ("does not validate", "validate"),
            ("doesn't validate", "validate"),
            ("is not valid", "valid"),
            ("isn't valid", "valid"),
            ("are not valid", "valid"),
            ("aren't valid", "valid"),
            ("was not valid", "valid"),
            ("wasn't valid", "valid"),
            ("were not valid", "valid"),
            ("weren't valid", "valid"),
        ],
    )
    def test_common_negation_forms_are_detected(self, phrase: str, target: str):
        negated_terms = _negated_grounding_terms(phrase)

        assert target in negated_terms

    def test_malformed_or_missing_citations_keep_safe_rejection(self):
        result = self._result_with_evidence()

        malformed, _ = _validate_grounding(
            "The signature validator checks payload fields [99].",
            result,
        )
        missing, _ = _validate_grounding(
            "The signature validator checks payload fields before processing requests.",
            result,
        )
        short_nonfactual, short_citations = _validate_grounding("Okay.", result)

        assert malformed is False
        assert missing is False
        assert short_nonfactual is True
        assert short_citations == []

    def test_supported_generated_answer_remains_unchanged(self):
        result = self._result_with_evidence()
        retriever = _make_mock_retriever(result)
        generator = CodeRAGGenerator(
            retriever,
            provider="openai",
            model="gpt-4o-mini",
            api_key="test-key",
        )
        supported_answer = "verify_signature validates the payload [1]."
        fake_backend = MagicMock(return_value=(supported_answer, 20, 10))

        with patch.dict("src.generation.generator._PROVIDERS", {"openai": fake_backend}):
            generated = generator.generate("Does this validate the payload?")

        assert generated.answer == supported_answer
        assert generated.citations == [result.items[0].chunk.doc_id]

    def test_unsupported_generated_answer_uses_safe_fallback(self):
        result = self._result_with_evidence()
        retriever = _make_mock_retriever(result)
        generator = CodeRAGGenerator(
            retriever,
            provider="openai",
            model="gpt-4o-mini",
            api_key="test-key",
        )
        fake_backend = MagicMock(
            return_value=(
                "The payment service sends signing secrets to an attacker "
                "during every callback request [1].",
                20,
                10,
            )
        )

        with patch.dict("src.generation.generator._PROVIDERS", {"openai": fake_backend}):
            generated = generator.generate("What does the validator do?")

        assert "attacker" not in generated.answer
        assert "Evidence-based assessment" in generated.answer


# ---------------------------------------------------------------------------
# CodeRAGGenerator tests (LLM mocked out)
# ---------------------------------------------------------------------------

def _make_mock_retriever(result: RetrievalResult) -> MagicMock:
    retriever = MagicMock()
    retriever.retrieve.return_value = result
    # graph.nodes[n].get("symbol_name", n)
    node_mock = MagicMock()
    node_mock.get.side_effect = lambda key, default=None: default
    retriever.graph.nodes.__getitem__.return_value = node_mock
    return retriever


class TestCodeRAGGenerator:

    def _make_generator(self, result: RetrievalResult, provider: str = "openai") -> CodeRAGGenerator:
        retriever = _make_mock_retriever(result)
        return CodeRAGGenerator(retriever, provider=provider, model="gpt-4o-mini", api_key="test-key")

    def test_unknown_provider_raises(self):
        result = _make_result()
        retriever = _make_mock_retriever(result)
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            CodeRAGGenerator(retriever, provider="fakeai")

    def test_generate_returns_generated_answer(self):
        result = _make_result()
        gen = self._make_generator(result)
        fake_response = ("The timeout occurs due to [1] missing retry logic.", 100, 50)
        fake_backend = MagicMock(return_value=fake_response)
        with patch.dict("src.generation.generator._PROVIDERS", {"openai": fake_backend}):
            answer = gen.generate("Why timeout?", role="Senior Dev")

        assert isinstance(answer, GeneratedAnswer)
        assert "timeout" in answer.answer.lower()
        assert answer.provider == "openai"
        assert answer.model == "gpt-4o-mini"
        assert answer.prompt_tokens == 100
        assert answer.completion_tokens == 50
        assert answer.total_tokens == 150
        assert answer.latency_ms >= 0

    def test_citations_extracted_from_answer(self):
        result = _make_result(n_chunks=3)
        gen = self._make_generator(result)
        fake_answer = "Based on [1] and [2], the issue is clear."
        fake_backend = MagicMock(return_value=(fake_answer, 80, 30))
        with patch.dict("src.generation.generator._PROVIDERS", {"openai": fake_backend}):
            answer = gen.generate("test query")

        assert result.items[0].chunk.doc_id in answer.citations
        assert result.items[1].chunk.doc_id in answer.citations
        assert len(answer.citations) == 2

    def test_precomputed_result_skips_retrieval(self):
        precomputed = _make_result()
        retriever = _make_mock_retriever(precomputed)
        gen = CodeRAGGenerator(retriever, provider="openai", api_key="k")
        fake_backend = MagicMock(return_value=("ok", 10, 5))
        with patch.dict("src.generation.generator._PROVIDERS", {"openai": fake_backend}):
            gen.generate("q", retrieval_result=precomputed)

        retriever.retrieve.assert_not_called()

    def test_to_dict_serialisable(self):
        result = _make_result()
        gen = self._make_generator(result)
        fake_backend = MagicMock(return_value=("answer [1]", 20, 10))
        with patch.dict("src.generation.generator._PROVIDERS", {"openai": fake_backend}):
            answer = gen.generate("q")

        d = answer.to_dict()
        assert d["provider"] == "openai"
        assert d["total_tokens"] == 30
        assert isinstance(d["citations"], list)

    def test_role_passed_through_to_retriever(self):
        result = _make_result(role="Security Lead")
        retriever = _make_mock_retriever(result)
        gen = CodeRAGGenerator(retriever, provider="openai", api_key="k")
        fake_backend = MagicMock(return_value=("ok", 5, 5))
        with patch.dict("src.generation.generator._PROVIDERS", {"openai": fake_backend}):
            gen.generate("q", role="Security Lead")

        retriever.retrieve.assert_called_once()
        _, kwargs = retriever.retrieve.call_args
        # role may be positional or keyword
        call_args = retriever.retrieve.call_args
        assert "Security Lead" in str(call_args)
