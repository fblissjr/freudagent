"""Recursive Language Model (RLM) provider for the experiment harness.

RLM is an inference-time scaffold that treats the user's prompt as a variable
in a persistent Python REPL. The model writes code to probe, slice, and
transform its input, and can recursively call itself (llm_query()) on subsets.

Architecture:
    - RLMProvider wraps an inner Provider (typically OpenAICompatProvider)
    - The REPL loop is the model's execution strategy, not orchestration
    - FreudAgent system prompts (archetypes, rules, skill) are appended
      to the RLM system prompt, not replaced
    - llm_query() delegates to a sub_provider for recursive sub-calls
"""

from __future__ import annotations

import io
import re
import signal
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from freud_schema.orchestrator import CompletionResult, Provider

from freud_schema.orchestrator import parse_source_tags, strip_source_tags


# ---------------------------------------------------------------------------
# RLM system prompt (adapted from the paper's Appendix C)
# ---------------------------------------------------------------------------

RLM_SYSTEM_PROMPT = """\
You have access to a Python REPL environment with a variable called `context` \
that contains the input data you need to process.

## Available Tools

- `context` (str): The full input text/data to process
- `llm_query(query: str) -> str`: Call a language model on a sub-question. \
Use this for tasks requiring reasoning over slices of the context.
- `print()`: Display intermediate results (output is fed back to you)
- Standard Python builtins for string manipulation, data processing, etc.

## How to Use the REPL

Write Python code in ```repl blocks:

```repl
# Your code here
result = context[:1000]
print(f"First 1000 chars: {result}")
```

The code executes in a persistent namespace -- variables persist across iterations.
You can write multiple iterations of code, building on previous results.

## Termination

When you have your final answer, call one of these functions in a code block:

- `FINAL("your answer text")` -- return a string answer
- `FINAL_VAR("variable_name")` -- return the value of a namespace variable

If your response contains no ```repl block, the response text itself is \
treated as the final answer.

## Strategy

1. Start by exploring the context: check its length, structure, first/last segments
2. Use slicing and search to find relevant sections
3. Use `llm_query()` for reasoning tasks on manageable chunks
4. Aggregate and format your final answer
5. Call FINAL() or FINAL_VAR() when done
"""


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_REPL_BLOCK_RE = re.compile(r"```repl\n(.*?)```", re.DOTALL)


def extract_repl_block(text: str) -> str | None:
    """Extract the first ```repl code block from model output."""
    match = _REPL_BLOCK_RE.search(text)
    return match.group(1).strip() if match else None


# ---------------------------------------------------------------------------
# Source content loading
# ---------------------------------------------------------------------------


def load_source_content(path: str, media_type: str) -> str:
    """Load source content as a string for the RLM context variable.

    Handles text files directly, JSON with formatting, and degrades
    gracefully for unsupported types.
    """
    p = Path(path)
    if not p.exists():
        return f"[Source file not found: {path}]"

    if media_type.startswith("text/") or media_type in (
        "application/json",
        "application/jsonl",
    ):
        return p.read_text(encoding="utf-8", errors="replace")

    if media_type == "application/pdf":
        # Try pdftotext from poppler-utils; degrade gracefully
        try:
            import subprocess  # noqa: S404 -- sandboxed pdftotext only

            proc = subprocess.run(  # noqa: S603, S607
                ["pdftotext", str(p), "-"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return (
            f"[PDF content not extractable: {path}. "
            f"Install poppler-utils (pdftotext) for text extraction.]"
        )

    return f"[Unsupported media type {media_type} for content loading: {path}]"


# ---------------------------------------------------------------------------
# Sandboxed code execution
# ---------------------------------------------------------------------------

# Restricted builtins for sandboxed execution. Blocks import, open, exec, eval,
# compile, and other dangerous builtins. This does NOT prevent attribute-access
# exploits (e.g., obj.__class__.__bases__[0].__subclasses__()) -- for that you'd
# need RestrictedPython's AST-level guards. Acceptable tradeoff for an experiment
# harness where the "attacker" is an LLM we prompted, not an adversary.
_SAFE_BUILTINS = {
    "abs", "all", "any", "bin", "bool", "bytes", "callable", "chr",
    "complex", "dict", "dir", "divmod", "enumerate", "filter", "float",
    "format", "frozenset", "getattr", "hasattr", "hash", "hex", "id",
    "int", "isinstance", "issubclass", "iter", "len", "list", "map",
    "max", "min", "next", "object", "oct", "ord", "pow", "print",
    "range", "repr", "reversed", "round", "set", "slice", "sorted",
    "str", "sum", "tuple", "type", "vars", "zip",
}


def _make_sandbox_builtins() -> dict:
    """Create a restricted builtins dict for sandboxed code execution."""
    import builtins

    return {
        name: getattr(builtins, name)
        for name in _SAFE_BUILTINS
        if hasattr(builtins, name)
    }


def run_code_in_namespace(
    code: str,
    namespace: dict,
    *,
    timeout: int = 30,
    max_output_chars: int = 10_000,
    sandbox: bool = True,
) -> tuple[str, str]:
    """Execute code in a persistent namespace, capturing stdout/stderr.

    Returns (stdout, stderr) as strings, truncated to max_output_chars.
    """
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    if sandbox and (
        "__builtins__" not in namespace
        or not isinstance(namespace.get("__builtins__"), dict)
    ):
        namespace["__builtins__"] = _make_sandbox_builtins()

    old_handler = None
    use_alarm = sys.platform != "win32" and timeout > 0

    if use_alarm:
        def _timeout_handler(signum, frame):
            raise TimeoutError(f"Code execution timed out after {timeout}s")

        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(timeout)

    try:
        compiled = compile(code, "<rlm-repl>", "exec")
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            exec(compiled, namespace)  # noqa: S102
    except TimeoutError as e:
        stderr_buf.write(str(e))
    except Exception as e:
        stderr_buf.write(f"{type(e).__name__}: {e}")
    finally:
        if use_alarm:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

    stdout = stdout_buf.getvalue()
    stderr = stderr_buf.getvalue()

    if len(stdout) > max_output_chars:
        stdout = (
            stdout[:max_output_chars]
            + f"\n... (truncated, {len(stdout)} total chars)"
        )
    if len(stderr) > max_output_chars:
        stderr = (
            stderr[:max_output_chars]
            + f"\n... (truncated, {len(stderr)} total chars)"
        )

    return stdout, stderr


# ---------------------------------------------------------------------------
# RLMProvider
# ---------------------------------------------------------------------------


class RLMProvider:
    """Provider that wraps an inner provider with an RLM REPL loop.

    The model receives the input data as a ``context`` variable and writes
    Python code to probe, slice, and transform it. Each iteration's code
    runs in a persistent namespace, with results fed back as conversation
    turns.
    """

    def __init__(
        self,
        inner,  # Provider
        *,
        sub_provider=None,  # Provider | None
        max_iterations: int = 10,
        max_output_chars: int = 10_000,
        timeout: int = 30,
        sandbox: bool = True,
    ):
        self._inner = inner
        self._sub_provider = sub_provider or inner
        self._max_iterations = max_iterations
        self._max_output_chars = max_output_chars
        self._timeout = timeout
        self._sandbox = sandbox

    def _build_context(self, user: str) -> str:
        """Build context from user message, loading source content when possible."""
        sources = parse_source_tags(user)
        if not sources:
            return user

        parts = []
        for src in sources:
            content = load_source_content(src["path"], src["media_type"])
            parts.append(
                f"--- Source: {src['path']} ({src['media_type']}) ---\n{content}"
            )

        # Include non-source text (task params etc.)
        non_source = strip_source_tags(user)
        if non_source:
            parts.append(f"--- Task ---\n{non_source}")

        return "\n\n".join(parts)

    def complete(self, system: str, user: str) -> "CompletionResult":
        from freud_schema.orchestrator import CompletionResult

        # Build namespace with context and termination functions
        context = self._build_context(user)
        namespace: dict = {"context": context, "_rlm_final": None}

        def final_fn(value=""):
            namespace["_rlm_final"] = str(value)

        def final_var_fn(name):
            if name in namespace:
                namespace["_rlm_final"] = str(namespace[name])
            else:
                namespace["_rlm_final"] = f"[Variable {name!r} not found]"

        namespace["FINAL"] = final_fn
        namespace["FINAL_VAR"] = final_var_fn

        # Inject llm_query() with sub-call counting
        sub = self._sub_provider
        sub_query_count = 0

        def llm_query(query: str) -> str:
            nonlocal sub_query_count
            sub_query_count += 1
            result = sub.complete("", query)
            return result.content

        namespace["llm_query"] = llm_query

        # Compose system prompt: RLM instructions + FreudAgent context
        full_system = RLM_SYSTEM_PROMPT
        if system:
            full_system += f"\n# Task Instructions\n\n{system}\n"

        # Initial user message: metadata about context
        ctx_len = len(context)
        preview = context[:500] + ("..." if ctx_len > 500 else "")
        initial_msg = (
            f"Context loaded ({ctx_len} chars, type: str).\n"
            f"Preview:\n{preview}\n\n"
            f"Process this context according to your task instructions."
        )

        # Message history for multi-turn
        messages = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": initial_msg},
        ]

        # Tracking
        total_input_tokens = 0
        total_output_tokens = 0
        trace: list[dict] = []
        last_model = None
        final_content = ""
        response_text = ""

        for iteration in range(self._max_iterations):
            # Call inner provider (prefer multi-turn if available)
            if hasattr(self._inner, "complete_chat"):
                result = self._inner.complete_chat(messages)
            else:
                # Fallback: flatten to single-turn
                flat_user = "\n\n---\n\n".join(
                    m["content"] for m in messages if m["role"] == "user"
                )
                result = self._inner.complete(full_system, flat_user)

            if result.input_tokens:
                total_input_tokens += result.input_tokens
            if result.output_tokens:
                total_output_tokens += result.output_tokens
            if result.model:
                last_model = result.model

            response_text = result.content

            # Extract and run code
            code = extract_repl_block(response_text)
            if code is None:
                # No code block -- treat response as final answer
                final_content = response_text
                trace.append({"iteration": iteration + 1, "action": "direct_response"})
                break

            # Execute code in namespace
            stdout, stderr = run_code_in_namespace(
                code,
                namespace,
                timeout=self._timeout,
                max_output_chars=self._max_output_chars,
                sandbox=self._sandbox,
            )

            trace.append({
                "iteration": iteration + 1,
                "code_len": len(code),
                "stdout_len": len(stdout),
                "stderr_len": len(stderr),
            })

            # Check if FINAL/FINAL_VAR was called
            if namespace["_rlm_final"] is not None:
                final_content = namespace["_rlm_final"]
                trace[-1]["action"] = "FINAL"
                break

            # Build feedback message
            feedback_parts = []
            if stdout:
                feedback_parts.append(f"Output:\n{stdout}")
            if stderr:
                feedback_parts.append(f"Error:\n{stderr}")
            if not feedback_parts:
                feedback_parts.append("(no output)")

            feedback = "\n".join(feedback_parts)
            messages.append({"role": "assistant", "content": response_text})
            messages.append({"role": "user", "content": feedback})
        else:
            # Max iterations reached
            if namespace["_rlm_final"] is not None:
                final_content = namespace["_rlm_final"]
            else:
                final_content = response_text or "[Max iterations reached]"
            trace.append({"iteration": self._max_iterations, "action": "max_iterations"})

        return CompletionResult(
            content=final_content,
            input_tokens=total_input_tokens or None,
            output_tokens=total_output_tokens or None,
            model=last_model,
            metadata={
                "rlm": {
                    "iterations": len(trace),
                    "sub_queries": sub_query_count,
                    "trace": trace,
                }
            },
        )
