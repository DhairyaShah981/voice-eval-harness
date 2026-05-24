"""All Retell linter rules.

Each rule is a small ``Rule`` subclass. Rules are pure: no I/O, no LLM calls,
just structural checks on the parsed agent JSON. The full bank ports the
13 known-broken-in-production checks from the original
``validate_retell_agent.py`` and adds two new rules for issues seen across
the voice-service repo:

  RTL-014 — ngrok dev URLs baked into agent JSON
  RTL-015 — knowledge_base_ids empty but global prompt references "KB doc"

To add a new rule: subclass ``Rule``, set ``id``/``severity``/``title``,
implement ``check``, and append the instance to ``ALL_RULES`` at the bottom.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from voice_eval_harness.linters.base import Issue, Rule, Severity

ALLOWED_ANALYSIS_TYPES = {
    "system-presets", "custom", "string", "boolean", "integer", "number",
}
ALLOWED_LANGUAGE_PREFIXES = (
    "en", "es", "fr", "de", "it", "pt", "zh", "ja", "ko", "ar", "hi",
    "ru", "nl", "pl", "tr", "sv", "da", "no", "fi",
)
ALLOWED_LANGUAGES_EXACT = {"multi"}
ALLOWED_JSONSCHEMA_TYPES = {
    "string", "integer", "number", "boolean", "object", "array", "null",
}
REQUIRED_TOP_LEVEL = {
    "agent_name", "response_engine", "webhook_url", "language",
    "voice_id", "conversationFlow",
}
REQUIRED_CF_KEYS = {
    "conversation_flow_id", "nodes", "start_node_id",
    "tools", "model_choice", "is_transfer_cf",
}


# ── Top-level rules ──────────────────────────────────────────────────────────


class R001_TopLevelKeys(Rule):
    id = "RTL-001"
    severity = Severity.FATAL
    title = "Required top-level keys present"

    def check(self, agent: dict[str, Any]) -> list[Issue]:
        return [
            Issue(self.id, self.severity, f"$.{k}", "missing required top-level key",
                  fix_hint=f"Add `{k}` to the agent JSON.")
            for k in REQUIRED_TOP_LEVEL
            if k not in agent
        ]


class R002_ResponseEngine(Rule):
    id = "RTL-002"
    severity = Severity.FATAL
    title = "response_engine shape"

    def check(self, agent: dict[str, Any]) -> list[Issue]:
        issues: list[Issue] = []
        block = agent.get("response_engine")
        if block is None:
            return issues
        if not isinstance(block, dict):
            return [Issue(self.id, self.severity, "$.response_engine",
                          "must be an object")]
        if block.get("type") != "conversation-flow":
            issues.append(Issue(
                self.id, self.severity, "$.response_engine.type",
                f"must be 'conversation-flow', got {block.get('type')!r}",
            ))
        for k in ("version", "conversation_flow_id"):
            if k not in block:
                issues.append(Issue(self.id, self.severity,
                                    f"$.response_engine.{k}", "missing"))
        return issues


class R003_LanguageCode(Rule):
    id = "RTL-003"
    severity = Severity.WARNING
    title = "Recognized language code"

    def check(self, agent: dict[str, Any]) -> list[Issue]:
        lang = agent.get("language")
        if not isinstance(lang, str):
            return []
        if (
            lang in ALLOWED_LANGUAGES_EXACT
            or any(lang.startswith(p) for p in ALLOWED_LANGUAGE_PREFIXES)
        ):
            return []
        return [Issue(
            self.id, self.severity, "$.language",
            f"unrecognized language code: {lang!r}",
            fix_hint='Use a BCP-47 code (e.g. "en-US", "es-ES") or "multi".',
        )]


# ── conversationFlow rules ───────────────────────────────────────────────────


class R004_IsTransferCf(Rule):
    """The famous one: missing this field crashes Retell with
    'Cannot read properties of undefined (reading is_transfer_cf)'."""

    id = "RTL-004"
    severity = Severity.FATAL
    title = "conversationFlow.is_transfer_cf present"

    def check(self, agent: dict[str, Any]) -> list[Issue]:
        cf = agent.get("conversationFlow")
        if not isinstance(cf, dict):
            return []
        if "is_transfer_cf" in cf:
            return []
        return [Issue(
            self.id, self.severity, "$.conversationFlow.is_transfer_cf",
            "missing — Retell importer crashes with "
            "'Cannot read properties of undefined (reading is_transfer_cf)'",
            fix_hint="Add `\"is_transfer_cf\": false` to conversationFlow.",
        )]


class R005_CfRequiredKeys(Rule):
    id = "RTL-005"
    severity = Severity.FATAL
    title = "conversationFlow required keys"

    def check(self, agent: dict[str, Any]) -> list[Issue]:
        cf = agent.get("conversationFlow")
        if not isinstance(cf, dict):
            return [Issue(self.id, self.severity, "$.conversationFlow",
                          "must be an object")]
        return [
            Issue(self.id, self.severity, f"$.conversationFlow.{k}",
                  "missing required key")
            for k in REQUIRED_CF_KEYS
            if k not in cf and k != "is_transfer_cf"  # R004 owns that one
        ]


class R006_Nodes(Rule):
    id = "RTL-006"
    severity = Severity.FATAL
    title = "Nodes well-formed"

    def check(self, agent: dict[str, Any]) -> list[Issue]:
        cf = agent.get("conversationFlow") or {}
        nodes = cf.get("nodes")
        issues: list[Issue] = []
        if nodes is None:
            return issues
        if not isinstance(nodes, list):
            return [Issue(self.id, self.severity, "$.conversationFlow.nodes",
                          "must be a list")]
        if not nodes:
            issues.append(Issue(self.id, self.severity,
                                "$.conversationFlow.nodes",
                                "empty — agent has no nodes"))
        for i, n in enumerate(nodes):
            if not isinstance(n, dict):
                issues.append(Issue(self.id, self.severity,
                                    f"$.conversationFlow.nodes[{i}]",
                                    "must be an object"))
                continue
            nid = n.get("id")
            if not nid:
                issues.append(Issue(self.id, self.severity,
                                    f"$.conversationFlow.nodes[{i}]",
                                    "missing id"))
                continue
            if not n.get("type"):
                issues.append(Issue(self.id, self.severity, f"node[{nid}]",
                                    "missing type"))
            if n.get("type") == "function" and not n.get("tool_id"):
                issues.append(Issue(self.id, self.severity, f"node[{nid}]",
                                    "function node missing tool_id"))
        return issues


class R007_DuplicateNodeIds(Rule):
    id = "RTL-007"
    severity = Severity.FATAL
    title = "Node ids are unique"

    def check(self, agent: dict[str, Any]) -> list[Issue]:
        cf = agent.get("conversationFlow") or {}
        nodes = cf.get("nodes") or []
        ids = [n["id"] for n in nodes if isinstance(n, dict) and n.get("id")]
        dups = sorted(k for k, v in Counter(ids).items() if v > 1)
        if not dups:
            return []
        return [Issue(self.id, self.severity, "$.conversationFlow.nodes",
                      f"duplicate node ids: {dups}")]


class R008_StartNodeIdResolves(Rule):
    id = "RTL-008"
    severity = Severity.FATAL
    title = "start_node_id resolves to an existing node"

    def check(self, agent: dict[str, Any]) -> list[Issue]:
        cf = agent.get("conversationFlow") or {}
        start = cf.get("start_node_id")
        nodes = cf.get("nodes") or []
        ids = {n.get("id") for n in nodes if isinstance(n, dict)}
        if start and start not in ids:
            return [Issue(self.id, self.severity,
                          "$.conversationFlow.start_node_id",
                          f"{start!r} not present in nodes")]
        return []


class R009_Edges(Rule):
    id = "RTL-009"
    severity = Severity.FATAL
    title = "Edges resolve and edge ids are globally unique"

    def check(self, agent: dict[str, Any]) -> list[Issue]:
        cf = agent.get("conversationFlow") or {}
        nodes = cf.get("nodes") or []
        node_ids = {n.get("id") for n in nodes if isinstance(n, dict)}
        issues: list[Issue] = []
        edge_ids: list[str] = []
        for n in nodes:
            if not isinstance(n, dict):
                continue
            for e in n.get("edges", []) or []:
                if not isinstance(e, dict):
                    continue
                eid = e.get("id")
                if eid:
                    edge_ids.append(eid)
                dst = e.get("destination_node_id")
                if dst and dst not in node_ids:
                    issues.append(Issue(
                        self.id, self.severity,
                        f"node[{n.get('id')}].edge[{eid}]",
                        f"destination_node_id {dst!r} not in nodes",
                    ))
        dups = sorted(k for k, v in Counter(edge_ids).items() if v > 1)
        if dups:
            issues.append(Issue(
                self.id, self.severity, "$.conversationFlow.edges",
                f"duplicate edge ids across flow: {dups}",
            ))
        return issues


# ── Tool rules ───────────────────────────────────────────────────────────────


class R010_ToolBasics(Rule):
    id = "RTL-010"
    severity = Severity.FATAL
    title = "Tool basics: id, URL, required[]"

    def check(self, agent: dict[str, Any]) -> list[Issue]:
        cf = agent.get("conversationFlow") or {}
        tools = cf.get("tools") or []
        issues: list[Issue] = []
        for i, t in enumerate(tools):
            if not isinstance(t, dict):
                continue
            tid = t.get("tool_id")
            label = tid or i
            if not tid:
                issues.append(Issue(self.id, self.severity, f"tool[{i}]",
                                    "missing tool_id"))
            if t.get("type") == "custom":
                url = t.get("url", "")
                if not url:
                    issues.append(Issue(self.id, self.severity, f"tool[{label}]",
                                        "missing url for custom tool"))
                elif not url.startswith("https://") and \
                        not url.startswith("http://localhost"):
                    issues.append(Issue(self.id, Severity.WARNING,
                                        f"tool[{label}]",
                                        f"url not https: {url}"))
                params = t.get("parameters", {}) or {}
                req = params.get("required", None)
                if isinstance(req, list) and len(req) == 0:
                    issues.append(Issue(
                        self.id, self.severity,
                        f"tool[{label}].parameters.required",
                        "empty array — Retell 400s on import.",
                        fix_hint="Declare at least one required field.",
                    ))
        return issues


class R011_ToolParameters(Rule):
    id = "RTL-011"
    severity = Severity.FATAL
    title = "Tool parameter properties have type and description"

    def check(self, agent: dict[str, Any]) -> list[Issue]:
        cf = agent.get("conversationFlow") or {}
        tools = cf.get("tools") or []
        issues: list[Issue] = []
        for i, t in enumerate(tools):
            if not isinstance(t, dict) or t.get("type") != "custom":
                continue
            label = t.get("tool_id") or i
            params = t.get("parameters", {}) or {}
            props = params.get("properties")
            if not props:
                issues.append(Issue(self.id, self.severity,
                                    f"tool[{label}].parameters",
                                    "missing/empty properties"))
                continue
            for pname, pdef in props.items():
                base = f"tool[{label}].parameters.properties.{pname}"
                if not isinstance(pdef, dict):
                    issues.append(Issue(self.id, self.severity, base,
                                        "must be an object"))
                    continue
                if "type" not in pdef:
                    issues.append(Issue(self.id, self.severity, base,
                                        "missing 'type' field"))
                elif pdef["type"] not in ALLOWED_JSONSCHEMA_TYPES:
                    issues.append(Issue(
                        self.id, self.severity, base,
                        f"invalid JSONSchema type {pdef['type']!r}",
                    ))
                desc = pdef.get("description", "")
                if not isinstance(desc, str) or not desc.strip():
                    issues.append(Issue(
                        self.id, self.severity, base,
                        "missing or empty 'description' — "
                        "Retell 400s on import for params without descriptions.",
                    ))
        return issues


class R012_FunctionTool_idRef(Rule):
    id = "RTL-012"
    severity = Severity.FATAL
    title = "Function-node tool_id resolves to a defined tool"

    def check(self, agent: dict[str, Any]) -> list[Issue]:
        cf = agent.get("conversationFlow") or {}
        nodes = cf.get("nodes") or []
        tools = cf.get("tools") or []
        tool_ids = {t.get("tool_id") for t in tools if isinstance(t, dict)}
        issues: list[Issue] = []
        for n in nodes:
            if not isinstance(n, dict) or n.get("type") != "function":
                continue
            tid = n.get("tool_id")
            if tid and tid not in tool_ids:
                issues.append(Issue(
                    self.id, self.severity, f"node[{n.get('id')}]",
                    f"tool_id {tid!r} not in tools[] "
                    f"(have: {sorted(x for x in tool_ids if x)})",
                ))
        return issues


class R013_DuplicateToolIds(Rule):
    id = "RTL-013"
    severity = Severity.FATAL
    title = "Tool ids are unique"

    def check(self, agent: dict[str, Any]) -> list[Issue]:
        cf = agent.get("conversationFlow") or {}
        tools = cf.get("tools") or []
        ids = [t["tool_id"] for t in tools
               if isinstance(t, dict) and t.get("tool_id")]
        dups = sorted(k for k, v in Counter(ids).items() if v > 1)
        if not dups:
            return []
        return [Issue(self.id, self.severity, "$.conversationFlow.tools",
                      f"duplicate tool_ids: {dups}")]


# ── Post-call + webhook rules ────────────────────────────────────────────────


class R014_PostCallAnalysis(Rule):
    """Retell uses a oneOf schema for post_call_analysis_data entries:
    branch A (system-presets) requires no description; branch B (any other
    type) requires a non-empty description. Missing description on branch B
    breaks Eva v3 import."""

    id = "RTL-014"
    severity = Severity.FATAL
    title = "post_call_analysis_data shape"

    def check(self, agent: dict[str, Any]) -> list[Issue]:
        entries = agent.get("post_call_analysis_data") or []
        issues: list[Issue] = []
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            t = entry.get("type")
            if t not in ALLOWED_ANALYSIS_TYPES:
                issues.append(Issue(
                    self.id, self.severity,
                    f"$.post_call_analysis_data[{i}].type",
                    f"type {t!r} not in allowed set "
                    f"{sorted(ALLOWED_ANALYSIS_TYPES)}",
                ))
            if not entry.get("name"):
                issues.append(Issue(self.id, self.severity,
                                    f"$.post_call_analysis_data[{i}]",
                                    "missing name"))
            if t and t != "system-presets":
                desc = entry.get("description", "")
                if not isinstance(desc, str) or not desc.strip():
                    issues.append(Issue(
                        self.id, self.severity,
                        f"$.post_call_analysis_data[{i}].description",
                        f"missing/empty — Retell rejects non-system-presets "
                        f"entries without description "
                        f"(entry name={entry.get('name')!r}, type={t!r})",
                    ))
        return issues


class R015_WebhookUrl(Rule):
    id = "RTL-015"
    severity = Severity.FATAL
    title = "webhook_url is https and not a placeholder"

    def check(self, agent: dict[str, Any]) -> list[Issue]:
        wh = agent.get("webhook_url", "")
        if not isinstance(wh, str):
            return []
        issues: list[Issue] = []
        if wh and not (wh.startswith("https://")
                       or wh.startswith("http://localhost")):
            issues.append(Issue(self.id, Severity.WARNING, "$.webhook_url",
                                f"not https: {wh}"))
        if "REPLACE" in wh:
            issues.append(Issue(self.id, self.severity, "$.webhook_url",
                                "still contains placeholder REPLACE token"))
        return issues


# ── New rules unique to voice-eval-harness ──────────────────────────────────


_NGROK_HOSTS = re.compile(r"\b[a-z0-9-]+\.ngrok(?:-free)?\.(?:dev|app|io)\b", re.I)


class R016_NgrokUrl(Rule):
    """Catch ngrok dev tunnels baked into agent JSON (tool URLs, webhooks).
    These rot the moment the tunnel restarts."""

    id = "RTL-016"
    severity = Severity.WARNING
    title = "ngrok dev URLs detected"

    def check(self, agent: dict[str, Any]) -> list[Issue]:
        hits: list[Issue] = []
        wh = agent.get("webhook_url", "")
        if isinstance(wh, str) and _NGROK_HOSTS.search(wh):
            hits.append(Issue(self.id, self.severity, "$.webhook_url",
                              f"ngrok dev URL in webhook: {wh}",
                              fix_hint="Move tool/webhook URLs to a stable "
                                       "production host before shipping."))
        cf = agent.get("conversationFlow") or {}
        for i, t in enumerate(cf.get("tools") or []):
            if not isinstance(t, dict):
                continue
            url = t.get("url", "")
            if isinstance(url, str) and _NGROK_HOSTS.search(url):
                hits.append(Issue(
                    self.id, self.severity,
                    f"tool[{t.get('tool_id') or i}].url",
                    f"ngrok dev URL in tool: {url}",
                ))
        return hits


_KB_REFERENCES = re.compile(
    r"\b(?:knowledge\s+base|kb\s+doc|knowledge[-_]base)\b",
    re.I,
)


class R017_KbEmptyButReferenced(Rule):
    """If the global prompt mentions a knowledge base but
    ``knowledge_base_ids`` is empty, the agent will hallucinate. Caught the
    Cal Retina ``iris-en.json`` bug where prompts referenced "KB doc 02"
    but no KB was actually wired in."""

    id = "RTL-017"
    severity = Severity.FATAL
    title = "knowledge_base_ids empty but referenced in prompt"

    def check(self, agent: dict[str, Any]) -> list[Issue]:
        cf = agent.get("conversationFlow") or {}
        kb_ids = cf.get("knowledge_base_ids", None)
        # Also check the agent-level field that some Retell configs use.
        if kb_ids is None:
            kb_ids = agent.get("knowledge_base_ids")
        if kb_ids is None:
            return []
        if not isinstance(kb_ids, list) or len(kb_ids) > 0:
            return []
        text_blobs: list[str] = []
        gp = cf.get("global_prompt") or agent.get("global_prompt") or ""
        if isinstance(gp, str):
            text_blobs.append(gp)
        for n in cf.get("nodes") or []:
            if not isinstance(n, dict):
                continue
            instr = n.get("instruction") or {}
            if isinstance(instr, dict):
                txt = instr.get("text", "")
                if isinstance(txt, str):
                    text_blobs.append(txt)
        joined = "\n".join(text_blobs)
        if _KB_REFERENCES.search(joined):
            return [Issue(
                self.id, self.severity, "$.conversationFlow.knowledge_base_ids",
                "empty list but global_prompt / node instructions reference a knowledge base",
                fix_hint="Either wire `knowledge_base_ids` to a real Retell KB "
                         "or remove the KB references from the prompts.",
            )]
        return []


ALL_RULES: list[Rule] = [
    R001_TopLevelKeys(),
    R002_ResponseEngine(),
    R003_LanguageCode(),
    R004_IsTransferCf(),
    R005_CfRequiredKeys(),
    R006_Nodes(),
    R007_DuplicateNodeIds(),
    R008_StartNodeIdResolves(),
    R009_Edges(),
    R010_ToolBasics(),
    R011_ToolParameters(),
    R012_FunctionTool_idRef(),
    R013_DuplicateToolIds(),
    R014_PostCallAnalysis(),
    R015_WebhookUrl(),
    R016_NgrokUrl(),
    R017_KbEmptyButReferenced(),
]
