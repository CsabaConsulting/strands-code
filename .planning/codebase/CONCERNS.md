---
last_mapped_commit: 4a23ae24e72098045e1d04b5328d95967221c4a0
last_mapped_at: 2026-09-22
---
# Codebase Concerns

**Analysis Date:** 2026-09-22

## Tech Debt

**CodeAgent mutates caller's `tools` list:**

- Issue: `tools.append(python_repl_tool)` appends in place when the caller passes a list, so the caller's list grows on every `CodeAgent` construction.
- Files: `strands_code_agent/code_agent.py`
- Impact: Reused tool lists accumulate duplicate `python_repl` entries; surprising aliasing bug in long-lived processes.
- Fix approach: Copy before appending (`tools = [*tools, python_repl_tool]`).

**Base interpreter constructor silently drops parameters:**

- Issue: `PythonInterpreter.__init__` accepts `authorized_imports`, `additional_functions`, and `timeout_seconds` but never stores them. `ExecPythonInterpreter` swallows them via `**kwargs`; only `SandboxedPythonInterpreter` and `AgentCorePythonInterpreter` handle subsets.
- Files: `strands_code_agent/python_environments/base.py`, `strands_code_agent/python_environments/local_exec.py`
- Impact: `timeout_seconds` is silently ignored for `ExecPythonInterpreter` (no timeout enforcement on bare `exec()`); inconsistent subclass contract.
- Fix approach: Store common fields in the base class and enforce/raise on unsupported options per subclass.

**Docstring contradicts actual default interpreter:**

- Issue: `CodeAgent` docstring says the default is `ExecPythonInterpreter` (unrestricted), but the signature defaults to `SandboxedPythonInterpreter`.
- Files: `strands_code_agent/code_agent.py`
- Impact: Misleads planners into assuming unrestricted execution; security-relevant misunderstanding.
- Fix approach: Correct the docstring and state explicitly that the sandbox is the default.

**Shared module-level callback handler instance:**

- Issue: `DEFAULT_CODE_AGENT_CALLBACK_HANDLER` is a single stateful object (owns a `rich.console.Console`) shared by every `CodeAgent` that uses the default.
- Files: `strands_code_agent/code_agent.py`, `strands_code_agent/callback_handler.py`
- Impact: Concurrent agents share console state; output interleaves and tests cannot isolate handler behavior.
- Fix approach: Default `callback_handler` to `None` and construct a fresh handler per agent.

**`tmp_dir` is created and never cleaned up:**

- Issue: `tempfile.mkdtemp(dir='/tmp')` per agent with no cleanup method, `close()`, or `__del__`.
- Files: `strands_code_agent/code_agent.py`
- Impact: `/tmp` fills up in long-running services or test suites that construct many agents.
- Fix approach: Add `close()`/`__enter__`/`__exit__` that removes the directory, or use `TemporaryDirectory`.

**Hardcoded `/tmp` parent directory:**

- Issue: `mkdtemp(dir='/tmp')` assumes a POSIX `/tmp` exists and is writable.
- Files: `strands_code_agent/code_agent.py`
- Impact: Breaks on Windows and locked-down containers; contradicts `requires-python = ">=3.10"` multi-platform claim.
- Fix approach: Omit `dir` (use platform default) or make it a parameter.

**Domain-symbol registry key collision:**

- Issue: `additional_functions` is keyed by `sym.__qualname__.split(".")[0]`, so two methods/nested classes sharing an outer name silently overwrite each other.
- Files: `strands_code_agent/code_agent.py`
- Impact: Wrong symbol available in the REPL with no error.
- Fix approach: Key by full `__qualname__` or raise on collision.

**Over-broad import authorization:**

- Issue: `extract_imports` adds both `node.module` and `module.name` for `ImportFrom` (e.g. `from pandas import DataFrame` authorizes `pandas.DataFrame`), and `CodeAgent` feeds all of these into `authorized_imports`.
- Files: `strands_code_agent/imports.py`, `strands_code_agent/code_agent.py`
- Impact: Authorization list is noisier than intended; semantics depend on how `smolagents` interprets dotted entries and wildcards such as `matplotlib.*` in `strands_code_agent/toolkits.py`.
- Fix approach: Authorize top-level package names only and add a test pinning the exact set.

**Frontmatter parser is naive:**

- Issue: `_parse_frontmatter` splits on `"---"` without checking that the closing fence is a full line, and `yaml.safe_load` exceptions propagate uncaught.
- Files: `strands_code_agent/knowledge/bundle.py`
- Impact: One malformed `.md` file breaks loading the entire bundle; bodies containing `---` can be misparsed.
- Fix approach: Parse line-oriented fences and wrap YAML errors with the file path.

**PDF converter slug collisions and page math:**

- Issue: Sections are keyed by `_slugify(title)` in `concept_map` and `children`, so duplicate titles overwrite each other; page extraction uses `range(start_page - 1, min(extract_end - 1, total_pages))`, which drops the last page of each section; `doc.close()` is not in `try/finally`.
- Files: `strands_code_agent/knowledge/pdf_to_okf_bundle.py`
- Impact: Silent data loss in generated bundles; file handle leak when extraction raises.
- Fix approach: Disambiguate slugs with a counter, fix the range bound, wrap `fitz.open` usage in `try/finally`.

**Undeclared `pymupdf` dependency:**

- Issue: `pdf_to_okf_bundle` does `import fitz` inside the function, but `pymupdf` appears nowhere in `pyproject.toml`.
- Files: `strands_code_agent/knowledge/pdf_to_okf_bundle.py`, `pyproject.toml`
- Impact: `ImportError` at runtime for fresh installs; example in `examples/pdf_to_okf_bundle/agent_with_knowledge.py` fails out of the box.
- Fix approach: Declare it as an optional extra (e.g. `pdf = ["pymupdf"]`) and document it.

**Global `botocore` monkeypatch on import:**

- Issue: Importing the package replaces `botocore.session.Session.__init__` process-wide with no undo hook, and `SOLUTION_UA` hardcodes `v0.4.0`.
- Files: `strands_code_agent/__init__.py`, `strands_code_agent/solution_user_agent.py`
- Impact: Side effect on every import (including tests); version string drifts from `pyproject.toml`; interacts badly with other libraries patching botocore.
- Fix approach: Register via botocore events or a documented opt-in call, and derive the version from package metadata.

**No lint/type/test automation:**

- Issue: No `ruff`/`mypy`/`black` configuration in `pyproject.toml` and the only GitHub workflow is `publish.yml` (PyPI release); there is no CI test gate.
- Files: `pyproject.toml`, `.github/workflows/publish.yml`
- Impact: Style, typing, and regression enforcement depends entirely on local discipline.
- Fix approach: Add a CI workflow running `uv run pytest` plus a linter and type check.

## Known Bugs

**Malformed bundle file crashes whole-bundle load:**

- Symptoms: `yaml.YAMLError` (or `UnicodeDecodeError`) from a single `.md` file aborts `OKFBundle._ensure_loaded`.
- Files: `strands_code_agent/knowledge/bundle.py`
- Trigger: Any concept file with invalid YAML frontmatter or non-UTF-8 bytes.
- Workaround: Manually find and fix the offending file.

**Duplicate PDF headings silently overwrite concepts:**

- Symptoms: Output bundle has fewer concepts than sections; returned `concepts` count equals unique slugs, not sections.
- Files: `strands_code_agent/knowledge/pdf_to_okf_bundle.py`
- Trigger: PDF with two identically-titled headings (common: "Introduction", "Conclusion").
- Workaround: None; rename headings in the source PDF.

**Caller tool list grows across constructions:**

- Symptoms: Duplicate `python_repl` tools when the same `tools` list is reused for multiple agents.
- Files: `strands_code_agent/code_agent.py`
- Trigger: Pass one list to two `CodeAgent(...)` constructors.
- Workaround: Pass a fresh list each time.

## Security Considerations

**LLM-generated code execution is the core attack surface:**

- Risk: `ExecPythonInterpreter` runs model-generated code via unrestricted `exec()` in-process with no timeout; the sandboxed interpreter delegates to `smolagents` `LocalPythonExecutor`, which is an allow-list sandbox, not an OS-level security boundary.
- Files: `strands_code_agent/python_environments/local_exec.py`, `strands_code_agent/python_environments/local_sandboxed.py`, `strands_code_agent/code_agent.py`
- Current mitigation: Default interpreter is `SandboxedPythonInterpreter`; `EXTRA_BUILTINS` is a small explicit list; `AgentCorePythonInterpreter` offers remote execution.
- Recommendations: Document that local execution must be treated as untrusted-code execution (run with OS sandboxing for hostile input); add timeout/resource limits to `ExecPythonInterpreter`; never switch the default to the unrestricted interpreter.

**Broad exception capture hides error types:**

- Risk: Both local interpreters stringify any exception into `stderr`, discarding type and traceback.
- Files: `strands_code_agent/python_environments/local_exec.py`, `strands_code_agent/python_environments/local_sandboxed.py`
- Current mitigation: Error text still reaches the agent as an observation.
- Recommendations: Include exception class name in `stderr` (e.g. `f"{type(e).__name__}: {e}"`) so the agent can distinguish user errors from system failures.

**Agent scratch directories are world-readable predictable paths:**

- Risk: Per-agent `mkdtemp` under shared `/tmp` with no cleanup; generated files may contain sensitive intermediate data.
- Files: `strands_code_agent/code_agent.py`
- Current mitigation: `mkdtemp` creates `0700` directories.
- Recommendations: Clean up on close and document that `tmp_dir` contents must be treated as sensitive.

**Remote interpreter ships local source to AWS:**

- Risk: `_build_initialization` serializes user-defined function source and sends it to Bedrock AgentCore; session IDs are logged at INFO.
- Files: `strands_code_agent/python_environments/agentcore.py`
- Current mitigation: Stdlib/site-packages callables are skipped; credentials come from the standard boto3 chain (no keys in code).
- Recommendations: Document exactly what source leaves the machine; keep session-ID logging but confirm log retention policy.

**YAML parsing is safe but brittle:**

- Risk: Bundle loading uses `yaml.safe_load` (good — no `yaml.load`), but a crafted file can still DoS loading via billion-laughs-style entity expansion or huge files read fully into memory.
- Files: `strands_code_agent/knowledge/bundle.py`
- Current mitigation: `safe_load` avoids arbitrary object construction.
- Recommendations: Cap file size and catch parse errors per file (see Tech Debt fix).

**No secrets detected in tree:**

- Risk: None observed; forbidden-file audit respected (`.env`/credential files not read).
- Files: `.gitignore` (covers `.env`-style entries; existence only, contents never inspected)
- Current mitigation: No credential files committed; AWS auth via boto3 default chain.
- Recommendations: Keep secrets out of `initialization_code` and toolkit strings committed to git.

## Performance Bottlenecks

**Bundle load reads every file on first access:**

- Problem: `_ensure_loaded` does a recursive `rglob("*.md")`, reads all files, builds backlinks, and rebuilds the search index synchronously.
- Files: `strands_code_agent/knowledge/bundle.py`
- Cause: No incremental loading, caching, or size cap; `toc()`, `find()`, and `read()` all trigger the full load.
- Improvement path: Cache the loaded bundle across instances (mtime-keyed), skip `index.md`/`log.md` already handled, and consider lazy body reads.

**Keyword search is O(corpus) substring scans:**

- Problem: `KeywordSearchIndex.query` runs `w in text` and `text.count(w)` over every concept for every query; substring (not token) matching.
- Files: `strands_code_agent/knowledge/search.py`
- Cause: No inverted index or tokenization; title is triple-counted by string duplication.
- Improvement path: Build a token→postings inverted index; match on word boundaries instead of substrings.

**Sandboxed executor re-initializes from scratch:**

- Problem: `clear_state()` calls `_init_executor()`, which re-instantiates `LocalPythonExecutor`, re-introspects all authorized modules via `getattr` (the code comment notes `DeprecationWarning` churn), and re-runs the preamble.
- Files: `strands_code_agent/python_environments/local_sandboxed.py`
- Cause: No state-reset shortcut in the wrapped executor.
- Improvement path: Reset only interpreter state if `smolagents` supports it; defer heavy imports until first use.

**AgentCore round-trip per call:**

- Problem: Each `execute_code` is a separate `invoke_code_interpreter` network call; `_ensure_session` adds a session-start call on first use.
- Files: `strands_code_agent/python_environments/agentcore.py`
- Cause: No batching API exposed.
- Improvement path: Document expected latency; allow callers to pre-warm the session.

## Fragile Areas

**`CodeAgent.__init__` assembly logic:**

- Files: `strands_code_agent/code_agent.py`
- Why fragile: Five toolkit fields merge with four interacting rules (auto-authorize preamble imports, skip `__main__` symbols, first-segment qualname keys, in-place `tools.append`); a change to one rule silently shifts what the model may import.
- Safe modification: Change one rule at a time and run `tests/test_code_agent.py` plus `tests/test_toolkits.py` (177 tests collected).
- Test coverage: Good for prompt assembly and import extraction; missing for the `tools.append` aliasing case and qualname collisions.

**Callback handler message-shape assumptions:**

- Files: `strands_code_agent/callback_handler.py`
- Why fragile: `__call__` indexes `message['content']`, `tool_use['input']['code']`, and `tool_result['content']` directly; `format_message` tries `ast.literal_eval` then `rich.json.JSON` (only `ValueError` caught) on arbitrary model text.
- Safe modification: Use `.get()` access with fallbacks; catch broader `Exception` around the `JSON` heuristic; add unit tests for malformed message shapes.
- Test coverage: No dedicated `test_callback_handler.py` file.

**`OKFBundle` link extraction and `toc()` heuristic:**

- Files: `strands_code_agent/knowledge/bundle.py`
- Why fragile: `_LINK_RE` only matches links ending in `.md` (query strings and extensionless links ignored); out-of-root links are silently skipped; `toc()` assumes `type == "Service"` marks top level and otherwise falls back to "most links" ranking.
- Safe modification: Extend the regex deliberately with new tests in `tests/test_okf_bundle.py`; keep `index.md`/`log.md` exclusion list in one place (`_RESERVED` vs. inline stem check are currently duplicated).
- Test coverage: Covered by `tests/test_okf_bundle.py` (186 lines) for happy paths; edge cases (dangling links, duplicate slugs) untested.

**`AgentCorePythonInterpreter` session lifecycle:**

- Files: `strands_code_agent/python_environments/agentcore.py`
- Why fragile: Lazy session creation, `__del__` performing network teardown (unreliable at GC), `_run_code` assuming `response["stream"]` shape, and silent skipping of unserializable functions (remote `NameError` later).
- Safe modification: Prefer explicit `close()` / context-manager usage over `__del__`; validate response shape; surface skipped functions as a warning.
- Test coverage: `tests/test_agentcore_python_interpreter.py` (495 lines, largest test file) mocks boto3; live paths are `integration`-marked and deselected by default.

**`solution_user_agent` import side effect:**

- Files: `strands_code_agent/solution_user_agent.py`, `strands_code_agent/__init__.py`
- Why fragile: Runs at every package import; double-import or reload stacks wrappers; hardcoded version drifts.
- Safe modification: Make registration idempotent and derive the version from package metadata; add a test asserting single registration.
- Test coverage: No test file covers this module.

**Response-metrics helper:**

- Files: `strands_code_agent/utils.py`
- Why fragile: Direct `summary['accumulated_usage']['inputTokens']` indexing assumes a fixed strands metrics shape; any SDK change raises `KeyError`.
- Safe modification: Use `.get()` with a clear error message; pin the supported shape in `tests/test_utils.py` (currently only 41 lines, image-focused).
- Test coverage: Metrics path lightly covered.

## Scaling Limits

**Single-process in-memory bundle:**

- Current capacity: Bounded by RAM; every concept body held in `self._concepts` plus duplicated title/description/body strings in `KeywordSearchIndex._texts`.
- Limit: Large documentation corpora (tens of thousands of pages) exhaust memory and make first `find()`/`read()` slow.
- Scaling path: Persist the index (sqlite/whoosh) or shard bundles per service; stream bodies from disk.

**One AgentCore session per interpreter:**

- Current capacity: Single `sessionId`; default idle timeout 900s, max 28800s.
- Limit: Concurrent `execute_code` calls on one instance race on the same session; long idle gaps silently expire server-side.
- Scaling path: Add a session pool or one-interpreter-per-worker; handle expiry by re-establishing the session transparently.

**Unbounded agent turns × local `exec`:**

- Current capacity: No turn or output cap in this package (governed by the strands harness).
- Limit: Runaway model loops consume CPU/RAM in-process for `ExecPythonInterpreter`.
- Scaling path: Enforce `timeout_seconds` uniformly and cap captured stdout/stderr size.

## Dependencies at Risk

**`strands-agents>=0.1.0` / `strands-harness>=0.1` (unbounded floor):**

- Risk: Pre-1.0 APIs churn; a fresh `uv sync` can pull breaking changes (message content shapes consumed directly by `callback_handler.py`).
- Impact: Callback rendering and `CodeAgent(Agent)` subclassing break on upgrade.
- Migration plan: Pin compatible ranges once verified (e.g. `strands-agents>=x,<y`) and add a message-shape regression test.

**`smolagents>=1.0.0` sandbox semantics:**

- Risk: Sandbox guarantees, `authorized_imports` wildcard handling, and `LocalPythonExecutor` state layout (`state["_print_outputs"]`) are all upstream internals this package depends on.
- Impact: Upgrade changes what model code can do or breaks stdout salvage in `local_sandboxed.py`.
- Migration plan: Pin the verified version; add a test asserting blocked-import and timeout behavior against the pinned version.

**`boto3` optional `agentcore` extra:**

- Risk: `AgentCorePythonInterpreter` imports `boto3` unconditionally at module import, even though `pyproject.toml` lists it only under `[project.optional-dependencies] agentcore`.
- Impact: `import strands_code_agent` fails without the extra installed.
- Migration plan: Make the import lazy inside `AgentCorePythonInterpreter` with a clear "install with `agentcore` extra" error.

**`pymupdf` (undeclared):**

- Risk: See Tech Debt; any version drift is invisible to the lockfile.
- Impact: PDF example breaks unpredictably.
- Migration plan: Declare as an extra and pin in `uv.lock`.

## Missing Critical Features

**No cleanup/close API on `CodeAgent`:**

- Problem: Neither the scratch `tmp_dir` nor the interpreter session is releasable; `AgentCorePythonInterpreter.close()` exists but `CodeAgent` never calls it.
- Blocks: Safe use in servers and test suites.

**No async or cancellation support:**

- Problem: All interpreters are synchronous; a stuck `execute_code` blocks the event loop / worker with no cancel handle.
- Blocks: Interactive latency-sensitive hosts.

**No output / resource caps:**

- Problem: No max-bytes on captured stdout/stderr, no wall-clock timeout for `ExecPythonInterpreter`, no turn budget.
- Blocks: Cost and stability control for autonomous loops.

## Test Coverage Gaps

**Callback handler — no test file:**

- What's not tested: `format_message` heuristics (literal-eval vs JSON vs Markdown fallthrough) and `__call__` with malformed `message` shapes.
- Files: `strands_code_agent/callback_handler.py`
- Risk: Rendering crash on unexpected model output goes unnoticed.
- Priority: Medium

**Solution user-agent registration:**

- What's not tested: Patch applied exactly once; version string matches `pyproject.toml`.
- Files: `strands_code_agent/solution_user_agent.py`, `strands_code_agent/__init__.py`
- Risk: Version drift and double-patch in long-lived processes.
- Priority: Low

**Error paths in `utils`:**

- What's not tested: `get_response_metrics` with missing keys or zero prices; `image_to_base64` with missing/oversized files.
- Files: `strands_code_agent/utils.py`
- Risk: `KeyError`/`OSError` propagated to agent hosts.
- Priority: Medium

**Bundle edge cases:**

- What's not tested: Malformed frontmatter, dangling links, duplicate titles/slugs, empty bundles, non-UTF-8 files.
- Files: `strands_code_agent/knowledge/bundle.py`, `strands_code_agent/knowledge/search.py`, `strands_code_agent/knowledge/pdf_to_okf_bundle.py`
- Risk: Production bundle load failures; silent concept loss.
- Priority: High

**Concurrency and lifecycle:**

- What's not tested: Concurrent `execute_code`, `clear_state` mid-execution, `AgentCorePythonInterpreter` session expiry/reconnect, `CodeAgent` with a reused `tools` list.
- Files: `strands_code_agent/code_agent.py`, `strands_code_agent/python_environments/agentcore.py`
- Risk: Race conditions and session leaks in server deployments.
- Priority: High

---

*Concerns audit: 2026-09-22*
