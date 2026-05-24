"""LLM client abstraction for transcript analysis.

Three backends, listed in order of HIPAA suitability:

  1. ``vertex``    — Anthropic Claude on GCP Vertex AI. **BAA-covered**
                     when the user has a signed BAA with Google Cloud.
                     Requires ``anthropic[vertex]`` (the ``[vertex]`` extra)
                     and ``gcloud auth application-default login``.
                     Recommended for any real patient PHI.
  2. ``anthropic`` — direct Anthropic API. Anthropic offers a BAA on
                     enterprise plans; check your contract before using
                     with real PHI. Requires ``anthropic``.
  3. ``openai``    — gpt-4o-mini. **NOT HIPAA-compliant by default**.
                     Use only on PHI-scrubbed corpora or synthetic data.
                     Requires ``openai``.

Backend selected via ``VOXEVAL_ANALYZE_BACKEND`` env var, or per-call
through the ``backend`` arg. Failure to load the chosen SDK raises with
a clear remediation message.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class AnalyzeResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class AnalyzeClient(ABC):
    backend_name: str = "?"

    @abstractmethod
    def generate(self, *, system: str, user: str,
                 max_tokens: int = 4096) -> AnalyzeResponse: ...

    def generate_json(self, *, system: str, user: str,
                      max_tokens: int = 4096) -> dict:
        """Generate + parse a JSON response. Falls back to bracket-extraction
        if the model wraps the JSON in prose."""
        resp = self.generate(system=system, user=user, max_tokens=max_tokens)
        raw = resp.text.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if 0 <= start < end:
                return json.loads(raw[start:end + 1])
            raise


# ── Vertex Claude backend (BAA-covered) ────────────────────────────────────

# Vertex Claude pricing (per million tokens, Haiku 4.5 snapshot).
# Cost estimation only — billing of record is the GCP invoice.
_VERTEX_PRICE_IN_PER_MTOK = 1.0
_VERTEX_PRICE_OUT_PER_MTOK = 5.0


class VertexClaudeClient(AnalyzeClient):
    backend_name = "vertex"

    def __init__(
        self, *, project_id: str, location: str = "us-east5",
        model: str = "claude-haiku-4-5@20251001",
    ) -> None:
        # Defaults match the trifetch-os backend (claude_client.py): haiku
        # snapshot for fast analysis tasks, region us-east5 where Anthropic
        # publisher models are enabled by default on most BAA accounts.
        try:
            from anthropic import AnthropicVertex  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "Vertex Claude backend requires the [vertex] extra. Install:\n"
                "  pip install 'voice-eval-harness[vertex]'\n"
                "Then authenticate with:\n"
                "  gcloud auth application-default login"
            ) from e
        self._client = AnthropicVertex(region=location, project_id=project_id)
        self._model = model

    def generate(self, *, system: str, user: str,
                 max_tokens: int = 4096) -> AnalyzeResponse:
        msg = self._client.messages.create(
            model=self._model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(
            block.text for block in msg.content
            if getattr(block, "type", "") == "text"
        )
        usage = getattr(msg, "usage", None)
        in_tok = getattr(usage, "input_tokens", 0) if usage else 0
        out_tok = getattr(usage, "output_tokens", 0) if usage else 0
        cost = (in_tok * _VERTEX_PRICE_IN_PER_MTOK +
                out_tok * _VERTEX_PRICE_OUT_PER_MTOK) / 1_000_000
        return AnalyzeResponse(text=text, input_tokens=in_tok,
                                output_tokens=out_tok, cost_usd=cost)


# ── Anthropic direct backend ───────────────────────────────────────────────


class AnthropicDirectClient(AnalyzeClient):
    backend_name = "anthropic"

    def __init__(
        self, *, api_key: str | None = None,
        model: str = "claude-opus-4-7",
    ) -> None:
        try:
            from anthropic import Anthropic  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "Anthropic backend requires the anthropic SDK. Install:\n"
                "  pip install anthropic"
            ) from e
        self._client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self._model = model

    def generate(self, *, system: str, user: str,
                 max_tokens: int = 4096) -> AnalyzeResponse:
        msg = self._client.messages.create(
            model=self._model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(
            block.text for block in msg.content
            if getattr(block, "type", "") == "text"
        )
        usage = getattr(msg, "usage", None)
        in_tok = getattr(usage, "input_tokens", 0) if usage else 0
        out_tok = getattr(usage, "output_tokens", 0) if usage else 0
        cost = (in_tok * _VERTEX_PRICE_IN_PER_MTOK +
                out_tok * _VERTEX_PRICE_OUT_PER_MTOK) / 1_000_000
        return AnalyzeResponse(text=text, input_tokens=in_tok,
                                output_tokens=out_tok, cost_usd=cost)


# ── OpenAI fallback (NOT BAA) ──────────────────────────────────────────────


class OpenAIAnalyzeClient(AnalyzeClient):
    backend_name = "openai"

    def __init__(
        self, *, api_key: str | None = None,
        model: str = "gpt-4o-2024-08-06",
    ) -> None:
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "OpenAI backend requires `pip install openai`."
            ) from e
        self._client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
        self._model = model

    def generate(self, *, system: str, user: str,
                 max_tokens: int = 4096) -> AnalyzeResponse:
        resp = self._client.chat.completions.create(
            model=self._model, temperature=0,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        in_tok = getattr(usage, "prompt_tokens", 0) if usage else 0
        out_tok = getattr(usage, "completion_tokens", 0) if usage else 0
        # gpt-4o pricing (Aug 2026 snapshot)
        cost = (in_tok * 2.5 + out_tok * 10.0) / 1_000_000
        return AnalyzeResponse(text=text, input_tokens=in_tok,
                                output_tokens=out_tok, cost_usd=cost)


# ── Factory ────────────────────────────────────────────────────────────────


def get_analyze_client(
    backend: str | None = None,
    *,
    vertex_project: str | None = None,
    vertex_location: str = "us-east5",
    vertex_model: str = "claude-haiku-4-5@20251001",
    anthropic_model: str = "claude-opus-4-7",
    openai_model: str = "gpt-4o-2024-08-06",
) -> AnalyzeClient:
    """Build a client for the requested backend.

    Backend resolution order:
      1. explicit ``backend`` argument
      2. ``VOXEVAL_ANALYZE_BACKEND`` env var
      3. auto: vertex if VOXEVAL_VERTEX_PROJECT set, else anthropic if
         ANTHROPIC_API_KEY set, else openai.

    PHI safety: if ``VOXEVAL_REQUIRE_BAA=1`` is set in the env, ANY backend
    other than ``vertex`` raises immediately rather than risk sending
    BAA-covered PHI to an OpenAI / Anthropic-direct endpoint.
    """
    backend = (backend
               or os.environ.get("VOXEVAL_ANALYZE_BACKEND")
               or _auto_pick())

    if os.environ.get("VOXEVAL_REQUIRE_BAA") == "1" and backend != "vertex":
        raise RuntimeError(
            f"VOXEVAL_REQUIRE_BAA=1 in env; backend={backend!r} is NOT "
            f"covered by your GCP BAA. Switch to --backend vertex (or unset "
            f"VOXEVAL_REQUIRE_BAA to allow non-BAA backends)."
        )

    if backend == "vertex":
        project = vertex_project or os.environ.get("VOXEVAL_VERTEX_PROJECT")
        if not project:
            raise RuntimeError(
                "Vertex backend requires --vertex-project or "
                "VOXEVAL_VERTEX_PROJECT env var."
            )
        return VertexClaudeClient(
            project_id=project, location=vertex_location, model=vertex_model,
        )
    if backend == "anthropic":
        return AnthropicDirectClient(model=anthropic_model)
    if backend == "openai":
        return OpenAIAnalyzeClient(model=openai_model)
    raise ValueError(
        f"unknown backend {backend!r}; "
        f"choose from: vertex, anthropic, openai"
    )


def _auto_pick() -> str:
    if os.environ.get("VOXEVAL_VERTEX_PROJECT"):
        return "vertex"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "openai"
