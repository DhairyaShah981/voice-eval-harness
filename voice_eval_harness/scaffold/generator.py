"""Generate a complete voxeval.yaml from an agent JSON + scenario library.

The generator is deliberately deterministic and template-based for v1.0
so it works without API keys. Pass ``--llm`` from the CLI to additionally
have gpt-4o rewrite the user_says lines into realistic, agent-specific
phrasing (uses one OpenAI call per case; budget-tracked).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from voice_eval_harness.scaffold.agent_parser import AgentMeta, ToolSpec
from voice_eval_harness.scaffold.healthcare_library import render_scenarios


def _toolcall_case(tool: ToolSpec) -> dict[str, Any]:
    """One scripted case per tool — exercises the happy path that should
    trigger it. Adds an ``assert_tool_called`` + ``assert_tool_shape``
    derived from the tool's declared parameter schema."""
    require: dict[str, Any] = {}
    for pname, pdef in tool.parameters.items():
        if not isinstance(pdef, dict):
            continue
        ptype = pdef.get("type") or "string"
        rule: dict[str, Any] = {"type": ptype}
        if "enum" in pdef:
            rule["in"] = pdef["enum"]
        if "minimum" in pdef:
            rule["min"] = pdef["minimum"]
        if "maximum" in pdef:
            rule["max"] = pdef["maximum"]
        if "pattern" in pdef:
            rule["regex"] = pdef["pattern"]
        require[pname] = rule

    # Plain-English user prompt that should plausibly trigger the tool.
    desc = (tool.description or tool.name or "").lower()
    if "availabil" in desc or "slot" in desc or "open" in desc:
        user_says = "Can you check what slots are open next week?"
    elif "book" in desc or "schedule" in desc or "create" in desc:
        user_says = "Please book that appointment for me."
    elif "cancel" in desc:
        user_says = "I need to cancel my appointment."
    elif "reschedul" in desc:
        user_says = "I'd like to reschedule my appointment."
    elif "lookup" in desc or "find" in desc or "search" in desc:
        user_says = "Can you look up my existing appointment?"
    elif "eligib" in desc or "insurance" in desc:
        user_says = "Can you verify my insurance coverage?"
    elif "transfer" in desc:
        user_says = "Please transfer me to a human."
    else:
        user_says = f"I'd like to {tool.name.replace('_', ' ')}."

    case: dict[str, Any] = {
        "id": f"tool_{tool.name}",
        "description": (
            f"Auto-generated: agent should call {tool.name!r} on this prompt. "
            f"Tool description: {tool.description!r}"
        ),
        "script": [
            {
                "user_says": user_says,
                "asserts": [
                    {"assert_tool_called": tool.name},
                ],
            },
        ],
        "suite_asserts": ["assert_no_crash"],
    }
    if require:
        case["script"][0]["asserts"].append({
            "assert_tool_shape": {
                "tool_name": tool.name,
                "require": require,
            },
        })
    return case


def build_provider_block(meta: AgentMeta) -> dict[str, Any]:
    """Build the ``provider:`` section of the YAML."""
    block: dict[str, Any]
    if meta.provider == "vapi":
        block = {
            "name": "vapi",
            "api_key": "${VAPI_API_KEY}",
            "agent_id": "REPLACE_WITH_VAPI_ASSISTANT_ID",
        }
    else:
        block = {
            "name": "retell",
            "api_key": "${RETELL_API_KEY}",
            "agent_id": "REPLACE_WITH_RETELL_AGENT_ID",
        }
    return block


def _maybe_filter_for_specialty(
    cases: list[dict[str, Any]], meta: AgentMeta,
) -> list[dict[str, Any]]:
    """Trim multilingual cases if the agent doesn't support a second language."""
    is_monolingual_en = (
        meta.language.lower().startswith("en")
        and "multi" not in (meta.languages_supported or [])
    )
    if not is_monolingual_en:
        return cases
    drop_ids = {"language_drift_spanish", "persona_code_switching_caller"}
    return [c for c in cases if c.get("id") not in drop_ids]


def _maybe_add_kb_assertion(cases: list[dict[str, Any]], meta: AgentMeta) -> None:
    """If the agent has a KB wired up, append a KB-coverage block at the end."""
    if not meta.has_knowledge_base:
        return
    # noop here — the kb_coverage block lives at the suite root, added by build_suite.


def build_suite(
    meta: AgentMeta,
    *,
    clinic_defaults: dict[str, str] | None = None,
    include_scenarios: bool = True,
    include_tool_calls: bool = True,
    include_personas: bool = True,
) -> dict[str, Any]:
    """Compose the complete voxeval.yaml dict from agent metadata."""
    cases: list[dict[str, Any]] = []

    if include_tool_calls:
        for tool in meta.tools:
            cases.append(_toolcall_case(tool))

    if include_scenarios:
        scenarios = render_scenarios(clinic_defaults)
        if not include_personas:
            scenarios = [s for s in scenarios if "persona" not in s]
        scenarios = _maybe_filter_for_specialty(scenarios, meta)
        cases.extend(scenarios)

    suite: dict[str, Any] = {
        "# Auto-generated by `voxeval generate`": None,
        f"# Source agent: {meta.agent_name!r} ({meta.provider})": None,
        f"# Detected specialty: {meta.detected_specialty or 'unspecified'}": None,
        f"# Languages: {','.join(meta.languages_supported)}": None,
        f"# Tools discovered: {len(meta.tools)} ({', '.join(t.name for t in meta.tools)})": None,
        "provider": build_provider_block(meta),
        "defaults": {"mode": "text", "timeout_s": 45,
                     "judge_model": "gpt-4o-mini-2024-07-18"},
        "cases": cases,
    }
    return suite


def write_suite_yaml(suite: dict[str, Any], path: Path) -> None:
    """Render the suite dict as YAML, with sentinel `None` keys turned
    into top-of-file comments."""

    class _NoNoneDumper(yaml.SafeDumper):
        pass

    header_lines: list[str] = []
    body: dict[str, Any] = {}
    for k, v in suite.items():
        if v is None and isinstance(k, str) and k.startswith("#"):
            header_lines.append(k)
        else:
            body[k] = v

    yaml_str = yaml.dump(
        body, Dumper=_NoNoneDumper, sort_keys=False, allow_unicode=True,
    )
    text = "\n".join(header_lines) + "\n\n" + yaml_str
    path.write_text(text)
