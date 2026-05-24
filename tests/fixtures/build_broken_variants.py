"""Generate a set of synthetic 'broken' Retell agent JSONs from the clean
fixture, where each variant violates exactly one rule. Used by the parity
test to verify both linters (ours + the vendored legacy validator) flag
the same files.

Run directly to regenerate the fixtures::

    python tests/fixtures/build_broken_variants.py
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
CLEAN = HERE / "agents" / "clean_minimal.json"
OUT = HERE / "agents"


def _drop_is_transfer_cf(a: dict[str, Any]) -> None:
    a["conversationFlow"].pop("is_transfer_cf", None)


def _empty_required(a: dict[str, Any]) -> None:
    a["conversationFlow"]["tools"][0]["parameters"]["required"] = []


def _dangling_tool_id(a: dict[str, Any]) -> None:
    for n in a["conversationFlow"]["nodes"]:
        if n.get("type") == "function":
            n["tool_id"] = "tool-does-not-exist"


def _dangling_edge_destination(a: dict[str, Any]) -> None:
    a["conversationFlow"]["nodes"][0]["edges"][0]["destination_node_id"] = "node_ghost"


def _duplicate_node_ids(a: dict[str, Any]) -> None:
    extra = copy.deepcopy(a["conversationFlow"]["nodes"][0])
    a["conversationFlow"]["nodes"].append(extra)


def _bad_start_node(a: dict[str, Any]) -> None:
    a["conversationFlow"]["start_node_id"] = "node_does_not_exist"


def _bad_post_call_type(a: dict[str, Any]) -> None:
    a["post_call_analysis_data"][1]["type"] = "datetime"  # not in allowed set


def _bad_language_code(a: dict[str, Any]) -> None:
    a["language"] = "xx-YY"


def _http_tool_url(a: dict[str, Any]) -> None:
    a["conversationFlow"]["tools"][0]["url"] = "http://api.example.com/check"


def _missing_param_description(a: dict[str, Any]) -> None:
    a["conversationFlow"]["tools"][0]["parameters"]["properties"]["day_of_week"]\
        .pop("description")


def _missing_param_type(a: dict[str, Any]) -> None:
    a["conversationFlow"]["tools"][0]["parameters"]["properties"]["day_of_week"]\
        .pop("type")


def _duplicate_edge_ids(a: dict[str, Any]) -> None:
    # Add a second node with an edge that reuses the same id.
    nodes = a["conversationFlow"]["nodes"]
    nodes.append({
        "id": "node_extra",
        "name": "Extra",
        "type": "conversation",
        "instruction": {"type": "prompt", "text": "x"},
        "edges": [{
            "id": "edge_welcome_to_book",  # duplicate id
            "condition": "always",
            "transition_condition": {"type": "prompt", "prompt": "x"},
            "destination_node_id": "node_book",
        }],
    })


def _webhook_placeholder(a: dict[str, Any]) -> None:
    a["webhook_url"] = "https://example.com/REPLACE"


def _ngrok_tool_url(a: dict[str, Any]) -> None:
    a["conversationFlow"]["tools"][0]["url"] = (
        "https://farreachingly-unrescissory-irena.ngrok-free.dev/api/v1/check"
    )


def _kb_empty_but_referenced(a: dict[str, Any]) -> None:
    a["conversationFlow"]["knowledge_base_ids"] = []
    a["conversationFlow"]["global_prompt"] = (
        "You are a scheduler. Use KB doc 02 to look up insurance acceptance."
    )


def _missing_top_level(a: dict[str, Any]) -> None:
    a.pop("voice_id")


# Each entry: filename -> (mutator, expected_rule_id_to_fire)
VARIANTS: dict[str, tuple[Callable[[dict[str, Any]], None], str]] = {
    "broken_missing_top_level.json":      (_missing_top_level,         "RTL-001"),
    "broken_bad_language.json":           (_bad_language_code,         "RTL-003"),
    "broken_no_is_transfer_cf.json":      (_drop_is_transfer_cf,       "RTL-004"),
    "broken_duplicate_node_ids.json":     (_duplicate_node_ids,        "RTL-007"),
    "broken_bad_start_node.json":         (_bad_start_node,            "RTL-008"),
    "broken_dangling_edge.json":          (_dangling_edge_destination, "RTL-009"),
    "broken_dup_edge_ids.json":           (_duplicate_edge_ids,        "RTL-009"),
    "broken_empty_required.json":         (_empty_required,            "RTL-010"),
    "broken_http_tool_url.json":          (_http_tool_url,             "RTL-010"),
    "broken_missing_param_desc.json":     (_missing_param_description, "RTL-011"),
    "broken_missing_param_type.json":     (_missing_param_type,        "RTL-011"),
    "broken_dangling_tool_id.json":       (_dangling_tool_id,          "RTL-012"),
    "broken_bad_post_call_type.json":     (_bad_post_call_type,        "RTL-014"),
    "broken_webhook_placeholder.json":    (_webhook_placeholder,       "RTL-015"),
    "broken_ngrok_tool_url.json":         (_ngrok_tool_url,            "RTL-016"),
    "broken_kb_empty_referenced.json":    (_kb_empty_but_referenced,   "RTL-017"),
}


def generate(force: bool = True) -> None:
    base = json.loads(CLEAN.read_text())
    for name, (mutator, _rule_id) in VARIANTS.items():
        out_path = OUT / name
        if out_path.exists() and not force:
            continue
        variant = copy.deepcopy(base)
        mutator(variant)
        out_path.write_text(json.dumps(variant, indent=2) + "\n")


if __name__ == "__main__":
    generate(force=True)
    for name in VARIANTS:
        print(f"wrote {name}")
