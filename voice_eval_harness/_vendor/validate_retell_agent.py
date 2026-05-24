"""Validate a Retell conversation-flow agent JSON before importing to Retell.

Usage:
    python scripts/validate_retell_agent.py <path-to-agent.json> [--reference linda-scheduling.json]

Catches the structural issues that have actually broken our imports:

  1. ``conversationFlow`` block missing or missing ``is_transfer_cf``
     (the bug that broke Eva v1 — Retell tried to read ``is_transfer_cf``
     from undefined and 500'd with "Cannot read properties of undefined").
  2. Tool's ``parameters.required`` is an empty array — Retell rejects
     tools that declare no required fields with a 400 on import.
  3. ``tool_id`` in a function node doesn't match any tool in the
     ``tools`` array — Retell will accept the import but then fail to
     find the tool at call time.
  4. Edge ``destination_node_id`` points to a node id that doesn't exist.
  5. Duplicate node ids.
  6. start_node_id missing or doesn't resolve.
  7. ``post_call_analysis_data`` entry has a ``type`` not in the known
     allowed set ({"system-presets", "custom", "string", "boolean",
     "integer", "number"}).
  8. ``language`` value not in the known set (BCP-47 codes + "multi").
  9. tools[].url missing or not https.
  10. Top-level required keys missing relative to a known-good reference
      (defaults to Linda's scheduling JSON if present).
  11. A tool parameter property is missing ``description`` — Retell's
      importer 400s on params with just ``{"type": ...}``. Every leaf
      property must carry a non-empty description (broke Eva v3 import
      attempt 2).
  12. A tool parameter property is missing ``type`` or has an invalid
      JSONSchema type.
  13. Edge-id duplicated across the whole flow (Retell requires globally
      unique edge ids, not just per-node).

Exits 0 on success, 1 on any error, prints every problem found.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from typing import Any

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REFERENCE = os.path.normpath(
    os.path.join(
        THIS_DIR, "..", "clients", "redding_endoscopy", "voice-agent",
        "linda-scheduling.json",
    )
)

ALLOWED_ANALYSIS_TYPES = {
    "system-presets", "custom", "string", "boolean", "integer", "number"
}
ALLOWED_LANGUAGES_PREFIX = (
    "en", "es", "fr", "de", "it", "pt", "zh", "ja", "ko", "ar", "hi",
    "ru", "nl", "pl", "tr", "sv", "da", "no", "fi",
)
ALLOWED_LANGUAGES_EXACT = {"multi"}


def _err(out: list[str], path: str, msg: str) -> None:
    out.append(f"  ❌ {path}: {msg}")


def _warn(out: list[str], path: str, msg: str) -> None:
    out.append(f"  ⚠️  {path}: {msg}")


def validate(d: dict[str, Any], reference: dict[str, Any] | None = None) -> list[str]:
    errs: list[str] = []

    # ── 1. Top-level keys ──
    required_top = {
        "agent_name", "response_engine", "webhook_url", "language",
        "voice_id", "conversationFlow",
    }
    for k in required_top:
        if k not in d:
            _err(errs, f"$.{k}", "missing required top-level key")

    # ── 2. response_engine ──
    re_block = d.get("response_engine", {})
    if not isinstance(re_block, dict):
        _err(errs, "$.response_engine", "must be an object")
    else:
        if re_block.get("type") != "conversation-flow":
            _err(errs, "$.response_engine.type", f"must be 'conversation-flow', got {re_block.get('type')!r}")
        for k in ("version", "conversation_flow_id"):
            if k not in re_block:
                _err(errs, f"$.response_engine.{k}", "missing")

    # ── 3. Language ──
    lang = d.get("language")
    if isinstance(lang, str):
        if not (
            lang in ALLOWED_LANGUAGES_EXACT
            or any(lang.startswith(p) for p in ALLOWED_LANGUAGES_PREFIX)
        ):
            _warn(errs, "$.language", f"unrecognized language code: {lang!r}")

    # ── 4. conversationFlow ──
    cf = d.get("conversationFlow", {})
    if not isinstance(cf, dict):
        _err(errs, "$.conversationFlow", "must be an object")
        return errs

    # Critical: this is the field whose absence broke Eva v1 import.
    if "is_transfer_cf" not in cf:
        _err(errs, "$.conversationFlow.is_transfer_cf",
             "missing — Retell importer crashes with 'Cannot read properties of undefined (reading is_transfer_cf)'")

    required_cf_keys = {
        "conversation_flow_id", "nodes", "start_node_id",
        "tools", "model_choice", "is_transfer_cf",
    }
    for k in required_cf_keys:
        if k not in cf:
            _err(errs, f"$.conversationFlow.{k}", "missing required key")

    nodes = cf.get("nodes", []) or []
    tools = cf.get("tools", []) or []
    start_id = cf.get("start_node_id")

    # ── 5. Nodes ──
    if not nodes:
        _err(errs, "$.conversationFlow.nodes", "empty — agent has no nodes")
    node_ids: list[str] = []
    for i, n in enumerate(nodes):
        nid = n.get("id")
        if not nid:
            _err(errs, f"$.conversationFlow.nodes[{i}]", "missing id")
            continue
        node_ids.append(nid)
        if not n.get("type"):
            _err(errs, f"node[{nid}]", "missing type")
        if not n.get("instruction"):
            _warn(errs, f"node[{nid}]", "no instruction block")
        if n.get("type") == "function":
            tid = n.get("tool_id")
            if not tid:
                _err(errs, f"node[{nid}]", "function node missing tool_id")

    # Duplicate node ids
    dup = [k for k, v in Counter(node_ids).items() if v > 1]
    if dup:
        _err(errs, "$.conversationFlow.nodes", f"duplicate node ids: {dup}")

    # start_node_id resolves
    id_set = set(node_ids)
    if start_id and start_id not in id_set:
        _err(errs, "$.conversationFlow.start_node_id",
             f"{start_id!r} not present in nodes")

    # ── 6. Edges resolve + globally unique edge ids ──
    edge_id_list: list[str] = []
    for n in nodes:
        for e in n.get("edges", []) or []:
            eid = e.get("id")
            if eid:
                edge_id_list.append(eid)
            dst = e.get("destination_node_id")
            if dst and dst not in id_set:
                _err(errs, f"node[{n.get('id')}].edge[{eid}]",
                     f"destination_node_id {dst!r} not in nodes")
    dup_e = [k for k, v in Counter(edge_id_list).items() if v > 1]
    if dup_e:
        _err(errs, "$.conversationFlow.edges", f"duplicate edge ids across flow: {dup_e}")

    # ── 7. Tools ──
    tool_ids: list[str] = []
    for i, t in enumerate(tools):
        tid = t.get("tool_id")
        if not tid:
            _err(errs, f"tool[{i}]", "missing tool_id")
        else:
            tool_ids.append(tid)
        if t.get("type") == "custom":
            url = t.get("url", "")
            if not url:
                _err(errs, f"tool[{tid or i}]", "missing url for custom tool")
            elif not url.startswith("https://") and not url.startswith("http://localhost"):
                _warn(errs, f"tool[{tid or i}]", f"url not https: {url}")
            params = t.get("parameters", {}) or {}
            req = params.get("required", [])
            if isinstance(req, list) and len(req) == 0:
                _err(errs, f"tool[{tid or i}].parameters.required",
                     "empty array — Retell 400s on import. Declare at least one required field.")
            props = params.get("properties") or {}
            if not props:
                _err(errs, f"tool[{tid or i}].parameters", "missing/empty properties")
            else:
                allowed_jsonschema_types = {"string", "integer", "number", "boolean", "object", "array", "null"}
                for pname, pdef in props.items():
                    if not isinstance(pdef, dict):
                        _err(errs, f"tool[{tid or i}].parameters.properties.{pname}",
                             "must be an object")
                        continue
                    if "type" not in pdef:
                        _err(errs, f"tool[{tid or i}].parameters.properties.{pname}",
                             "missing 'type' field")
                    elif pdef["type"] not in allowed_jsonschema_types:
                        _err(errs, f"tool[{tid or i}].parameters.properties.{pname}",
                             f"invalid JSONSchema type {pdef['type']!r}")
                    if not pdef.get("description", "").strip():
                        _err(errs, f"tool[{tid or i}].parameters.properties.{pname}",
                             "missing or empty 'description' — Retell 400s on import for params without descriptions.")

    # Function-node tool_id refs match tools[]
    tool_id_set = set(tool_ids)
    for n in nodes:
        if n.get("type") == "function":
            tid = n.get("tool_id")
            if tid and tid not in tool_id_set:
                _err(errs, f"node[{n.get('id')}]",
                     f"tool_id {tid!r} not found in tools[] (have: {sorted(tool_id_set)})")

    # Duplicate tool_ids
    dup_t = [k for k, v in Counter(tool_ids).items() if v > 1]
    if dup_t:
        _err(errs, "$.conversationFlow.tools", f"duplicate tool_ids: {dup_t}")

    # ── 8. post_call_analysis_data — Retell uses a oneOf schema ──
    # Branch A: ``type: "system-presets"`` with a name from the preset set
    #           (call_summary / call_successful / user_sentiment / in_voicemail)
    #           — description NOT required.
    # Branch B: any other type (string / boolean / number / integer) — description
    #           REQUIRED, else Retell rejects with "must have required property
    #           'description'" + "must match exactly one schema in oneOf"
    #           (we hit this on Eva v3 attempt 3).
    for i, entry in enumerate(d.get("post_call_analysis_data", []) or []):
        t = entry.get("type")
        if t not in ALLOWED_ANALYSIS_TYPES:
            _err(errs, f"$.post_call_analysis_data[{i}].type",
                 f"type {t!r} not in allowed set {sorted(ALLOWED_ANALYSIS_TYPES)}")
        if not entry.get("name"):
            _err(errs, f"$.post_call_analysis_data[{i}]", "missing name")
        if t and t != "system-presets":
            desc = entry.get("description", "")
            if not isinstance(desc, str) or not desc.strip():
                _err(errs, f"$.post_call_analysis_data[{i}].description",
                     f"missing/empty — Retell rejects non-system-presets entries without description "
                     f"(entry name={entry.get('name')!r}, type={t!r})")

    # ── 9. Webhook URL ──
    wh = d.get("webhook_url", "")
    if wh and not (wh.startswith("https://") or wh.startswith("http://localhost")):
        _warn(errs, "$.webhook_url", f"not https: {wh}")
    if "REPLACE" in wh:
        _err(errs, "$.webhook_url", "still contains placeholder REPLACE token")

    # ── 10. Reference-shape diff (informational) ──
    if reference:
        for k in reference.keys():
            if k not in d:
                _warn(errs, f"$.{k}", "missing vs reference (Linda) — may be optional")

    return errs


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", help="Path to the Retell agent JSON.")
    p.add_argument(
        "--reference",
        default=DEFAULT_REFERENCE if os.path.exists(DEFAULT_REFERENCE) else None,
        help="Optional reference JSON (default: linda-scheduling.json).",
    )
    args = p.parse_args()

    try:
        d = json.load(open(args.path))
    except json.JSONDecodeError as e:
        print(f"❌ {args.path} is not valid JSON: {e}", file=sys.stderr)
        return 1

    ref = None
    if args.reference and os.path.exists(args.reference):
        try:
            ref = json.load(open(args.reference))
        except json.JSONDecodeError:
            ref = None

    errs = validate(d, ref)
    if not errs:
        print(f"✅ {args.path} — passes all Retell-import safety checks")
        return 0

    fatal = [e for e in errs if e.strip().startswith("❌")]
    warns = [e for e in errs if e.strip().startswith("⚠️")]
    print(f"\n{args.path}\n")
    if fatal:
        print(f"FATAL ({len(fatal)}):")
        for e in fatal:
            print(e)
        print()
    if warns:
        print(f"WARNINGS ({len(warns)}):")
        for e in warns:
            print(e)
        print()
    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
