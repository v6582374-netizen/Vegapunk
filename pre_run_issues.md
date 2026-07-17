# PaperOrchestra Pre-run Issues

## 2026-07-17 - Discovery handoff paper-generation test

### Scope

Start a new PaperOrchestra run from
`results/AutoFatigueFractureMechanics/20260716_121133_launch`.  This is a
pipeline-execution test, not evidence of a scientifically valid paper: the
handoff summary reports zero successful Discovery candidates.

### Issue 1: Default provider configuration cannot authenticate

- **Observed:** `config/model_catalog.yaml` selected the `qwen` provider for
  text, vision, and image generation, all of which require
  `DASHSCOPE_API_KEY`.  The current process, user, and machine environments do
  not define that variable.
- **Impact:** `UnifiedModelRuntime` rejects the run before the vendored
  PaperOrchestra process can begin, with a missing API-key error for `qwen`.
- **Cause:** The repository's freshly synchronized default catalog is bound to
  DashScope, while the available local credential is `OPENAI_API_KEY` for the
  configured `relay` provider (`https://ai.cloudyz.top/v1`).
- **Change attempted:** Rebind the active text and vision roles to the existing
  `relay/gpt-5.6-sol` model and the image role to `relay/gpt-image-1`.  No API
  key is written to the repository or printed in logs.
- **Rollback:** Restore the three bindings in `config/model_catalog.yaml` to
  `qwen/qwen3.7-max`, `qwen/qwen3.6-plus`, and
  `qwen/qwen-image-2.0-pro` after providing `DASHSCOPE_API_KEY`.

### Issue 2: No successful Discovery candidate is available

- **Observed:** `discovery_summary.json` reports `total_successful: 0`.
- **Impact:** The paper generator has only the research prompt and failed-run
  materials, not validated experimental findings.  The run is useful only for
  end-to-end integration testing; its output must not be treated as a research
  result.
- **Change attempted:** None.  Preserve the handoff exactly as supplied.

### Issue 3: Windows host Python is missing declared runtime dependencies

- **Observed:** The catalog preflight failed during import with
  `ModuleNotFoundError: No module named 'json_repair'`.
- **Impact:** The launcher cannot reach its provider validation or start the
  vendored process.  This is a local Python-environment problem, not an
  upstream API, network, or concurrency failure.
- **Cause:** The available Windows Python 3.11 installation does not contain
  dependencies declared in the root `requirements.txt`; in particular it lacks
  `json_repair` (pinned to `0.51.0`) and `thefuzz` (pinned to `0.22.1`).
- **Change attempted:** Install only those two declared packages into the
  existing host Python, then re-run the no-request catalog preflight.  No
  project source is changed for this issue.
- **Verification:** Installation completed successfully and the catalog now
  initializes with `relay/gpt-5.6-sol` for text/vision and
  `relay/gpt-image-1` for images.

### Issue 4: Upstream progress was invisible in the operator terminal

- **Observed:** `_run_vendored_cli` redirected its child process stdout and
  stderr only to `stdout.log` and `stderr.log`.  `launch_paper.py` therefore
  prints no live upstream progress until the entire child process ends.
- **Impact:** An operator cannot distinguish normal long-running generation
  from a stalled process in the requested visible terminal.
- **Change attempted:** Stream each child pipe to its existing UTF-8 per-run
  log and to the launcher terminal concurrently.  The command, working
  directory, model bindings, and exit-code handling are unchanged.  Added
  `run_paper_visible.ps1` to set an UTF-8 console and start the run.
- **Rollback:** Restore the original `subprocess.run(... stdout=stdout_file,
  stderr=stderr_file ...)` block and delete `run_paper_visible.ps1` if live
  terminal forwarding is no longer needed.

### Run monitoring

The visible terminal command, PID, output files, subsequent failures, and any
further changes will be appended to this document as they occur.

### Issue 5: Installed Responses SDK rejects the cache-control argument

- **Observed:** Visible run started at 2026-07-17 16:11 (PowerShell PID
  `24920`) and reached PaperOrchestra's `OutlineAgent`, proving that the
  handoff, runtime initialization, child process, and provider dispatch path
  were entered.  Its first text request then failed with:
  `AsyncResponses.create() got an unexpected keyword argument
  'prompt_cache_options'`.
- **Impact:** The vendored CLI exits before producing an outline, TeX, or PDF.
  Its detailed output is preserved in
  `results/AutoFatigueFractureMechanics/20260716_121133_launch/paper_orchestra_runs/paper/stdout.log`.
- **Cause under investigation:** The runtime passes a cache-control keyword
  that is not accepted by the locally installed OpenAI client implementation.
  This is an SDK/request-shape compatibility failure before the upstream can
  return a model response; it is not a network, concurrency, or API-key error.
- **Change attempted:** The adapter now inspects the client's request
  signature.  It sends `prompt_cache_options` and the paired cache breakpoint
  only to legacy/relay-compatible clients that accept arbitrary keyword
  arguments; with the installed SDK it omits those extension fields while
  retaining the standard `prompt_cache_key`.  Added a strict-signature unit
  test for this path.  The failed run directory is retained as diagnostic
  evidence; the next run will use a fresh run directory rather than overwrite
  it.
- **Verification:** `python -m unittest tests.models.test_openai_responses_runtime`
  passes all 12 tests, including the strict modern-SDK request test.
- **Run archival:** The first failed `paper` directory is being retained as
  `paper_failed_20260717_161110`; a new `paper` directory will be created for
  the retry.

### Issue 6: Inherited loopback proxy blocks relay connectivity

- **Observed:** The retry reached the first upstream request but emitted no
  further progress for 25 seconds.  Its inherited `HTTP_PROXY`, `HTTPS_PROXY`,
  `ALL_PROXY` and lowercase equivalents all point to `http://127.0.0.1:9`.
- **Impact:** Requests to the configured relay are routed to a local port with
  no proxy service, so the client waits for connection retries instead of
  reaching the provider.  This is a network-environment configuration error,
  not a model or concurrency failure.
- **Evidence:** A direct relay call in this environment previously succeeded
  only after clearing those proxy variables.
- **Change attempted:** `run_paper_visible.ps1` now removes only those six
  variables from its own process before starting Python; the user's persistent
  environment is unchanged.  The in-flight retry will be stopped and archived
  because it inherited the bad proxy.
- **Verification:** With those variables removed, direct minimal `responses`
  and `chat/completions` calls to `relay/gpt-5.6-sol` both returned `OK` in
  approximately five seconds.

### Issue 7: PaperOrchestra outline request has no bounded output budget

- **Observed:** The proxy-free retry remained at its first OutlineAgent
  Responses request for several minutes without output.  `py-spy` showed the
  main thread correctly waiting in `client.responses.create`; it was not
  deadlocked.  The same provider answers small requests promptly.
- **Impact:** The default `xhigh` reasoning request has neither a
  `max_output_tokens` bound nor a practical per-request timeout (3600 seconds),
  making a minimal E2E test appear stalled for an unreasonable period.
- **Change attempted:** Configure the relay with `max_output_tokens: 4096` and
  `request_timeout: 180` in `config/model_catalog.yaml`.  This retains the
  active model and reasoning policy, gives the outline enough room for its JSON
  schema, and bounds one stalled upstream attempt to three minutes.
- **Diagnostic tool:** Installed `py-spy` into the host Python solely to inspect
  the live process stack; it did not modify project source or the running
  process.

### Issue 8: Cloudyz long Responses requests terminate at the upstream gateway

- **Observed:** The stalled outline request eventually returned HTTP 504 from
  the upstream gateway.  This occurred after the stack inspection and before
  the 3600-second client timeout.  A same-sized Outline-style request made via
  `chat/completions` with `max_tokens=4096` completed in 39 seconds, returning
  10,315 characters with `finish_reason=stop`.
- **Impact:** The cloudyz relay's Responses endpoint is unsuitable for this
  PaperOrchestra workload, even though small Responses requests succeed.
- **Change attempted:** Extend `OpenAIModel` with an explicit
  `chat_completions` transport that preserves typed text, image, JSON, and
  function-call request/response conversion.  Configure the relay provider to
  use that transport; the DashScope provider remains Responses-native.
- **Rationale:** This switches only the configured relay's transport to the
  path demonstrated to complete the real outline-sized request.  It does not
  change the provider URL, credential, model identity, or paper inputs.

### Issue 9: Full upstream Outline instruction exceeds relay's practical budget

- **Observed:** The real Outline payload is 23,094 characters (about 5,774
  input tokens), including a 12,417-character instruction and worked example.
  The Chat transport timed out at the configured 180 seconds, while a shorter
  outline-style Chat request completed in 39 seconds.
- **Impact:** The normal upstream instruction is too large for a useful
  minimal-E2E run through this relay. Retrying it three times only repeats the
  timeout.
- **Change attempted:** Add an opt-in `PAPER_ORCHESTRA_MINIMAL_E2E=1` mode.
  It replaces only the Outline instruction with a concise prompt that preserves
  the downstream JSON schema, explicitly leaves the plotting plan empty, and
  states that successful experimental evidence is absent. Added
  `config/paper_orchestra_minimal_e2e.yaml` to disable plotting. The visible
  launcher alone enables this mode; the normal PaperOrchestra configuration and
  Discovery handoff remain unchanged.

### Successful progress after Issue 9 changes

- **Visible run:** Minimal E2E run started in the visible PowerShell window
  (PID `28928`) at 2026-07-17 16:33.
- **Confirmed milestones:** The upstream CLI started, wrote `outline.json`
  (9,056 bytes), and entered the Hybrid Literature Agent. The compact outline
  intentionally supplied zero search tasks, so no external literature search
  was launched.
- **Expected warning:** The CLI warns that no figures are present. This is
  expected because minimal E2E mode explicitly disables plotting and the
  Discovery handoff has no validated experiment figures.
- **Live evidence:**
  `results/AutoFatigueFractureMechanics/20260716_121133_launch/paper_orchestra_runs/paper/stdout.log`
  contains the UTF-8 live output; the visible console displays the same stream.

### Issue 10: Full SectionWritingAgent prompt triggers cloudyz gateway timeout

- **Observed:** After Outline and literature stages completed, the full section
  writing call returned cloudyz HTTP 504. The upstream writer then restarted
  its whole three-attempt workflow from Outline.
- **Impact:** The normal section prompt concatenates the full outline,
  guidelines, template, idea, figures, and system instruction. It repeats the
  same long-prompt failure seen in the normal Outline path.
- **Change attempted:** In opt-in minimal E2E mode only, SectionWritingAgent
  now supplies a concise system instruction plus a bounded Outline excerpt,
  idea excerpt, and full LaTeX template. It asks for one complete fenced LaTeX
  document and prohibits fabricated results, figures, tables, and citations.
  The normal SectionWritingAgent prompt is unchanged.

### Issue 11: Default content-refinement loops are outside minimal E2E scope

- **Observed:** The successful initial PDF entered a three-review baseline
  ensemble and then the first of three content-refinement iterations. That
  iteration submits the full draft, review data, and screenshots to the relay
  and produced no progress during the observation window.
- **Impact:** The normal quality-refinement and formatting loops can multiply
  slow relay calls after the core handoff-to-PDF chain has already been proven.
- **Change attempted:** In opt-in minimal E2E mode, after SectionWritingAgent
  produces the draft, `paper_writer.py` copies it to the service-required
  `final_refined_paper.tex`, compiles it with the existing `compile_latex`
  helper, and writes `final_paper.pdf`. Default mode still runs the complete
  baseline, content-refinement, and formatting loops.
- **Coverage note:** Before this reduction, the live run already completed the
  initial PDF compile and all three baseline review ensemble calls, then entered
  refinement iteration 1/3.

## Final Minimal E2E Result - 2026-07-17

- **Status:** Succeeded. The visible launcher process completed; its PowerShell
  window remains open by design for operator review.
- **Final English PDF:**
  `results/AutoFatigueFractureMechanics/20260716_121133_launch/paper_orchestra_runs/paper/final_paper.pdf`
  (69,720 bytes, 3 pages, readable by `pypdf`).
- **Final TeX:**
  `content_refinement_workdir/final_refined_paper.tex` (8,039 bytes) contains
  `\\documentclass`, `\\begin{document}`, and `\\end{document}`. Its LaTeX
  log contains no fatal or emergency-stop marker.
- **Chinese companion:** `final_paper.zh-CN.pdf` was also generated (170,617
  bytes).
- **Scope caveat:** This validates Discovery-handoff-to-paper E2E mechanics in
  minimal mode. The source handoff still has zero successful experiments, so
  the resulting paper is not evidence-backed research output.

### Successful progress after Issue 10 changes

- **Confirmed artifacts:** SectionWritingAgent wrote
  `latex_writeup/raw_draft_paper.tex` (10,290 bytes), and ContentRefinement
  compiled `content_refinement_workdir/initial_draft.pdf`.
- **Current stage:** The visible run entered its baseline review ensemble. The
  final TeX/PDF pair is not yet available, so this is continuing execution,
  not a success declaration.

## Current Checkout Disposition - 2026-07-17

This review compared each Windows observation with the current `main` checkout.
It distinguishes repository defects from intentional product behavior and host-specific conditions.

| Issue | Disposition | Current conclusion |
| --- | --- | --- |
| 1 | Fixed | The default text, vision, and image bindings now use Relay. |
| 2 | Skip | A Paper Handoff without a successful candidate is intentional current behavior. |
| 3 | Skip | `json_repair` and `thefuzz` are declared in the root requirements; the Windows interpreter was incomplete. |
| 4 | Fixed | Vendored stdout and stderr now stream to both their run logs and the invoking terminal. |
| 5 | Skip | The locked `openai==2.45.0` SDK accepts the cache-control request fields; the Windows SDK was stale. |
| 6 | Skip | The PaperOrchestra child only inherited an invalid host proxy; the runtime does not create that proxy configuration. |
| 7 | Fixed in part | Both remote Providers now have a 300-second request timeout within the 900-second retry budget; the intentionally omitted default output-token ceiling remains unchanged. |
| 8 | Skip | A current 23,094-character Relay Responses probe succeeded, so the recorded 504 was not reproduced. |
| 9 | Skip | The full Outline prompt is production input, not an error to be replaced with a reduced E2E prompt. |
| 10 | Skip | The full SectionWritingAgent context is required for source-faithful paper generation; a Relay capacity failure does not justify trimming it. |
| 11 | Skip | Review and refinement loops are the normal production quality path, not an integration-test defect. |

The current checkout has no `PAPER_ORCHESTRA_MINIMAL_E2E` mode.
Any future investigation of Relay capacity must retain the full production prompts and quality loops.
