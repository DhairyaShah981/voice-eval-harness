"""Prompts the analyzer sends to Claude (or fallback LLM)."""

from __future__ import annotations

SYSTEM_PROMPT = """\
You are a senior voice-AI evaluator analyzing a corpus of phone-call
transcripts between a healthcare voice agent and real patients. The
transcripts have been PHI-scrubbed; patient identifiers appear as
<redacted:phone> / <redacted:dob> / etc.

Your job: read the corpus and produce a structured analysis that will
become the seed of an automated regression test suite for THIS specific
clinic. Be specific to the call patterns you actually see — generic
healthcare advice is useless here.

Output ONLY a JSON object matching the schema in the user message. No
prose outside the JSON. Use the exact field names. Empty arrays are
fine if a category has no examples.
"""

USER_PROMPT_TEMPLATE = """\
CLINIC METADATA
  agent_id:        {agent_id}
  agent_name:      {agent_name}
  detected_specialty: {specialty}
  call_count_sampled: {n_calls}  (out of {n_total} total in window)
  knowledge_base_md_chars: {kb_chars}

CORPUS (transcripts, oldest first):
{corpus}

KNOWLEDGE BASE (markdown, may be empty):
{kb}

OUTPUT SCHEMA — produce exactly this shape:

{{
  "summary": "<2-3 sentence narrative of what this clinic's calls look like>",
  "happy_paths": [
    {{
      "name": "<short id, snake_case>",
      "description": "<one sentence>",
      "user_says_examples": ["<verbatim or close-paraphrase opener from a real call>", "..."],
      "expected_tool_calls": ["<tool_name if visible in transcripts>"],
      "frequency": "<approx N/M of sampled calls>"
    }}
  ],
  "failure_modes": [
    {{
      "name": "<short id>",
      "description": "<one sentence: what went wrong, with which kind of caller>",
      "user_says_examples": ["<real opener that led to this failure>"],
      "agent_failure_pattern": "<what the agent did wrong — hallucinated, looped, hung up, ignored signal>",
      "occurred_in_calls": <int>
    }}
  ],
  "derived_scenarios": [
    {{
      "id": "<unique snake_case id, prefixed with clinic slug>",
      "description": "<one sentence>",
      "script": [
        {{"user_says": "<utterance>"}},
        {{"user_says": "<follow-up>", "asserts": [
          {{"assert_llm_judge": "<criterion the agent must satisfy>"}}
        ]}}
      ],
      "suite_asserts": ["assert_no_crash"]
    }}
  ],
  "kb_coverage_gaps": [
    "<one sentence per fact that callers asked about but the KB does not document>"
  ],
  "recommended_tool_shapes": [
    {{
      "tool_name": "<from transcripts>",
      "observed_args": [{{"arg_name": "<example_value>"}}],
      "suggested_assertions": ["<one sentence per assert_tool_shape rule>"]
    }}
  ]
}}

Cap derived_scenarios at 12. Prioritize scenarios that are not already
covered by the generic healthcare library (which already includes:
new_patient happy path, returning_patient, urgent triage,
insurance_verification, provider_preference, reschedule, cancel,
wrong_number, after_hours, rx_refill, transfer_to_human, referral,
language drift). Focus on clinic-specific patterns: provider names,
insurance quirks, intake workflows, specialty-specific symptoms,
local/regional caller idioms, recurring tool-call sequences.
"""


def render_user_prompt(
    *, agent_id: str, agent_name: str | None,
    specialty: str | None, n_calls: int, n_total: int,
    corpus_text: str, kb_text: str,
) -> str:
    return USER_PROMPT_TEMPLATE.format(
        agent_id=agent_id,
        agent_name=agent_name or "<unnamed>",
        specialty=specialty or "unspecified",
        n_calls=n_calls,
        n_total=n_total,
        kb_chars=len(kb_text),
        corpus=corpus_text,
        kb=kb_text or "(no KB markdown provided)",
    )


def assemble_corpus_text(records: list, *, max_chars: int = 60_000) -> str:
    """Format records into a numbered text block, truncating to a cap so
    we don't blow past the model's context window."""
    parts: list[str] = []
    used = 0
    for i, r in enumerate(records):
        header = (f"\n--- call #{i+1}  id={r.call_id}  "
                  f"disconnect={r.disconnect_reason}  "
                  f"duration_ms={r.duration_ms} ---\n")
        block = header + (r.transcript or "")
        if used + len(block) > max_chars:
            parts.append(
                f"\n--- (corpus truncated at {max_chars} chars; "
                f"{len(records) - i} more calls omitted) ---"
            )
            break
        parts.append(block)
        used += len(block)
    return "\n".join(parts)
