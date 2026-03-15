"""Thin orchestrator loop and subagent runner for the experiment harness.

The orchestrator decomposes tasks, the runner executes subtasks. Model calls
are pluggable via the Provider protocol: any object with a complete() method
that returns a CompletionResult. This lets the harness work with Claude,
OpenAI-compatible local servers (heylookitsanllm, llama.cpp, vLLM, Ollama),
or echo providers for testing.

Architecture:
    - Orchestrator context: task description + rules + skill/source metadata
      (small -- routing decisions, not work)
    - Runner context: rules -> skill -> source -> task parameters
      (progressive disclosure hierarchy)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

import orjson

from freud_schema.harness import compose_preset
from freud_schema.store import ExperimentStore
from freud_schema.tables import (
    AgentRole,
    Extraction,
    Session,
    SessionStatus,
    SourceStatus,
    Subtask,
    TaskPlan,
    ValidationStatus,
)


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
    cost_usd: float | None = None
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
# Runner: execute a single subtask
# ---------------------------------------------------------------------------


def run_subtask(
    store: ExperimentStore,
    subtask: Subtask,
    *,
    provider: Provider,
    parent_session_id: int | None = None,
    model_name: str = "unknown",
    prior_results: dict | None = None,
    preset: str | None = None,
) -> Extraction | None:
    """Execute a single subtask: assemble context, call model, store results.

    Returns the Extraction if the subtask produces one, None otherwise.
    """
    # Resolve skill
    skill = store.get_active_skill(
        domain=subtask.skill_domain,
        task_type=subtask.skill_task_type,
    )
    if skill is None:
        return None
    assert skill.id is not None  # always set after DB fetch

    # Create session record
    session = Session(
        task_description=f"{subtask.type}: {subtask.skill_domain}/{subtask.skill_task_type}",
        task_type=subtask.type,
        parent_session_id=parent_session_id,
        agent_role=AgentRole.SUBAGENT,
        skill_id=skill.id,
        context_loaded={
            "skill_id": skill.id,
            "source_ids": subtask.source_ids,
            "prior_results": prior_results is not None,
        },
        model_used=model_name,
        status=SessionStatus.RUNNING,
    )
    session_id = store.insert_session(session)

    # Assemble context -- Fix A: prior_results no longer gated on subtask.context
    task_params = ""
    if prior_results:
        task_params = f"Prior results: {prior_results}\n\n"
    task_params += f"Execute {subtask.type} task."

    system_prompt, user_message = assemble_runner_context(
        store,
        skill_id=skill.id,
        source_ids=subtask.source_ids,
        domain=subtask.skill_domain,
        task_params=task_params,
        preset=preset,
    )

    # Call model
    try:
        result = provider.complete(system_prompt, user_message)

        # Build token usage from CompletionResult
        token_usage = None
        if result.input_tokens is not None or result.output_tokens is not None:
            token_usage = {}
            if result.input_tokens is not None:
                token_usage["input_tokens"] = result.input_tokens
            if result.output_tokens is not None:
                token_usage["output_tokens"] = result.output_tokens

        # Prefer model name from response over caller's string
        actual_model = result.model or model_name
        store.con.execute(
            "UPDATE sessions SET model_used = ? WHERE id = ?",
            [actual_model, session_id],
        )

        session_result = {"raw": result.content}
        if result.metadata:
            session_result.update(result.metadata)

        store.complete_session(
            session_id,
            status=SessionStatus.COMPLETED,
            result=session_result,
            token_usage=token_usage,
        )
    except Exception as exc:
        store.complete_session(
            session_id, status=SessionStatus.FAILED, result={"error": str(exc)}
        )
        return None

    # Store extraction if we have source(s)
    extraction = None
    if subtask.source_ids:
        extraction = Extraction(
            source_id=subtask.source_ids[0],
            skill_id=skill.id,
            session_id=session_id,
            output={"raw": result.content},
            validation_status=ValidationStatus.PENDING,
        )
        ext_id = store.insert_extraction(extraction)
        # Fix C: re-fetch instead of mutating frozen-ish model
        extraction = store.get_extraction(ext_id)

    return extraction


# ---------------------------------------------------------------------------
# Orchestrator: decompose and coordinate
# ---------------------------------------------------------------------------


def run_task(
    store: ExperimentStore,
    plan: TaskPlan,
    *,
    provider: Provider,
    task_description: str = "",
    model_name: str = "unknown",
    preset: str | None = None,
) -> list[Extraction]:
    """Execute a task plan: process subtasks in dependency order.

    Subtasks with no dependencies run first. Subtasks with depends_on
    wait until their dependencies complete. Results from dependencies
    are passed as prior_results.

    Args:
        preset: When provided, archetype-composed system prompt is
            prepended to each subtask's context.
    """
    # Create orchestrator session
    orch_session = Session(
        task_description=task_description or "orchestrator",
        task_type="orchestration",
        agent_role=AgentRole.ORCHESTRATOR,
        model_used=model_name,
        context_loaded={
            "preset": preset,
            "subtask_count": len(plan.subtasks),
        },
        status=SessionStatus.RUNNING,
    )
    orch_session_id = store.insert_session(orch_session)

    # Fix B: wrap in try/except/finally so session always completes
    results: dict[int, Extraction | None] = {}
    extractions: list[Extraction] = []
    failed_count = 0

    try:
        for idx, subtask in enumerate(plan.subtasks):
            # Collect results from dependencies
            prior = {}
            for dep_idx in subtask.depends_on:
                dep_result = results.get(dep_idx)
                if dep_result:
                    prior[f"subtask_{dep_idx}"] = dep_result.output

            extraction = run_subtask(
                store,
                subtask,
                provider=provider,
                parent_session_id=orch_session_id,
                model_name=model_name,
                prior_results=prior if prior else None,
                preset=preset,
            )
            results[idx] = extraction
            if extraction:
                extractions.append(extraction)
            else:
                failed_count += 1
    except Exception:
        store.complete_session(
            orch_session_id,
            status=SessionStatus.FAILED,
            result={
                "error": "unexpected exception",
                "extraction_count": len(extractions),
                "extraction_ids": [e.id for e in extractions],
            },
        )
        raise
    else:
        # Determine final status
        if failed_count == len(plan.subtasks):
            final_status = SessionStatus.FAILED
        else:
            final_status = SessionStatus.COMPLETED

        store.complete_session(
            orch_session_id,
            status=final_status,
            result={
                "extraction_count": len(extractions),
                "extraction_ids": [e.id for e in extractions],
            },
        )

    return extractions


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
            sub_provider = get_provider(sub_model, model_name=model_name, base_url=base_url)

        return RLMProvider(inner, sub_provider=sub_provider, max_iterations=max_iterations)
    raise ValueError(
        f"Unknown provider: {name!r}. "
        f"Use 'echo', 'anthropic', 'local', 'rlm', or 'rlm-anthropic'."
    )


# ---------------------------------------------------------------------------
# Convenience: run without manual TaskPlan construction
# ---------------------------------------------------------------------------


def run_simple(
    store: ExperimentStore,
    *,
    domain: str,
    task_type: str,
    source_ids: list[int] | None = None,
    provider: Provider,
    model_name: str = "unknown",
    task_description: str = "",
    preset: str | None = None,
) -> list[Extraction]:
    """Run a skill against source(s) without manual TaskPlan creation.

    If source_ids is None, processes all active sources. Creates one
    Subtask per source, all independent (no dependencies).

    When preset is provided, archetype-composed system prompt is
    prepended to each subtask's context.
    """
    if source_ids is None:
        sources = store.list_sources(status=SourceStatus.ACTIVE)
        source_ids = [s.id for s in sources if s.id is not None]
    if not source_ids:
        return []

    subtasks = [
        Subtask(
            type=task_type,
            skill_domain=domain,
            skill_task_type=task_type,
            source_ids=[sid],
        )
        for sid in source_ids
    ]

    plan = TaskPlan(subtasks=subtasks)
    return run_task(
        store,
        plan,
        provider=provider,
        task_description=task_description or f"{domain}/{task_type}",
        model_name=model_name,
        preset=preset,
    )
