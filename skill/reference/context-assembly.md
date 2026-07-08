# Context Assembly: Progressive Disclosure Layers

Last updated: 2026-07-07

How `assemble_runner_context()` implements progressive disclosure.

## The Function

`assemble_runner_context()` in `orchestrator.py` is FreudAgent's core function. It builds
a (system_prompt, user_message) tuple from the data layer, following a strict hierarchy.

```python
def assemble_runner_context(
    store, *, skill_key, source_keys, domain=None, task_params="", preset=None
) -> tuple[str, str]:
```

`skill_key` and `source_keys` are sha256/32 hash keys (`keys.dimension_key()`), not
integers -- the v0.17.0 key migration renamed every id-shaped parameter and
column in the schema (the hash algorithm itself moved from MD5 to sha256/32 in
v0.23, same 32-char length, no further parameter/column changes).

## Layer Stack

### Layer 0: Archetype Identity (optional)

When a `preset` is specified, `compose_preset()` generates the archetype-composed
system prompt. This shapes the agent's behavioral stance (careful, exploratory,
iterative) before any task-specific content.

**Maps to**: L1 in the progressive disclosure hierarchy (always loaded when active).

### Layer 1: Rules

Global and domain-specific constraints, loaded from `dim_rule`. Priority-ordered.
These are always small (one-liners) and always present.

Example: "Output valid JSON", "Use ISO dates for insurance domain"

**Maps to**: L1 -- constraints that apply regardless of task.

### Layer 2: Skill

The actual instructions for the domain/task_type, loaded from `dim_skill`.
This is the medium-sized context that tells the agent what to do.

Example: "Extract policy number, effective date, and named insureds from insurance documents."

**Maps to**: L2 -- loaded by routing decision (which skill matches this task).

### Layer 3: Sources

References to the raw artifacts to process, rendered as source tags:
`<source id="a1b2c3..." type="application/pdf" path="/data/policy.pdf" />`

`id` is the source's sha256/32 hash key (`source_key`), not a sequence number --
`parse_source_tags()` accepts any non-empty id string, not just digits.

The RLM provider resolves these tags into actual file content. Other providers
receive the metadata for the harness to handle content loading.

**Maps to**: L3 -- loaded on demand (specific to this execution).

### Task Parameters

Additional context from the caller (task description, prior results).
Appended to the user message after source references.

## Output Structure

```
system_prompt = [archetype identity] + [rules] + [skill]
user_message  = [source references] + [task parameters]
```

The system prompt contains identity and instructions (who you are, what to do).
The user message contains the work (what to process, specific parameters).

## How This Maps to L1/L2/L3

| Progressive Disclosure Level | Context Assembly Layer | Content |
|-----|-----|-----|
| L1 (always loaded) | Layer 0 + Layer 1 | Archetypes + rules |
| L2 (loaded on match) | Layer 2 | Skill instructions |
| L3 (loaded on demand) | Layer 3 + params | Sources + task |

The harness controls WHEN to load L2 and L3. FreudAgent provides the HOW.
