"""Tests for the RLM (Recursive Language Model) provider."""

import pytest

from freud_schema.orchestrator import CompletionResult, EchoProvider
from freud_schema.rlm import (
    RLMProvider,
    RLM_SYSTEM_PROMPT,
    extract_repl_block,
    load_source_content,
    run_code_in_namespace,
)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def test_extract_repl_block_basic():
    text = 'Some text\n```repl\nprint("hello")\n```\nMore text'
    assert extract_repl_block(text) == 'print("hello")'


def test_extract_repl_block_multiline():
    text = '```repl\nx = 1\ny = 2\nprint(x + y)\n```'
    assert extract_repl_block(text) == "x = 1\ny = 2\nprint(x + y)"


def test_extract_repl_block_none():
    assert extract_repl_block("No code here") is None
    assert extract_repl_block("```python\nprint(1)\n```") is None


def test_extract_repl_block_first_match():
    text = '```repl\nfirst\n```\n```repl\nsecond\n```'
    assert extract_repl_block(text) == "first"


# ---------------------------------------------------------------------------
# Code execution
# ---------------------------------------------------------------------------


def test_run_code_captures_stdout():
    ns = {}
    stdout, stderr = run_code_in_namespace("print('hello')", ns, sandbox=False)
    assert stdout == "hello\n"
    assert stderr == ""


def test_run_code_captures_stderr():
    ns = {}
    stdout, stderr = run_code_in_namespace("1/0", ns, sandbox=False)
    assert stdout == ""
    assert "ZeroDivisionError" in stderr


def test_run_code_persistent_namespace():
    ns = {}
    run_code_in_namespace("x = 42", ns, sandbox=False)
    stdout, _ = run_code_in_namespace("print(x)", ns, sandbox=False)
    assert stdout == "42\n"


def test_run_code_truncates_output():
    ns = {}
    stdout, _ = run_code_in_namespace(
        "print('x' * 200)", ns, max_output_chars=50, sandbox=False,
    )
    assert len(stdout) < 300
    assert "truncated" in stdout


def test_run_code_sandbox_blocks_import():
    ns = {}
    _, stderr = run_code_in_namespace("import os", ns, sandbox=True)
    assert stderr != ""


def test_run_code_sandbox_blocks_open():
    ns = {}
    _, stderr = run_code_in_namespace("open('/etc/passwd')", ns, sandbox=True)
    assert stderr != ""


def test_run_code_sandbox_allows_builtins():
    ns = {}
    stdout, stderr = run_code_in_namespace(
        "print(len([1, 2, 3]))", ns, sandbox=True,
    )
    assert stdout == "3\n"
    assert stderr == ""


def test_run_code_sandbox_allows_string_ops():
    ns = {"context": "hello world"}
    stdout, stderr = run_code_in_namespace(
        "print(context.upper())", ns, sandbox=True,
    )
    assert stdout == "HELLO WORLD\n"
    assert stderr == ""


# ---------------------------------------------------------------------------
# Source content loading
# ---------------------------------------------------------------------------


def test_load_source_content_text_file(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello world")
    assert load_source_content(str(f), "text/plain") == "hello world"


def test_load_source_content_json_file(tmp_path):
    f = tmp_path / "data.json"
    f.write_text('{"key": "value"}')
    assert load_source_content(str(f), "application/json") == '{"key": "value"}'


def test_load_source_content_missing_file():
    result = load_source_content("/nonexistent/file.txt", "text/plain")
    assert "not found" in result


def test_load_source_content_unsupported_type(tmp_path):
    f = tmp_path / "test.bin"
    f.write_bytes(b"\x00\x01\x02")
    result = load_source_content(str(f), "application/octet-stream")
    assert "Unsupported" in result


# ---------------------------------------------------------------------------
# Mock providers for RLM testing
# ---------------------------------------------------------------------------


class _SequenceProvider:
    """Returns responses from a pre-defined sequence."""

    def __init__(self, responses: list[str], *, input_tokens: int = 10, output_tokens: int = 5):
        self._responses = list(responses)
        self._call_count = 0
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self.calls: list[dict] = []

    def complete(self, system: str, user: str) -> CompletionResult:
        self.calls.append({"system": system, "user": user})
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        return CompletionResult(
            content=self._responses[idx],
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            model="mock",
        )

    def complete_chat(self, messages: list[dict]) -> CompletionResult:
        self.calls.append({"messages": messages})
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        return CompletionResult(
            content=self._responses[idx],
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            model="mock",
        )


class _SingleTurnProvider:
    """Provider without complete_chat -- tests fallback path."""

    def __init__(self, response: str):
        self._response = response
        self.calls: list[dict] = []

    def complete(self, system: str, user: str) -> CompletionResult:
        self.calls.append({"system": system, "user": user})
        return CompletionResult(content=self._response, model="mock-single")


# ---------------------------------------------------------------------------
# RLMProvider: direct response (no code block)
# ---------------------------------------------------------------------------


def test_rlm_direct_response():
    """Model returns plain text without code blocks -- treated as final answer."""
    provider = _SequenceProvider(["The answer is 42."])
    rlm = RLMProvider(provider, max_iterations=5)
    result = rlm.complete("Extract numbers.", "The input is forty-two.")

    assert result.content == "The answer is 42."
    assert result.metadata["rlm"]["iterations"] == 1
    assert result.metadata["rlm"]["trace"][0]["action"] == "direct_response"


# ---------------------------------------------------------------------------
# RLMProvider: REPL loop with FINAL()
# ---------------------------------------------------------------------------


def test_rlm_repl_with_final():
    """Model writes code that calls FINAL() to terminate."""
    responses = [
        '```repl\nresult = len(context)\nFINAL(f"Length: {result}")\n```',
    ]
    provider = _SequenceProvider(responses)
    rlm = RLMProvider(provider, max_iterations=5, sandbox=False)
    result = rlm.complete("Count chars.", "hello world")

    assert result.content == "Length: 11"
    assert result.metadata["rlm"]["trace"][0]["action"] == "FINAL"


def test_rlm_repl_with_final_var():
    """Model writes code that calls FINAL_VAR() to terminate."""
    responses = [
        '```repl\nanswer = context.upper()\nFINAL_VAR("answer")\n```',
    ]
    provider = _SequenceProvider(responses)
    rlm = RLMProvider(provider, max_iterations=5, sandbox=False)
    result = rlm.complete("Uppercase.", "hello")

    assert result.content == "HELLO"


# ---------------------------------------------------------------------------
# RLMProvider: multi-iteration REPL loop
# ---------------------------------------------------------------------------


def test_rlm_multi_iteration():
    """Model explores in one iteration, then terminates in the next."""
    responses = [
        '```repl\nprint(f"Context has {len(context)} chars")\n```',
        '```repl\nFINAL(f"Processed {len(context)} chars")\n```',
    ]
    provider = _SequenceProvider(responses)
    rlm = RLMProvider(provider, max_iterations=5, sandbox=False)
    result = rlm.complete("", "test input")

    assert result.content == "Processed 10 chars"
    assert result.metadata["rlm"]["iterations"] == 2
    # First iteration: code execution, no FINAL
    assert "action" not in result.metadata["rlm"]["trace"][0]
    # Second iteration: FINAL
    assert result.metadata["rlm"]["trace"][1]["action"] == "FINAL"


# ---------------------------------------------------------------------------
# RLMProvider: max_iterations limit
# ---------------------------------------------------------------------------


def test_rlm_max_iterations():
    """Loop terminates after max_iterations even without FINAL()."""
    responses = [
        '```repl\nprint("still going")\n```',
    ]
    provider = _SequenceProvider(responses)
    rlm = RLMProvider(provider, max_iterations=3, sandbox=False)
    result = rlm.complete("", "data")

    # Should have 3 iteration trace entries + 1 max_iterations entry
    assert result.metadata["rlm"]["trace"][-1]["action"] == "max_iterations"
    # Total iterations is 3 code executions + the max_iterations sentinel
    assert len(result.metadata["rlm"]["trace"]) == 4


# ---------------------------------------------------------------------------
# RLMProvider: llm_query() sub-calls
# ---------------------------------------------------------------------------


def test_rlm_llm_query_subcalls():
    """Code can call llm_query() which delegates to sub_provider."""
    sub_provider = _SequenceProvider(["Sub-answer: 42"])

    responses = [
        '```repl\nresult = llm_query("What is 6*7?")\nFINAL(result)\n```',
    ]
    inner = _SequenceProvider(responses)
    rlm = RLMProvider(inner, sub_provider=sub_provider, max_iterations=5, sandbox=False)
    result = rlm.complete("", "context data")

    assert result.content == "Sub-answer: 42"
    assert result.metadata["rlm"]["sub_queries"] == 1


# ---------------------------------------------------------------------------
# RLMProvider: token aggregation
# ---------------------------------------------------------------------------


def test_rlm_token_aggregation():
    """Tokens from multiple iterations are summed."""
    responses = [
        '```repl\nprint("step 1")\n```',
        '```repl\nFINAL("done")\n```',
    ]
    provider = _SequenceProvider(responses, input_tokens=100, output_tokens=50)
    rlm = RLMProvider(provider, max_iterations=5, sandbox=False)
    result = rlm.complete("", "data")

    assert result.input_tokens == 200  # 100 * 2 iterations
    assert result.output_tokens == 100  # 50 * 2 iterations


# ---------------------------------------------------------------------------
# RLMProvider: sandbox enforcement
# ---------------------------------------------------------------------------


def test_rlm_sandbox_blocks_imports():
    """Sandbox mode prevents import statements in REPL code."""
    responses = [
        '```repl\nimport os\nFINAL(os.getcwd())\n```',
    ]
    provider = _SequenceProvider(responses)
    rlm = RLMProvider(provider, max_iterations=5, sandbox=True)
    result = rlm.complete("", "data")

    # Import should fail; error feedback goes back, then direct response on next iteration
    # The trace should show the error in stderr_len
    trace = result.metadata["rlm"]["trace"]
    assert trace[0]["stderr_len"] > 0


# ---------------------------------------------------------------------------
# RLMProvider: fallback to single-turn (no complete_chat)
# ---------------------------------------------------------------------------


def test_rlm_fallback_single_turn():
    """When inner provider lacks complete_chat(), falls back to complete()."""
    provider = _SingleTurnProvider("The result is 7.")
    rlm = RLMProvider(provider, max_iterations=5)
    result = rlm.complete("system", "user input")

    assert result.content == "The result is 7."
    assert result.model == "mock-single"
    assert len(provider.calls) == 1


# ---------------------------------------------------------------------------
# RLMProvider: uses complete_chat when available
# ---------------------------------------------------------------------------


def test_rlm_uses_complete_chat():
    """When inner provider has complete_chat(), it's preferred."""
    responses = [
        '```repl\nprint("exploring")\n```',
        "Final answer.",
    ]
    provider = _SequenceProvider(responses)
    rlm = RLMProvider(provider, max_iterations=5, sandbox=False)
    result = rlm.complete("sys", "data")

    assert result.content == "Final answer."
    # Second call should have messages (from complete_chat)
    assert "messages" in provider.calls[1]


# ---------------------------------------------------------------------------
# RLMProvider: system prompt composition
# ---------------------------------------------------------------------------


def test_rlm_system_prompt_composition():
    """FreudAgent system prompt is appended to RLM system prompt."""
    calls_seen = []

    class _CapturingProvider:
        def complete_chat(self, messages):
            calls_seen.append(messages)
            return CompletionResult(content="done", model="mock")

    rlm = RLMProvider(_CapturingProvider(), max_iterations=1)
    rlm.complete("Extract policy numbers.", "input data")

    # The system message should contain both RLM instructions and task instructions
    system_msg = calls_seen[0][0]
    assert system_msg["role"] == "system"
    assert "REPL" in system_msg["content"]  # RLM prompt
    assert "Extract policy numbers" in system_msg["content"]  # FreudAgent prompt


# ---------------------------------------------------------------------------
# RLMProvider: context preview in initial message
# ---------------------------------------------------------------------------


def test_rlm_context_preview():
    """Initial user message contains context metadata and preview."""
    calls_seen = []

    class _CapturingProvider:
        def complete_chat(self, messages):
            calls_seen.append(messages)
            return CompletionResult(content="done", model="mock")

    rlm = RLMProvider(_CapturingProvider(), max_iterations=1)
    rlm.complete("", "A" * 1000)

    user_msg = calls_seen[0][1]
    assert user_msg["role"] == "user"
    assert "1000 chars" in user_msg["content"]
    assert "..." in user_msg["content"]  # Truncated preview


# ---------------------------------------------------------------------------
# RLMProvider: source content loading integration
# ---------------------------------------------------------------------------


def test_rlm_loads_source_content(tmp_path):
    """Source tags in user message trigger content loading."""
    f = tmp_path / "test.txt"
    f.write_text("actual file content here")

    user_msg = (
        f'<source id="1" type="text/plain" path="{f}" />\n'
        f"Execute extraction task."
    )

    calls_seen = []

    class _CapturingProvider:
        def complete_chat(self, messages):
            calls_seen.append(messages)
            return CompletionResult(content="done", model="mock")

    rlm = RLMProvider(_CapturingProvider(), max_iterations=1)
    rlm.complete("", user_msg)

    # Context preview should show loaded file content, not the XML tag
    user_content = calls_seen[0][1]["content"]
    assert "actual file content here" in user_content
    assert "Execute extraction task" in user_content


# ---------------------------------------------------------------------------
# RLMProvider: error handling in code execution
# ---------------------------------------------------------------------------


def test_rlm_code_error_fed_back():
    """Errors in code execution are fed back as user messages."""
    responses = [
        '```repl\n1/0\n```',
        "I see there was a division error. The answer is: unknown.",
    ]
    provider = _SequenceProvider(responses)
    rlm = RLMProvider(provider, max_iterations=5, sandbox=False)
    result = rlm.complete("", "data")

    assert "division error" in result.content.lower() or "unknown" in result.content.lower()
    # First iteration should have stderr
    assert result.metadata["rlm"]["trace"][0]["stderr_len"] > 0


# ---------------------------------------------------------------------------
# RLMProvider: metadata structure
# ---------------------------------------------------------------------------


def test_rlm_metadata_structure():
    """CompletionResult.metadata has the expected RLM structure."""
    provider = _SequenceProvider(["done"])
    rlm = RLMProvider(provider, max_iterations=5)
    result = rlm.complete("", "data")

    assert "rlm" in result.metadata
    rlm_meta = result.metadata["rlm"]
    assert "iterations" in rlm_meta
    assert "sub_queries" in rlm_meta
    assert "trace" in rlm_meta
    assert isinstance(rlm_meta["trace"], list)


# ---------------------------------------------------------------------------
# Integration: preset + RLM
# ---------------------------------------------------------------------------


def test_rlm_with_preset_system_prompt():
    """RLM composes correctly with archetype system prompts."""
    from freud_schema.harness import compose_preset

    preset_prompt = compose_preset("creative-explorer")
    calls_seen = []

    class _CapturingProvider:
        def complete_chat(self, messages):
            calls_seen.append(messages)
            return CompletionResult(content="done", model="mock")

    rlm = RLMProvider(_CapturingProvider(), max_iterations=1)
    rlm.complete(preset_prompt, "test data")

    system_content = calls_seen[0][0]["content"]
    # Should have both RLM and archetype content
    assert "REPL" in system_content
    assert "Operating Principles" in system_content
    assert "free-association" in system_content


# ---------------------------------------------------------------------------
# Integration: RLM in orchestrator pipeline
# ---------------------------------------------------------------------------


def test_rlm_in_orchestrator_pipeline():
    """RLMProvider works end-to-end through run_subtask."""
    from freud_schema.db import connect
    from freud_schema.orchestrator import run_subtask
    from freud_schema.store import ExperimentStore
    from freud_schema.tables import Skill, Source, Subtask

    con = connect(":memory:")
    store = ExperimentStore(con)

    store.insert_skill(Skill(
        domain="test", task_type="extraction",
        content="Extract data.", status="active",
    ))
    source_id = store.insert_source(Source(
        content_path="/data/test.txt", media_type="text/plain",
    ))

    inner = _SequenceProvider(["The extracted data is: {result: 42}"])
    rlm = RLMProvider(inner, max_iterations=5)

    subtask = Subtask(
        type="extraction",
        skill_domain="test",
        skill_task_type="extraction",
        source_ids=[source_id],
    )
    extraction = run_subtask(store, subtask, provider=rlm, model_name="rlm-mock")

    assert extraction is not None
    assert "42" in extraction.output["raw"]

    # Session should have RLM metadata
    sessions = store.list_sessions()
    assert len(sessions) == 1
    session = sessions[0]
    assert "rlm" in session.result

    con.close()
