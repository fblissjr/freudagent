"""Context assembly and provider protocol for the experiment harness.

The data layer assembles context (rules, skills, sources) into prompts.
Providers are pluggable model interfaces for testing. Orchestration is
the harness's job -- FreudAgent provides the data, not the loop.

Architecture:
    - Context assembly: rules -> skill -> source -> task parameters
      (progressive disclosure hierarchy)
    - Providers: echo, anthropic, local, rlm (pluggable via Protocol)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

import orjson

from freud_schema.harness import compose_preset
from freud_schema.store import ExperimentStore


# ---------------------------------------------------------------------------
# Provider protocol and CompletionResult
# ---------------------------------------------------------------------------


@dataclass
class CompletionResult:
    """Structured response from a model provider."""

    content: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None
    metadata: dict | None = None


class Provider(Protocol):
    """Any object that can produce a completion from system + user messages."""

    def complete(self, system: str, user: str) -> CompletionResult: ...


# ---------------------------------------------------------------------------
# Source tag format (single source of truth for generation + parsing)
# ---------------------------------------------------------------------------

_SOURCE_TAG_RE = re.compile(
    r'<source\s+id="(\d+)"\s+type="([^"]*)"\s+path="([^"]*)"\s*/>'
)


def format_source_tag(source_id: int, media_type: str, path: str) -> str:
    """Render a source reference tag for inclusion in user messages."""
    return f'<source id="{source_id}" type="{media_type}" path="{path}" />'


def parse_source_tags(text: str) -> list[dict[str, str]]:
    """Parse source tags from a user message.

    Returns list of dicts with keys: id, media_type, path.
    """
    return [
        {"id": m.group(1), "media_type": m.group(2), "path": m.group(3)}
        for m in _SOURCE_TAG_RE.finditer(text)
    ]


def strip_source_tags(text: str) -> str:
    """Remove source tags from text, returning the remaining content."""
    return _SOURCE_TAG_RE.sub("", text).strip()


# ---------------------------------------------------------------------------
# Context assembly (progressive disclosure hierarchy)
# ---------------------------------------------------------------------------


def assemble_runner_context(
    store: ExperimentStore,
    *,
    skill_id: int,
    source_ids: list[int],
    domain: str | None = None,
    task_params: str = "",
    preset: str | None = None,
) -> tuple[str, str]:
    """Build system prompt and user message for a subagent run.

    Returns (system_prompt, user_message) following the progressive
    disclosure hierarchy: [preset archetypes ->] rules -> skill -> source -> task.

    When preset is provided, the archetype-composed system prompt is
    prepended to the system prompt, connecting identity to execution.
    """
    # Layer 0: Archetype identity (optional)
    archetype_block = ""
    if preset:
        archetype_block = compose_preset(preset) + "\n\n"

    # Layer 1: Rules (always first, always small)
    rules = store.get_rules(domain=domain)
    rules_block = ""
    if rules:
        rules_text = "\n".join(f"- {r.content}" for r in rules)
        rules_block = f"# Rules\n\n{rules_text}\n\n"

    # Layer 2: Skill (loaded by routing decision)
    skill = store.get_skill(skill_id)
    skill_block = ""
    if skill:
        skill_block = f"# Skill: {skill.domain} / {skill.task_type} (v{skill.version})\n\n{skill.content}\n\n"

    # Layer 3: Source references (bulk fetch)
    source_block = ""
    if source_ids:
        source_map = store.get_sources_by_ids(source_ids)
        for sid in source_ids:
            source = source_map.get(sid)
            if source:
                source_block += format_source_tag(
                    source.id, source.media_type, source.content_path
                ) + "\n"
        if source_block:
            source_block = f"# Sources\n\n{source_block}\n"

    system_prompt = (archetype_block + rules_block + skill_block).strip()
    user_message = (source_block + task_params).strip()

    return system_prompt, user_message


# ---------------------------------------------------------------------------
# Built-in provider implementations
# ---------------------------------------------------------------------------


class EchoProvider:
    """Returns the assembled context as output, for pipeline verification.

    Proves the pipeline works end-to-end without requiring API keys.
    The output shows exactly what a real model would receive.
    """

    def complete(self, system: str, user: str) -> CompletionResult:
        content = orjson.dumps({
            "model": "echo",
            "system_prompt": system,
            "user_message": user,
        }).decode()
        return CompletionResult(content=content, model="echo")


class ClaudeProvider:
    """Calls the Anthropic API via the official SDK."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        try:
            import anthropic  # type: ignore[import-untyped]
        except ImportError:
            raise ImportError(
                "Anthropic SDK not installed. Run: uv pip install anthropic"
            ) from None
        self._client = anthropic.Anthropic()
        self._model = model

    def complete(self, system: str, user: str) -> CompletionResult:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return CompletionResult(
            content=response.content[0].text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
        )

    def complete_chat(self, messages: list[dict]) -> CompletionResult:
        """Multi-turn completion for RLM and other iterative patterns."""
        system = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                chat_messages.append(msg)

        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system,
            messages=chat_messages,
        )
        return CompletionResult(
            content=response.content[0].text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
        )


class OpenAICompatProvider:
    """Calls any OpenAI-compatible endpoint (heylookitsanllm, llama.cpp, vLLM, Ollama).

    Uses httpx for HTTP calls. Sends standard /v1/chat/completions requests.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        model: str = "default",
    ):
        try:
            import httpx  # type: ignore[import-untyped]
        except ImportError:
            raise ImportError(
                "httpx not installed. Run: uv pip install httpx"
            ) from None
        self._client = httpx.Client(base_url=base_url, timeout=120.0)
        self._model = model

    def complete(self, system: str, user: str) -> CompletionResult:
        return self.complete_chat([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])

    def complete_chat(self, messages: list[dict]) -> CompletionResult:
        """Multi-turn completion for RLM and other iterative patterns."""
        response = self._client.post(
            "/v1/chat/completions",
            json={
                "model": self._model,
                "messages": messages,
                "stream": False,
            },
        )
        response.raise_for_status()
        data = response.json()

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

        return CompletionResult(
            content=content,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            model=data.get("model"),
        )


def get_provider(
    name: str,
    *,
    model_name: str | None = None,
    base_url: str | None = None,
    max_iterations: int = 10,
    sub_model: str | None = None,
) -> Provider:
    """Factory for provider instances.

    Args:
        name: "echo" for pipeline verification, "anthropic" for Claude API,
              "local" for any OpenAI-compatible endpoint, "rlm" for RLM
              wrapping local, "rlm-anthropic" for RLM wrapping Claude.
        model_name: Model name override (provider-specific default otherwise).
        base_url: Base URL for local provider (default: http://localhost:8080).
        max_iterations: Maximum REPL iterations for RLM providers.
        sub_model: Provider name for llm_query() sub-calls (RLM only).
    """
    if name == "echo":
        return EchoProvider()
    if name == "anthropic":
        return ClaudeProvider(model=model_name or "claude-sonnet-4-6")
    if name == "local":
        return OpenAICompatProvider(
            base_url=base_url or "http://localhost:8080",
            model=model_name or "default",
        )
    if name in ("rlm", "rlm-anthropic"):
        from freud_schema.rlm import RLMProvider

        if name == "rlm":
            inner = OpenAICompatProvider(
                base_url=base_url or "http://localhost:8080",
                model=model_name or "default",
            )
        else:
            inner = ClaudeProvider(model=model_name or "claude-sonnet-4-6")

        sub_provider = None
        if sub_model:
            # Sub-provider gets its own defaults -- don't forward model_name
            # from the outer provider (e.g., a Claude model name is wrong for
            # a local sub-provider).
            sub_provider = get_provider(sub_model, base_url=base_url)

        return RLMProvider(inner, sub_provider=sub_provider, max_iterations=max_iterations)
    raise ValueError(
        f"Unknown provider: {name!r}. "
        f"Use 'echo', 'anthropic', 'local', 'rlm', or 'rlm-anthropic'."
    )


