"""Prompt construction for the CodeGraph RAG answer engine.

Builds grounded prompts from retrieved code context and execution paths.
The prompt is intentionally strict so the LLM does not invent causes,
symbols, behaviours, or recommendations that are not supported by the
retrieved evidence.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, List, Tuple

if TYPE_CHECKING:
    from src.retrieval.hybrid import RetrievalResult


# ---------------------------------------------------------------------------
# Role persona fragments
# ---------------------------------------------------------------------------

_ROLE_PERSONA: dict[str, str] = {
    "Junior Dev": (
        "You are a helpful senior engineer. Explain clearly without assuming "
        "deep knowledge of authentication or payment-gateway internals."
    ),
    "Senior Dev": (
        "You are a principal engineer conducting a technical deep-dive. "
        "Be precise, trace the actual code path, and discuss performance "
        "implications only when supported by the retrieved code."
    ),
    "Security Lead": (
        "You are a senior application-security architect. Highlight "
        "security-relevant behaviour only when it is directly supported "
        "by the retrieved code."
    ),
}

_DEFAULT_PERSONA = (
    "You are an expert software-engineering assistant specialising in "
    "fintech payment systems and secure API design."
)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_TEMPLATE = """\
{persona}

You are answering a question about a real software codebase.

The user question must be answered using ONLY the retrieved code context and
the explicitly provided execution paths.

STRICT GROUNDING RULES:

1. Do NOT use outside knowledge to invent code behaviour.
2. Do NOT invent symbols, functions, classes, files, variables, errors,
   configuration values, database behaviour, network behaviour, or causes.
3. Every factual claim about the code MUST have a citation in the form [N],
   where N is the numbered retrieved context block containing the evidence.
4. A citation must support the claim it follows. Do not cite unrelated code.
5. If a claim cannot be directly supported by the retrieved context, do NOT
   present it as a fact.
6. If evidence is incomplete, explicitly say:
   "The retrieved code does not provide enough evidence to establish this."
7. Do NOT recommend a fix unless the retrieved code provides enough evidence
   to explain the relevant problem. If you mention a possible improvement,
   clearly label it as a suggestion rather than an established fact.
8. Do NOT infer database connection-pool exhaustion, thread exhaustion,
   network behaviour, infrastructure behaviour, deployment configuration,
   production traffic characteristics, or external service behaviour unless
   the retrieved context explicitly shows it.
9. Do NOT convert comments such as "Defect", "WARNING", or "prone to"
   into stronger claims than the code supports.
10. Prefer the actual execution path over unrelated retrieved chunks.
11. When an execution path is provided, explain the sequence in that path
    using the corresponding retrieved context blocks.
12. Do not cite execution-path text itself as evidence. Cite the numbered
    code block that proves each step.
13. Never output a citation such as [99] if there is no context block [99].
14. If there is insufficient evidence for a definitive root cause, use
    cautious wording such as "the retrieved code indicates" or
    "the available evidence suggests".
15. Do not fabricate HTTP status codes, timeout values, SQL behaviour,
    retry counts, latency values, or configuration values.

ANSWER FORMAT:

- Start with a concise direct answer.
- Then explain the relevant execution sequence.
- Identify the strongest evidence from the retrieved code.
- Distinguish confirmed evidence from inference.
- Use citations immediately after the supported statement.
- End with an "Evidence status" statement:
  - "Supported" when the retrieved code directly establishes the answer.
  - "Partially supported" when the retrieved code establishes part of the
    explanation but not the complete cause.
  - "Insufficient evidence" when the retrieved code cannot establish the
    requested explanation.

CITATION EXAMPLE:

"The callback handler calls the payment service [1]. The payment service
then acquires the account lock before calling the 1LINK verification method
[3]. The 1LINK verification method is wrapped by the retry decorator [5]."

IMPORTANT:
The example above is only an example of citation formatting. Do not reuse
its facts unless those facts actually appear in the retrieved context.

Role: {role}
"""


# ---------------------------------------------------------------------------
# User prompt
# ---------------------------------------------------------------------------

_USER_TEMPLATE = """\
## Retrieved Code Context

{context_blocks}
{path_section}

## Question

{query}

## Final Instructions

Answer the question using only the retrieved evidence above.

For every factual statement about the code, include the appropriate [N]
citation immediately after the statement.

If the evidence does not establish the complete cause, do not guess.
Clearly separate:
- Confirmed evidence
- Reasonable inference
- Missing evidence

Do not invent missing infrastructure or production details.
"""


# ---------------------------------------------------------------------------
# Context formatting
# ---------------------------------------------------------------------------

def _format_context_blocks(result: "RetrievalResult") -> str:
    """Render retrieved chunks as numbered code blocks."""

    lines: List[str] = []

    for idx, item in enumerate(result.items, start=1):
        c = item.chunk

        rel_path = Path(c.file_path).as_posix()

        source_tag = (
            f" [{item.source}]"
            if item.source
            else ""
        )

        header = (
            f"### [{idx}] `{c.symbol_name}` — "
            f"{rel_path}:{c.start_line}-{c.end_line}{source_tag}"
        )

        lines.append(header)
        lines.append("```python")
        lines.append(c.content.strip())
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Execution-path formatting
# ---------------------------------------------------------------------------

def _format_execution_paths(
    path_summaries: List[str],
) -> str:
    """Format execution paths for the user prompt."""

    if not path_summaries:
        return ""

    path_lines = "\n".join(
        f"- {path}"
        for path in path_summaries
    )

    return (
        "## Execution Paths\n\n"
        f"{path_lines}\n\n"
    )


# ---------------------------------------------------------------------------
# Public prompt builder
# ---------------------------------------------------------------------------

def build_prompts(
    result: "RetrievalResult",
    path_summaries: List[str],
) -> Tuple[str, str]:
    """Return ``(system_prompt, user_prompt)`` for the LLM.

    The resulting prompts enforce evidence-grounded answers, numbered
    citations, explicit uncertainty, and execution-path reasoning.
    """

    persona = _ROLE_PERSONA.get(
        result.role,
        _DEFAULT_PERSONA,
    )

    system_prompt = _SYSTEM_TEMPLATE.format(
        persona=persona,
        role=result.role,
    )

    context_blocks = _format_context_blocks(result)

    path_section = _format_execution_paths(
        path_summaries
    )

    user_prompt = _USER_TEMPLATE.format(
        context_blocks=context_blocks,
        path_section=path_section,
        query=result.query,
    )

    return system_prompt, user_prompt