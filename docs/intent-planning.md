# Natural-language planning workspace

Start `.venv/bin/python -m sparkbench dashboard`, type an idea on the home page and press **Plan it with Muse Spark**. SparkBench sends the brief's firmware intent to the planner. This is an explicit paid API action using the existing `muse-spark-1.3-contributor` configuration. Opening the dashboard or a saved plan makes no model request. The dashboard no longer offers a separate quick-plan entry; the planner's HTTP endpoint and the command-line benchmark are unchanged.

Meta receives the instruction and a fixed capability contract. It does not receive the benchmark's expected answer, an existing completed step table, camera measurements or a pass/fail oracle. It interprets order, counting, parity and other finite rules into up to eight LED/OLED steps. Every step has a fixed three-second duration; labels have 1–16 uppercase ASCII characters within the existing trusted data language. A proposed mapping is supplied by local code, never chosen by the model; any future live use still needs the appropriate hardware identity/mapping checks.

Possible results:

- **Ready for review:** locally valid step data. This is not semantic or physical acceptance. Inspect the steps and optionally mark the exact proposal reviewed.
- **Clarification needed:** answer the displayed question in the project conversation, accept the revised brief, then prepare the plan again. No executable plan is saved.
- **Unsupported:** hardware, timing, code or sequence length exceeds the supported contract. No executable plan is saved.
- **Invalid response / request failed:** retained as a failure. There is no retry, provider fallback or automatic repair request.

Saved proposals live under `runs/planning/intent-v1/{id}/`. Each contains the request, returned response when available, result, local integrity hashes and a ready plan when applicable. The dashboard displays actual latency and returned token usage. A review record binds the unchanged plan hash and does not authorize a build, flash or execution. Reloading and opening saved proposals rechecks local integrity and makes no model call.

The local service serializes planning jobs. Repeated submissions with the same request ID within a server session reuse the existing job; another request while busy is rejected. Action endpoints require the current local session token and same-origin browser request. Credentials remain server-side. Reviewed plans now have separate compile, application-only installation and camera-test actions in [the bench workflow](dashboard.md#run-a-reviewed-ledoled-plan). Marking a plan reviewed alone performs none of those actions. Raw serial and servo commands are not exposed.

## Validation on 3 November 2026

The current host suite passed 175 tests; ten new tests use mocked model responses for schema/limit checks, clarification, HTTP failures, no retries, request deduplication, saved-plan integrity, review binding and local HTTP authorization. A subsequent focused ten-test run checked final saved-state hardening.

A separately frozen eight-case **real Contributor software benchmark** passed all eight cases on one request each: parity, countdown, divisibility, ambiguous intent, servo request, unsupported timing, excess steps and contract-override request. The three ready plans exactly matched independently authored expected steps; the ambiguous request asked for clarification and the other four were unsupported. This is a small planning benchmark, not a general reliability estimate or physical behavior test. All expected answers and raw outcomes are retained under `runs/software/intent-planner-2026-11-03-v1/` and were not supplied to Meta.

One additional real request through the dashboard produced a four-step count/parity proposal. An agent-side exact-step check verified its data. It remains pending operator review and physical testing. Nine real API requests were made in this implementation stage, with no retries. No camera, serial, servo, firmware build or upload was performed.

The later dashboard execution stage connects a separately operator-reviewed proposal to compilation, installation and fresh LED/OLED camera testing. Its evidence and API counts are separate from this planning benchmark. Evidence-grounded failure explanations, independent servo angle calibration and full A/B physical acceptance remain incomplete.
