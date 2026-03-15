# Tutorial: Using the RLM provider for large-context extraction

This walks through the RLM (Recursive Language Model) provider, which wraps
any model with a Python REPL loop. Instead of passing the entire source to the
model in one shot, the model writes code to explore, slice, and transform the
input iteratively. This is useful when sources are too large for a single
context window, or when the extraction task benefits from programmatic probing.

Building on the arxiv extraction tutorial -- same database, same skills, same
rules. The difference is in how the model processes the source.

## What you'll learn

- How RLM turns extraction into an iterative code-writing loop
- Why source content loading matters and how it works
- How `llm_query()` enables recursive sub-calls
- How archetype presets map to RLM behaviors
- How to compare RLM vs single-shot extraction using session data

---

## 0. Prerequisites

Complete the [arxiv extraction tutorial](tutorial-arxiv-extraction.md) through
at least step 5 (echo run). You need the database initialized with rules,
a skill, and a source.

For RLM to be useful, you also need a real model. Pick one:

```bash
# Option A: Local MLX server (heylookitsanllm or mlx_lm.server)
uv sync --extra local

# Option B: Claude API
uv sync --extra anthropic
```

If using a local server, start it in another terminal:

```bash
# From ~/workspace/heylookitsanllm or equivalent
python -m mlx_lm.server --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit
```

## 1. Understand what RLM does differently

In a single-shot provider (`local`, `anthropic`), the pipeline calls
`provider.complete(system_prompt, user_message)` once. The model gets the full
context and returns one response.

In the RLM provider, the pipeline still calls `provider.complete(system, user)`
-- the interface is identical. But inside, RLMProvider does this:

1. Loads source content into a `context` variable (the user message becomes data)
2. Tells the model about the REPL environment (`context`, `llm_query()`, `FINAL()`)
3. Appends the FreudAgent system prompt (archetypes, rules, skill) as task instructions
4. Enters a loop: the model writes code in ` ```repl ` blocks, code runs in
   a persistent namespace, output is fed back as the next conversation turn
5. The model calls `FINAL("answer")` or `FINAL_VAR("variable")` to terminate
6. RLMProvider returns the final answer as a normal `CompletionResult`

The orchestrator, skill, rules, and session tracking are unaware this happened.
To them, it's just a provider that took longer to respond.

## 2. Source content loading

The existing arxiv tutorial pointed out that the harness passes source
*metadata* (path, MIME type) but not content. The RLM provider closes this gap.

When RLMProvider receives a user message containing source tags like:

```xml
<source id="1" type="application/pdf" path="data/papers/attention-is-all-you-need.pdf" />
```

It parses the tags and attempts to load the file content:

- `text/*` and `application/json` -- read directly
- `application/pdf` -- attempts `pdftotext` (install `poppler-utils` if needed)
- Other types -- includes a metadata placeholder

The loaded content becomes the `context` variable in the REPL namespace. The
model never sees the raw XML tag -- it sees the actual file content.

For the PDF case, install poppler if you haven't:

```bash
# macOS
brew install poppler

# Linux
apt-get install poppler-utils
```

If pdftotext isn't available, the model gets a placeholder message and can
still work with whatever metadata is in the user message.

## 3. Run with echo (verify RLM context assembly)

```bash
uv run freud-schema run --domain arxiv --task-type extraction --model rlm
```

This will fail to connect (no local server for echo to reach), but it
illustrates that `--model rlm` is accepted. For actual echo verification of
the RLM wrapper's behavior, the existing `--model echo` pipeline shows what
context the RLM provider would receive.

To see the full context the RLM model gets (system prompt + REPL instructions
+ archetype/rules/skill), run with echo first:

```bash
uv run freud-schema run --domain arxiv --task-type extraction --model echo
```

The system prompt in the echo output is what gets prepended with RLM REPL
instructions when you switch to `--model rlm`.

## 4. Run with RLM (local model)

```bash
uv run freud-schema run --domain arxiv --task-type extraction \
  --model rlm \
  --model-name "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit" \
  --endpoint http://localhost:8080 \
  --max-iterations 10
```

What happens inside:

1. The orchestrator assembles context as usual (rules + skill + source tag)
2. RLMProvider intercepts the `complete()` call
3. Source content is loaded from disk into the `context` variable
4. The model receives the RLM system prompt + the FreudAgent system prompt
5. The model writes code to explore the context (e.g., `print(len(context))`)
6. Code output is fed back, the model writes more code
7. After several iterations, the model calls `FINAL(json_output)`
8. The final answer flows back through the normal extraction pipeline

**`--max-iterations`** caps the REPL loop. Default is 10. If the model hasn't
called `FINAL()` by then, the last response text becomes the answer. Start
with 10 and adjust based on how many iterations your model typically needs.

## 5. Run with RLM (Claude API)

```bash
uv run freud-schema run --domain arxiv --task-type extraction \
  --model rlm-anthropic \
  --max-iterations 8
```

Same mechanics, different inner provider. `rlm-anthropic` wraps `ClaudeProvider`
instead of `OpenAICompatProvider`.

## 6. Use a sub-model for llm_query()

The `llm_query()` function in the REPL namespace lets the model make recursive
sub-calls. By default, these go to the same inner provider. But you can use a
different (cheaper, faster) model for sub-calls:

```bash
uv run freud-schema run --domain arxiv --task-type extraction \
  --model rlm-anthropic \
  --sub-model local \
  --endpoint http://localhost:8080 \
  --max-iterations 10
```

This uses Claude for the main REPL loop but a local model for `llm_query()`
sub-calls. Useful when the main model needs to be smart (choosing what code to
write) but sub-calls are simpler tasks (summarizing a paragraph, answering a
factual question about a text slice).

## 7. Add the recursive-decomposer preset

The `recursive-decomposer` preset maps RLM behaviors to Freudian archetypes:

| RLM Behavior | Archetype | Why |
|---|---|---|
| Iterative context probing | `free-association` | Open-ended exploration before convergence |
| Condensing large inputs | `dream-work` | Condensation, displacement, secondary revision |
| Context budget management | `fixation` | Deliberate attention allocation |
| Knowing when to stop | `pleasure-principle` | Recognizing completion |

```bash
uv run freud-schema run --domain arxiv --task-type extraction \
  --model rlm \
  --endpoint http://localhost:8080 \
  --preset recursive-decomposer \
  --max-iterations 10
```

The preset's archetype fragments are appended to the RLM system prompt as
"Task Instructions". The model gets both "how to use the REPL" and "what
behavior to exhibit." This is the thesis test: does composing these archetypes
measurably change iteration count, sub-call efficiency, and extraction quality?

## 8. Inspect RLM session metadata

After an RLM run, the session result contains extra metadata:

```bash
uv run freud-schema session list
```

Look at the subagent session. Its `result` JSON includes:

```json
{
  "raw": "the extraction output",
  "rlm": {
    "iterations": 5,
    "sub_queries": 2,
    "trace": [
      {"iteration": 1, "code_len": 45, "stdout_len": 231, "stderr_len": 0},
      {"iteration": 2, "code_len": 89, "stdout_len": 412, "stderr_len": 0},
      {"iteration": 3, "code_len": 67, "stdout_len": 0, "stderr_len": 42},
      {"iteration": 4, "code_len": 112, "stdout_len": 890, "stderr_len": 0},
      {"iteration": 5, "code_len": 34, "stdout_len": 0, "stderr_len": 0, "action": "FINAL"}
    ]
  }
}
```

This tells you:
- How many iterations the model needed
- How many `llm_query()` sub-calls it made
- Per-iteration: how much code it wrote, how much output it produced, whether
  there were errors
- What terminated the loop (FINAL, direct_response, max_iterations)

Use the DuckDB MCP tools to query across sessions:

```sql
-- Compare iteration counts across presets
SELECT
    s.context_loaded->>'$.preset' AS preset,
    s.result->>'$.rlm.iterations' AS iterations,
    s.result->>'$.rlm.sub_queries' AS sub_queries
FROM sessions s
WHERE s.result->>'$.rlm' IS NOT NULL
ORDER BY s.created_at DESC;
```

## 9. Sandboxing

RLM code execution is sandboxed by default:

- **Restricted builtins**: `open`, `__import__`, `exec`, `eval`, `compile` are
  removed. The model can use `print`, `len`, `sorted`, `range`, and other safe
  builtins.
- **Timeout**: Each code execution has a 30-second timeout (configurable).
- **Output truncation**: stdout/stderr are capped at 10KB per iteration.
- **No filesystem access**: The model can only operate on the `context` variable
  and `llm_query()` function injected into its namespace.

The sandbox is not a security boundary (no process isolation). It prevents
accidental damage during experimentation. If you need to run trusted code with
full Python access, pass `sandbox=False` when constructing the provider
programmatically.

## 10. Compare single-shot vs RLM

The real test: run the same skill, rules, and source with different providers
and compare results.

```bash
# Single-shot (baseline)
uv run freud-schema run --domain arxiv --task-type extraction --model anthropic

# RLM with same model
uv run freud-schema run --domain arxiv --task-type extraction --model rlm-anthropic --max-iterations 8

# RLM with preset
uv run freud-schema run --domain arxiv --task-type extraction --model rlm-anthropic --max-iterations 8 --preset recursive-decomposer
```

Then compare:

```bash
# List all extractions for this skill
uv run freud-schema extraction list --skill-id 1

# Show each extraction and compare quality
uv run freud-schema extraction show <id>

# Check token usage in sessions
uv run freud-schema session list
```

The questions to answer:
- Did RLM find things single-shot missed?
- Did the preset change iteration count or sub-call patterns?
- Was the token cost justified by quality improvement?
- Did the model terminate cleanly (FINAL) or hit max_iterations?

---

## What to try next

- **Larger sources.** RLM is designed for 10K+ token inputs where single-shot
  struggles. Try concatenating multiple papers or using a long technical document.

- **Custom sub-model routing.** Use `--sub-model echo` to see what `llm_query()`
  calls the model makes without actually running them. This shows the model's
  decomposition strategy.

- **Tune max-iterations.** Some tasks converge in 3 iterations, others need 15.
  Check the trace data to find the right ceiling for your domain.

- **Phase 2 (coming).** RLM-as-verifier: use the same REPL mechanics to verify
  extraction correctness. `extraction validate N --model rlm` passes the
  extraction output as `context` instead of the source content, with a
  verification-focused skill.
