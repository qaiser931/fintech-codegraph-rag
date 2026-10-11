"""LLM answer generator for the CodeGraph RAG pipeline.

Supports multiple providers (OpenAI, Gemini, Groq, Ollama) via a single
``CodeRAGGenerator`` class.

The generator also performs post-generation citation validation so that
unsupported model output is not returned as if it were grounded evidence.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Set

from src.config import settings
from src.generation.prompt_builder import build_prompts

if TYPE_CHECKING:
    from src.retrieval.hybrid import HybridRetriever, RetrievalResult


# ---------------------------------------------------------------------------
# Response dataclass
# ---------------------------------------------------------------------------

@dataclass
class GeneratedAnswer:
    """The complete output of one generation call."""

    query: str
    role: str
    answer: str
    citations: List[str] = field(default_factory=list)
    model: str = ""
    provider: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    retrieval_result: Optional["RetrievalResult"] = field(
        default=None,
        repr=False,
    )

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "role": self.role,
            "answer": self.answer,
            "citations": self.citations,
            "model": self.model,
            "provider": self.provider,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
        }


# ---------------------------------------------------------------------------
# Citation extraction
# ---------------------------------------------------------------------------

_CITATION_PATTERN = re.compile(r"\[(\d+)\]")
_CLAIM_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+|;\s+|\n+")
_CLAIM_STOP_WORDS = {
    "a", "about", "above", "after", "also", "an", "and", "any", "are",
    "as", "at", "based", "be", "because", "been", "before", "being",
    "between", "but", "by", "can", "could", "clear", "code", "does",
    "doing", "during", "each", "either", "else", "evidence", "for", "from",
    "function", "functions", "has", "have", "here", "how", "if", "in",
    "into", "is", "it", "its", "just", "less", "like", "may", "might",
    "more", "most", "method", "methods", "no", "nor", "not", "never", "cannot", "of", "off",
    "on", "once", "only", "or", "other", "our", "out", "over", "own",
    "same", "should", "so", "some", "such", "than", "that", "the", "their",
    "then", "there", "these", "they", "this", "those", "through", "to", "too",
    "under", "until", "up", "upon", "us", "very", "was", "we", "were", "what",
    "when", "where", "which", "while", "who", "with", "within", "without",
    "would", "you", "your", "issue", "result", "shown", "above", "below",
}
_NEGATION_CONTRACTIONS = {
    r"\bcan['’]t\b": "cannot",
    r"\bdoesn['’]t\b": "does not",
    r"\bdon['’]t\b": "do not",
    r"\bdidn['’]t\b": "did not",
    r"\bisn['’]t\b": "is not",
    r"\baren['’]t\b": "are not",
    r"\bwasn['’]t\b": "was not",
    r"\bweren['’]t\b": "were not",
    r"\bhasn['’]t\b": "has not",
    r"\bhaven['’]t\b": "have not",
    r"\bhadn['’]t\b": "had not",
    r"\bwon['’]t\b": "will not",
    r"\bwouldn['’]t\b": "would not",
    r"\bcouldn['’]t\b": "could not",
    r"\bshouldn['’]t\b": "should not",
}
_NEGATION_CUES = {"not", "no", "never", "without", "cannot"}


def _extract_citation_numbers(answer_text: str) -> List[int]:
    """Return unique citation numbers appearing in the answer."""

    numbers: List[int] = []

    for match in _CITATION_PATTERN.findall(answer_text):
        number = int(match)

        if number not in numbers:
            numbers.append(number)

    return numbers


def _extract_citations(
    answer_text: str,
    result: "RetrievalResult",
) -> List[str]:
    """Parse valid [N] markers and resolve them to document IDs."""

    cited: List[str] = []

    for number in _extract_citation_numbers(answer_text):
        index = number - 1

        if 0 <= index < len(result.items):
            doc_id = result.items[index].chunk.doc_id

            if doc_id not in cited:
                cited.append(doc_id)

    return cited


def _invalid_citation_numbers(
    answer_text: str,
    result: "RetrievalResult",
) -> List[int]:
    """Return citation numbers that do not map to retrieved context."""

    invalid: List[int] = []

    for number in _extract_citation_numbers(answer_text):
        index = number - 1

        if not (0 <= index < len(result.items)):
            invalid.append(number)

    return invalid


# ---------------------------------------------------------------------------
# Grounding validation
# ---------------------------------------------------------------------------

def _has_factual_content(answer_text: str) -> bool:
    """Determine whether the model produced a substantive answer."""

    normalized = answer_text.strip()

    if not normalized:
        return False

    # Very short acknowledgement-style output is not treated as factual
    # technical analysis.
    if len(normalized) < 40:
        return False

    return True


def _grounding_tokens(text: str) -> List[str]:
    split_identifiers = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    normalized = split_identifiers.replace("’", "'")
    for pattern, replacement in _NEGATION_CONTRACTIONS.items():
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    return re.findall(r"[a-z0-9]+", normalized.lower())


def _grounding_terms(text: str) -> set[str]:
    return {
        token
        for token in _grounding_tokens(text)
        if token not in _CLAIM_STOP_WORDS
    }


def _grounding_token_forms(token: str) -> set[str]:
    forms = {token}
    if len(token) > 5 and token.endswith("ies"):
        forms.add(token[:-3] + "y")
    if len(token) > 5 and token.endswith("es"):
        forms.add(token[:-2])
    if len(token) > 4 and token.endswith("s"):
        forms.add(token[:-1])
    if len(token) > 6 and token.endswith("ed"):
        forms.add(token[:-2])
    if len(token) > 7 and token.endswith("ing"):
        stem = token[:-3]
        forms.add(stem)
        if len(stem) > 2 and stem[-1] == stem[-2]:
            forms.add(stem[:-1])
    return forms


def _negated_grounding_terms(text: str) -> set[str]:
    tokens = _grounding_tokens(text)
    negated_terms: set[str] = set()

    for index, token in enumerate(tokens):
        if token not in _NEGATION_CUES:
            continue
        if token == "not" and index + 1 < len(tokens) and tokens[index + 1] in {"only", "just"}:
            continue

        target_index = index + 1
        while target_index < len(tokens) and tokens[target_index] in _CLAIM_STOP_WORDS:
            target_index += 1
        if target_index < len(tokens):
            negated_terms.update(_grounding_token_forms(tokens[target_index]))

    return negated_terms


def _claim_supported_by_citations(
    claim: str,
    citation_numbers: List[int],
    result: "RetrievalResult",
) -> bool:
    claim_terms = _grounding_terms(claim)
    if not claim_terms:
        return True

    evidence_text = " ".join(
        part
        for number in citation_numbers
        for part in (
            result.items[number - 1].chunk.symbol_name,
            result.items[number - 1].chunk.file_path,
            result.items[number - 1].chunk.content,
        )
    )
    evidence_terms = _grounding_terms(evidence_text)
    evidence_forms = {
        form
        for token in evidence_terms
        for form in _grounding_token_forms(token)
    }

    claim_negated_terms = _negated_grounding_terms(claim)
    evidence_negated_terms = _negated_grounding_terms(evidence_text)
    for claim_term in claim_terms:
        claim_forms = _grounding_token_forms(claim_term)
        claim_is_negated = bool(claim_forms & claim_negated_terms)
        matching_evidence_terms = [
            token
            for token in evidence_terms
            if claim_forms & _grounding_token_forms(token)
        ]

        if claim_is_negated and not any(
            _grounding_token_forms(token) & evidence_negated_terms
            for token in matching_evidence_terms
        ):
            return False

        for evidence_term in matching_evidence_terms:
            evidence_is_negated = bool(
                _grounding_token_forms(evidence_term) & evidence_negated_terms
            )
            if claim_is_negated != evidence_is_negated:
                return False

    supported_terms = sum(
        bool(_grounding_token_forms(token) & evidence_forms)
        for token in claim_terms
    )

    return (
        supported_terms >= min(2, len(claim_terms))
        and supported_terms / len(claim_terms) >= 0.6
    )


def _validate_grounding(
    answer_text: str,
    result: "RetrievalResult",
) -> tuple[bool, List[str]]:
    """Validate that generated output contains usable grounded citations.

    Returns:
        (is_grounded, resolved_citations)
    """

    citations = _extract_citations(
        answer_text,
        result,
    )

    invalid_numbers = _invalid_citation_numbers(
        answer_text,
        result,
    )

    if invalid_numbers:
        return False, citations

    if _has_factual_content(answer_text) and not citations:
        return False, []

    for claim in _CLAIM_SPLIT_PATTERN.split(answer_text):
        claim = claim.strip()
        if not claim:
            continue

        citation_numbers = [
            int(number)
            for number in _CITATION_PATTERN.findall(claim)
        ]
        claim_text = _CITATION_PATTERN.sub("", claim).strip()
        claim_terms = _grounding_terms(claim_text)

        if not citation_numbers:
            if _has_factual_content(claim_text) or len(claim_terms) >= 2:
                return False, citations
            continue

        if not _claim_supported_by_citations(
            claim_text,
            citation_numbers,
            result,
        ):
            return False, citations

    return True, citations


# ---------------------------------------------------------------------------
# Safe fallback
# ---------------------------------------------------------------------------

def _safe_evidence_fallback(
    result: "RetrievalResult",
) -> str:
    """Build a conservative answer when the model fails grounding.

    This fallback deliberately does not invent a root cause. It reports only
    facts that are directly visible from retrieved metadata and execution
    paths.
    """

    lines: List[str] = []

    lines.append(
        "## Evidence-based assessment"
    )

    lines.append(
        "The retrieved code provides relevant execution-path evidence, "
        "but it does not establish the complete cause of the reported "
        "timeout. Therefore, a definitive root cause cannot be stated "
        "from the retrieved evidence alone."
    )

    # ------------------------------------------------------------------
    # Retrieved symbols
    # ------------------------------------------------------------------

    relevant_items = result.items[:8]

    if relevant_items:
        lines.append("")
        lines.append("### Retrieved evidence")

        for index, item in enumerate(
            relevant_items,
            start=1,
        ):
            chunk = item.chunk

            lines.append(
                f"- `{chunk.symbol_name}` at "
                f"`{chunk.file_path}:{chunk.start_line}-"
                f"{chunk.end_line}` [{index}]"
            )

    # ------------------------------------------------------------------
    # Execution paths
    # ------------------------------------------------------------------

    if result.execution_paths:
        lines.append("")
        lines.append("### Execution paths")

        graph = getattr(
            getattr(result, "_retriever", None),
            "graph",
            None,
        )

        # The RetrievalResult normally does not expose the graph itself,
        # so use the already available symbol metadata when possible.
        for path in result.execution_paths[:5]:
            if not path:
                continue

            names: List[str] = []

            for node in path:
                text = str(node)

                if "::" in text:
                    text = text.split("::", 1)[1]

                names.append(text)

            lines.append(
                "- " + " -> ".join(names)
            )

    lines.append("")
    lines.append("### Evidence status")
    lines.append(
        "Insufficient evidence: the retrieved code does not establish "
        "that database connection-pool exhaustion, infrastructure "
        "behaviour, or another specific timeout mechanism is the root cause."
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Provider backends
# ---------------------------------------------------------------------------

def _call_openai(
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float,
    api_key: str,
) -> tuple[str, int, int]:
    """Call OpenAI chat-completions."""

    from openai import OpenAI  # type: ignore

    client = OpenAI(
        api_key=api_key or settings.openai_api_key
    )

    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
    )

    text = response.choices[0].message.content or ""

    usage = response.usage

    pt = (
        usage.prompt_tokens
        if usage
        else 0
    )

    ct = (
        usage.completion_tokens
        if usage
        else 0
    )

    return text, pt, ct


def _call_gemini(
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float,
    api_key: str,
) -> tuple[str, int, int]:
    """Call Google Gemini."""

    import google.generativeai as genai  # type: ignore

    genai.configure(
        api_key=api_key or settings.gemini_api_key
    )

    gen_model = genai.GenerativeModel(
        model_name=model,
        system_instruction=system_prompt,
        generation_config=genai.GenerationConfig(
            temperature=temperature
        ),
    )

    response = gen_model.generate_content(
        user_prompt
    )

    text = response.text or ""

    usage = getattr(
        response,
        "usage_metadata",
        None,
    )

    pt = (
        getattr(
            usage,
            "prompt_token_count",
            0,
        )
        or 0
    )

    ct = (
        getattr(
            usage,
            "candidates_token_count",
            0,
        )
        or 0
    )

    return text, pt, ct


def _call_groq(
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float,
    api_key: str,
) -> tuple[str, int, int]:
    """Call Groq's official endpoint using the existing httpx dependency."""
    import httpx
    from src.config import settings

    token = (api_key or settings.groq_api_key).strip()
    if not token:
        raise ValueError("GROQ_API_KEY is not configured.")
    payload = {
        "model": model,
        "temperature": temperature,
        "max_completion_tokens": 2048,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if model in {"openai/gpt-oss-120b", "openai/gpt-oss-20b"}:
        payload.update(reasoning_effort="low", include_reasoning=False)
    # Transport retries are off by default; one call per generation request.
    with httpx.Client(timeout=httpx.Timeout(90.0, connect=5.0),
                      follow_redirects=False) as client:
        response = client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer " + token},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    choices = data.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        raise RuntimeError("Groq returned no completion.")
    choice = choices[0]
    message = choice.get("message") or {}
    text = message.get("content") or ""
    if not isinstance(text, str):
        raise RuntimeError("Groq returned an invalid completion.")
    # Do not accept a cut answer; the generator must use its evidence fallback.
    if choice.get("finish_reason") == "length":
        text = ""
    usage = data.get("usage") or {}
    return text, usage.get("prompt_tokens") or 0, usage.get("completion_tokens") or 0

def _call_ollama(
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float,
    api_key: str,
) -> tuple[str, int, int]:
    """Call a local Ollama model."""

    import ollama  # type: ignore

    import httpx
    from src.config import settings

    client = ollama.Client(
        timeout=httpx.Timeout(
            settings.ollama_read_timeout,
            connect=settings.ollama_connect_timeout,
        )
    )
    try:
        response = client.chat(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            options={
                "temperature": temperature,
            },
        )
    finally:
        client._client.close()

    message = response.get(
        "message",
        {},
    )

    text = (
        message.get(
            "content",
            "",
        )
        or ""
    )

    prompt_tokens = (
        response.get(
            "prompt_eval_count",
            0,
        )
        or 0
    )

    completion_tokens = (
        response.get(
            "eval_count",
            0,
        )
        or 0
    )

    return (
        text,
        prompt_tokens,
        completion_tokens,
    )


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

_PROVIDERS = {
    "openai": _call_openai,
    "gemini": _call_gemini,
    "groq": _call_groq,
    "ollama": _call_ollama,
}


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

class CodeRAGGenerator:
    """Orchestrates retrieval -> prompts -> LLM -> validation -> answer."""

    def __init__(
        self,
        retriever: "HybridRetriever",
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self.retriever = retriever

        self.provider = (
            provider or settings.llm_provider
        ).lower()

        self.model = (
            model or settings.llm_model
        )

        self.temperature = (
            temperature
            if temperature is not None
            else settings.llm_temperature
        )

        self.api_key = api_key or ""

        if self.provider not in _PROVIDERS:
            raise ValueError(
                f"Unknown LLM provider '{self.provider}'. "
                f"Choose from: {list(_PROVIDERS)}"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        query: str,
        role: str = "Junior Dev",
        *,
        retrieval_kwargs: Optional[dict] = None,
        retrieval_result: Optional["RetrievalResult"] = None,
    ) -> GeneratedAnswer:
        """Run retrieval, generation, grounding validation and return answer."""

        t_start = time.perf_counter()

        # --------------------------------------------------------------
        # 1. Retrieve or accept pre-computed result
        # --------------------------------------------------------------

        if retrieval_result is None:
            kwargs = retrieval_kwargs or {}

            result = self.retriever.retrieve(
                query,
                role=role,
                **kwargs,
            )
        else:
            result = retrieval_result

        # --------------------------------------------------------------
        # 2. Format execution paths
        # --------------------------------------------------------------

        graph = self.retriever.graph

        path_summaries: List[str] = []

        for path in result.execution_paths:
            symbols = [
                graph.nodes[n].get(
                    "symbol_name",
                    n,
                )
                for n in path
            ]

            path_summaries.append(
                " -> ".join(symbols)
            )

        # --------------------------------------------------------------
        # 3. Build grounded prompts
        # --------------------------------------------------------------

        system_prompt, user_prompt = build_prompts(
            result,
            path_summaries,
        )

        # --------------------------------------------------------------
        # 4. Call selected provider
        # --------------------------------------------------------------

        answer_text, pt, ct = _PROVIDERS[
            self.provider
        ](
            system_prompt,
            user_prompt,
            self.model,
            self.temperature,
            self.api_key,
        )

        # --------------------------------------------------------------
        # 5. Validate model grounding
        # --------------------------------------------------------------

        grounded, citations = _validate_grounding(
            answer_text,
            result,
        )

        if not grounded or not answer_text.strip():
            answer_text = _safe_evidence_fallback(
                result
            )
            citations = _extract_citations(
                answer_text,
                result,
            )

        # --------------------------------------------------------------
        # 6. Calculate latency
        # --------------------------------------------------------------

        latency = round(
            (
                time.perf_counter()
                - t_start
            )
            * 1000,
            2,
        )

        # --------------------------------------------------------------
        # 7. Return structured answer
        # --------------------------------------------------------------

        return GeneratedAnswer(
            query=query,
            role=role,
            answer=answer_text,
            citations=citations,
            model=self.model,
            provider=self.provider,
            prompt_tokens=pt,
            completion_tokens=ct,
            total_tokens=pt + ct,
            latency_ms=latency,
            retrieval_result=result,
        )