"""Parse a Retell or Vapi agent definition into a uniform metadata struct."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]   # JSONSchema-shaped properties dict
    required: list[str]


@dataclass(frozen=True)
class AgentMeta:
    """Provider-agnostic snapshot of an agent for scenario generation."""

    provider: Literal["retell", "vapi", "unknown"]
    agent_name: str
    language: str
    languages_supported: list[str]    # ["en"] or ["en","es","multi"]
    voice_id: str | None
    global_prompt: str
    node_names: list[str]             # for Retell conversation-flow agents
    tools: list[ToolSpec]
    knowledge_base_ids: list[str]
    has_knowledge_base: bool          # KB IDs present (not empty)
    references_kb_in_prompt: bool     # prompt text mentions "KB doc" / "knowledge base"
    detected_specialty: str | None    # heuristic from prompt text ("cardiology", "ENT", ...)
    raw: dict[str, Any] = field(default_factory=dict)


_KB_REFERENCES = re.compile(
    r"\b(?:knowledge\s+base|kb\s+doc|knowledge[-_]base|knowledge-base)\b", re.I,
)

_SPECIALTY_HINTS = {
    "cardiology":   ("cardiology", "cardiologist", "heart", "ekg", "stress test"),
    "ent":          ("ent", "ear nose throat", "otolaryngology", "audiology", "hearing"),
    "ophthalmology":("eye", "retina", "ophthalmolog", "glaucoma", "cataract"),
    "endoscopy":    ("endoscopy", "colonoscopy", "gi clinic", "gastro"),
    "dermatology":  ("derm", "skin", "rash"),
    "ortho":        ("ortho", "joint", "knee", "shoulder", "fracture"),
    "primary_care": ("primary care", "family medicine", "pcp"),
    "ob_gyn":       ("ob/gyn", "ob gyn", "obstetric", "gynecolog"),
    "pediatrics":   ("pediatric", "pediatrician"),
}


def _detect_specialty(text: str) -> str | None:
    low = text.lower()
    for specialty, hints in _SPECIALTY_HINTS.items():
        if any(h in low for h in hints):
            return specialty
    return None


def _parse_retell(d: dict[str, Any]) -> AgentMeta:
    cf = d.get("conversationFlow") or {}
    tools_raw = cf.get("tools") or []
    tools: list[ToolSpec] = []
    for t in tools_raw:
        if not isinstance(t, dict):
            continue
        params = t.get("parameters") or {}
        tools.append(ToolSpec(
            name=t.get("name") or t.get("tool_id") or "<unknown>",
            description=t.get("description") or "",
            parameters=params.get("properties") or {},
            required=params.get("required") or [],
        ))
    global_prompt = cf.get("global_prompt") or d.get("global_prompt") or ""
    node_names = [
        (n.get("name") or n.get("id") or "")
        for n in cf.get("nodes") or []
        if isinstance(n, dict)
    ]
    kb_ids = cf.get("knowledge_base_ids") or d.get("knowledge_base_ids") or []
    language = d.get("language") or "en-US"
    langs = [language] if language != "multi" else ["en", "es", "zh", "multi"]
    return AgentMeta(
        provider="retell",
        agent_name=d.get("agent_name") or "Untitled Retell Agent",
        language=language,
        languages_supported=langs,
        voice_id=d.get("voice_id"),
        global_prompt=global_prompt,
        node_names=node_names,
        tools=tools,
        knowledge_base_ids=list(kb_ids),
        has_knowledge_base=bool(kb_ids),
        references_kb_in_prompt=bool(_KB_REFERENCES.search(global_prompt)),
        detected_specialty=_detect_specialty(global_prompt + " " + (d.get("agent_name") or "")),
        raw=d,
    )


def _parse_vapi(d: dict[str, Any]) -> AgentMeta:
    model = d.get("model") or {}
    messages = model.get("messages") or []
    system_msg = next(
        (m.get("content", "") for m in messages
         if isinstance(m, dict) and m.get("role") == "system"),
        "",
    )
    tools_raw = model.get("tools") or []
    tools: list[ToolSpec] = []
    for t in tools_raw:
        if not isinstance(t, dict):
            continue
        fn = t.get("function") or t
        params = fn.get("parameters") or {}
        tools.append(ToolSpec(
            name=fn.get("name") or "<unknown>",
            description=fn.get("description") or "",
            parameters=params.get("properties") or {},
            required=params.get("required") or [],
        ))
    voice = d.get("voice") or {}
    transcriber = d.get("transcriber") or {}
    language = transcriber.get("language") or "en"
    langs = [language] if language != "multi" else ["en", "es", "multi"]
    return AgentMeta(
        provider="vapi",
        agent_name=d.get("name") or "Untitled Vapi Assistant",
        language=language,
        languages_supported=langs,
        voice_id=voice.get("voiceId") or voice.get("provider"),
        global_prompt=system_msg,
        node_names=[],
        tools=tools,
        knowledge_base_ids=[],
        has_knowledge_base=False,
        references_kb_in_prompt=bool(_KB_REFERENCES.search(system_msg)),
        detected_specialty=_detect_specialty(system_msg + " " + (d.get("name") or "")),
        raw=d,
    )


def parse_agent(path: str | Path) -> AgentMeta:
    """Load an agent JSON and return a uniform AgentMeta. Auto-detects provider."""
    p = Path(path)
    d = json.loads(p.read_text())
    # Heuristic: Retell agents have conversationFlow / response_engine;
    # Vapi assistants have model / transcriber / voice nested objects.
    if "conversationFlow" in d or "response_engine" in d:
        return _parse_retell(d)
    if "model" in d and isinstance(d["model"], dict):
        return _parse_vapi(d)
    # Fall back to Retell parsing — most permissive.
    return _parse_retell(d)
