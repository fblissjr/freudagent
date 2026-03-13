"""Thin orchestrator loop and subagent runner for the experiment harness.

The orchestrator decomposes tasks, the runner executes subtasks. Model calls
are pluggable: pass any callable that takes a prompt string and returns a
string. This lets the harness work with Claude, GPT, local models, or
mock functions for testing.

Architecture:
    - Orchestrator context: task description + rules + skill/source metadata
      (small -- routing decisions, not work)
    - Runner context: rules -> skill -> source -> task parameters
      (progressive disclosure hierarchy)
"""

from __future__ import annotations

from typing import Protocol

import orjson

from freud_schema.store import ExperimentStore
from freud_schema.tables import Extraction, Session, Subtask, TaskPlan


class ModelCall(Protocol):
    """Any callable that takes a prompt and returns a completion."""

    def __call__(self, system_prompt: str, user_message: str) -> str: ...


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
        from freud_schema.harness import compose_preset
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

    # Layer 3: Source references
    source_block = ""
    for sid in source_ids:
        source = store.get_source(sid)
        if source:
            source_block += (
                f"<source id=\"{source.id}\" type=\"{source.media_type}\" "
                f"path=\"{source.content_path}\" />\n"
            )
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
    model_fn: ModelCall,
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
        domain=subtask.skill_query.get("domain", ""),
        task_type=subtask.skill_query.get("task_type", ""),
    )
    if skill is None:
        return None

    # Create session record
    session = Session(
        task_description=f"{subtask.type}: {subtask.skill_query}",
        task_type=subtask.type,
        parent_session_id=parent_session_id,
        agent_role="subagent",
        skill_id=skill.id,
        context_loaded={
            "skill_id": skill.id,
            "source_ids": subtask.source_ids,
            "prior_results": prior_results is not None,
        },
        model_used=model_name,
        status="running",
    )
    session_id = store.insert_session(session)

    # Assemble context
    task_params = ""
    if subtask.context and prior_results:
        task_params = f"Prior results: {prior_results}\n\n"
    task_params += f"Execute {subtask.type} task."

    system_prompt, user_message = assemble_runner_context(
        store,
        skill_id=skill.id,
        source_ids=subtask.source_ids,
        domain=subtask.skill_query.get("domain"),
        task_params=task_params,
        preset=preset,
    )

    # Call model
    try:
        raw_output = model_fn(system_prompt, user_message)
        store.complete_session(session_id, status="completed", result={"raw": raw_output})
    except Exception as exc:
        store.complete_session(session_id, status="failed", result={"error": str(exc)})
        return None

    # Store extraction if we have source(s)
    extraction = None
    if subtask.source_ids:
        extraction = Extraction(
            source_id=subtask.source_ids[0],
            skill_id=skill.id,
            session_id=session_id,
            output={"raw": raw_output},
            validation_status="pending",
        )
        ext_id = store.insert_extraction(extraction)
        extraction.id = ext_id

    return extraction


# ---------------------------------------------------------------------------
# Orchestrator: decompose and coordinate
# ---------------------------------------------------------------------------


def run_task(
    store: ExperimentStore,
    plan: TaskPlan,
    *,
    model_fn: ModelCall,
    task_description: str = "",
    model_name: str = "unknown",
    orchestrator_preset: str = "hierarchical-orchestrator",
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
        agent_role="orchestrator",
        model_used=model_name,
        context_loaded={
            "preset": orchestrator_preset,
            "subtask_count": len(plan.subtasks),
        },
        status="running",
    )
    orch_session_id = store.insert_session(orch_session)

    # Process subtasks in dependency order
    results: dict[int, Extraction | None] = {}
    extractions: list[Extraction] = []

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
            model_fn=model_fn,
            parent_session_id=orch_session_id,
            model_name=model_name,
            prior_results=prior if prior else None,
            preset=preset,
        )
        results[idx] = extraction
        if extraction:
            extractions.append(extraction)

    # Complete orchestrator session
    store.complete_session(
        orch_session_id,
        status="completed",
        result={
            "extraction_count": len(extractions),
            "extraction_ids": [e.id for e in extractions],
        },
    )

    return extractions


# ---------------------------------------------------------------------------
# Built-in model implementations
# ---------------------------------------------------------------------------


class EchoModel:
    """Returns the assembled context as output, for pipeline verification.

    Proves the pipeline works end-to-end without requiring API keys.
    The output shows exactly what a real model would receive.
    """

    def __call__(self, system_prompt: str, user_message: str) -> str:
        return orjson.dumps({
            "model": "echo",
            "system_prompt": system_prompt,
            "user_message": user_message,
        }).decode()


def get_model(name: str, *, model_name: str | None = None) -> ModelCall:
    """Factory for model callables.

    Args:
        name: "echo" for pipeline verification, "anthropic" for Claude API.
        model_name: Anthropic model name (default: claude-sonnet-4-6).
    """
    if name == "echo":
        return EchoModel()
    if name == "anthropic":
        try:
            import anthropic  # type: ignore[import-untyped]
        except ImportError:
            raise ImportError(
                "Anthropic SDK not installed. Run: uv pip install anthropic"
            ) from None
        client = anthropic.Anthropic()
        actual_model = model_name or "claude-sonnet-4-6"

        def _call_anthropic(system_prompt: str, user_message: str) -> str:
            response = client.messages.create(
                model=actual_model,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text

        return _call_anthropic
    raise ValueError(f"Unknown model: {name!r}. Use 'echo' or 'anthropic'.")


# ---------------------------------------------------------------------------
# Convenience: run without manual TaskPlan construction
# ---------------------------------------------------------------------------


def run_simple(
    store: ExperimentStore,
    *,
    domain: str,
    task_type: str,
    source_ids: list[int] | None = None,
    model_fn: ModelCall,
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
        sources = store.list_sources(status="active")
        source_ids = [s.id for s in sources if s.id is not None]
    if not source_ids:
        return []

    subtasks = [
        Subtask(
            type=task_type,
            skill_query={"domain": domain, "task_type": task_type},
            source_ids=[sid],
        )
        for sid in source_ids
    ]

    plan = TaskPlan(subtasks=subtasks)
    return run_task(
        store,
        plan,
        model_fn=model_fn,
        task_description=task_description or f"{domain}/{task_type}",
        model_name=model_name,
        preset=preset,
    )
