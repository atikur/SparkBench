# SparkBench local dashboard plan

Planning baseline: 3 November 2026. This document defines the dashboard; it does not authorize a new firmware installation or servo movement. The accompanying interactive screen is a layout proposal using two existing recorded runs. It does not operate the rig or call Meta.

Implementation update: the recorded viewer, intent planning and separate reviewed-plan compile/install/camera-test workflow are implemented. Read-only diagnosis remains pending. See [the current dashboard guide](dashboard.md); the stages below retain the original planning baseline. Servo calibration and full-rig acceptance remain incomplete.

## Product goal

An embedded developer should be able to describe supported behavior, inspect a proposed plan, run a bounded test, and see what the physical hardware actually did. Judges should understand the input, Meta's contribution and independently measured outcome from a single screen.

Delivery target: a local desktop web app on this Mac. The existing Swift helper acquires the explicitly selected iPhone camera. Existing Python modules remain responsible for generation, builds, capture, measurements and comparisons. No phone app, account system, cloud deployment or additional AI provider is part of this dashboard scope.

## Screen structure

One bench workspace, with a small run-history rail. Keep primary work visible rather than spreading it over many pages.

- **Header:** SparkBench, current mode (Recorded or Live), scoped rig status. In recorded mode show capture date and recorded device, not a claim that the device is currently connected. In live mode the timestamp of the last host status check matters. Show STOP only when an actual controllable job exists.
- **Request / plan area:** future natural-language input, clarification, proposed LED/OLED steps, review action. An actual plan states what Meta supplied and what trusted software imposed. Do not display invented reasoning or a model-written pass verdict. Initial evidence-only release hides or clearly disables this area.
- **Camera / evidence area:** dominant image, frame selector, capture timestamp, measured sample marker and inspection overlays when available. Opening a saved frame does not start the camera. Use “Live sampled frames” rather than promising video if the backend is serving sampled JPEGs. Full-resolution originals remain available; thumbnails are display derivatives only.
- **Results area:** expected versus observed values from the exact selected frame, separate overall run verdict and scope, counts of failures/unknowns, expandable evidence provenance. Keep the image and selected observation synchronized.
- **Diagnosis area:** later Meta evidence-based explanation and proposed next action. An explanation cannot change measurements, thresholds or verdicts. Label offline diagnosis and actual verified recovery separately.
- **History:** select real completed or incomplete runs; retain failures. Avoid decorative global project scores and simulated activity.

Visual direction: restrained engineering workspace, neutral surfaces, readable system typography, one teal accent for selection. Pair semantic status colors with words/icons. Desktop camera/results columns become stacked on narrow screens. Use compact, visible labels and keyboard-operable controls.

## First release: recorded evidence viewer

The initial route opens the latest independent LED/OLED check. The screen can switch to the physical wiring-swap test and an incomplete run. No API call, camera access, serial connection or compilation occurs when loading or navigating it.

Initial catalog:

1. `runs/live/led-oled-resume-2026-11-03-v1/latest-view-oled-fresh/analysis/verification.json`: 45 settled LED/OLED samples, no mismatches or unknowns; recorded scoped behavior pass.
2. `runs/live/led-oled-resume-2026-11-03-v1/physical-led-swap-negative-fresh-v2/result.json`: 47 settled LED samples, 36 wrong-channel readings, no unknowns; behavior mismatch, fault correctly detected. Its outer `status: pass` is a successful negative test, not correct hardware behavior.
3. `runs/live/led-oled-resume-2026-11-03-v1/latest-view-oled-verification/analysis/verification.json`: retained incomplete OLED analysis. The report exists; the catalog adapter must preserve its incomplete state and unknown readings.
4. Optional second milestone: within-session static servo tracking, visibly labeled localization only; physical angles remain unmeasured.

The selected frame view includes both expected and observed state. For the wiring-swap test, OLED is unmeasured rather than blank/failed/off. Servo angles are unmeasured everywhere they lack qualified physical readings. Between-frame behavior and transition intervals are outside the current verified scope.

Keep provenance available in a disclosure: source run, timestamp, original image hash, specification, reader/model identity where applicable, and integrity check result. Recorded runs may have passed in their own view without establishing current rig readiness.

## Build architecture

Prefer the existing Python environment and a small static HTML/CSS/JavaScript frontend. A lightweight local HTTP service exposes an explicit run catalog and normalized view data. No frontend package/build toolchain is required for the first release. If later asynchronous job needs justify a framework, choose it during that integration, not to build the initial viewer.

Suggested module boundaries, not implemented yet:

- `dashboard/catalog.py`: explicit approved run entries, schema adapters, source paths and capabilities.
- `dashboard/evidence.py`: read-only normalized run/frame/step records and integrity status.
- `dashboard/server.py`: loopback-only static and JSON/image routes.
- `dashboard/static/`: one responsive workspace and renderer; no verifier logic.
- Later `dashboard/jobs.py`: bounded serialized jobs and cancellation bridge into existing Python workflows.

Initial routes: `GET /api/runs`, `GET /api/runs/{id}`, `GET /api/runs/{id}/frames/{frame_id}`, and the corresponding allowlisted image route. Frame identity maps to a known file in the selected run; clients cannot request arbitrary absolute paths. Model output and recorded text render as text, never executable HTML. Credentials and raw filesystem browsing never appear in responses.

Normalized view model: `run_id`, `mode`, `recorded_at`, `scope`, `source_kind`, `acquisition_status`, `measurement_status`, `behavior_verdict`, `qualification_outcome`, `frame_count`, `evaluated_sample_count`, `mismatch_count` with unit, `unknown_count` with unit, `frames`, `expectations`, `observations`, `model_activity`, `integrity`, and `capabilities`. Unsupported or absent data stays explicitly unavailable; unknown timestamps/costs are not guessed.

The UI consumes existing verifier outputs. It never recomputes acceptance from pixels or rewrites the source result. In particular, loading a recorded run must not call `workflow.execute(source_run=...)`, which performs fresh paid analysis. Offline replay and fresh Meta analysis are distinct future actions.

## Delivery order

### Milestone 1 — Browse trustworthy evidence

Implement catalog adapters and the read-only local service, then the bench screen with run selection, actual frame selection, expected/observed comparison, scoped statuses and provenance. Include pass, physical-negative and incomplete cases. This is the first independently deliverable dashboard.

Acceptance:
- Sample counts and displayed values match source records for all three cases.
- A selected image and observation always refer to the same frame.
- Opening/browsing generates zero hardware operations and zero Meta requests.
- Null values never become zero, off or pass.
- Changed/missing evidence shows a visible unavailable/integrity state rather than stale success.
- Every saved image is labeled Recorded; synthetic fixtures, if added, are separate and labeled Synthetic.
- Desktop and narrow layouts remain usable with keyboard navigation and text labels.

### Milestone 2 — Meaningful AI planning and read-only diagnosis

Add natural-language intent to bounded plan generation using the existing Meta API and Contributor configuration. Integrate clarification, plan review, schema validation and comparison against independently authored benchmark expectations. Keep the benchmark answers out of generation requests. Show the proposal, not fake progress or invented reasoning.

Add evidence-grounded explanations of saved failures, with linked observations and uncertainty. Save actual requests/results and token usage; show costs only when derivable from recorded usage and documented rates. Existing credentials suffice. Generation and analysis calls are explicit actions; browsing remains free of API activity.

Acceptance: real model output is displayed as a proposal, invalid/ambiguous/unsupported requests do not become executable plans, original A/B expectations remain unchanged, and diagnosis cannot override the verifier.

### Milestone 3 — Controlled live LED/OLED workflow

Add stages Draft → Review → Compile → Ready → Capture → Analyze → Verify. Firmware installation is a separate explicit operation and is not hidden inside Run. Use fresh host camera/serial enumeration, artifact identity and existing preflight checks. Support only the currently authorized LED/OLED execution path initially.

One server-side job owns camera/serial at a time. The browser never sends raw serial commands. Add a real cancellation interface to the worker so STOP reaches the existing cleanup path through the same serial owner. An HTTP cancellation or browser disconnect alone is not proof of output shutdown. Display “Stop requested” until acknowledgement, and “Shutdown unconfirmed” if it cannot be established. The firmware lease remains a fallback with its existing limitations.

Keep endpoints on loopback, reject untrusted origins and require a local session token for actions. Avoid command-shell concatenation and arbitrary client-supplied paths. Logs, source snapshots and outputs remain in new evidence directories.

Acceptance: UI failures cannot create a second hardware owner, browser refresh cannot start or duplicate a job, STOP is tested through the worker, real connection failures are visible, and an acquisition-complete state cannot masquerade as a physical pass.

### Milestone 4 — Calibrated full-rig integration

Enable only after independent physical calibration, supported moving-range tracking and runtime prerequisites are satisfied. A dashboard does not remove those requirements. Until then the UI shows “Servo angle unmeasured / full-rig acceptance incomplete.”

## Demonstration sequence

For the first release: open a real scoped pass → inspect one frame and expected/observed states → switch to real wiring-swap failure → show fault correctly detected → show an incomplete result with unknown readings. Explain where Meta read OLED text and where deterministic software performed measurement/comparison.

Later replace recorded navigation with one genuine intent-to-plan LED/OLED run and an authorized physical diagnosis/recovery sequence. Recorded examples remain a clearly labeled fallback. Do not make a proposed interface or offline diagnosis look like a completed live model workflow.

## Scope and release gate

Finish and review Milestone 1 before expanding. Its usefulness does not depend on the protractor. Intent/diagnosis and live-control integration are separate deliverables; they should not delay the first readable evidence demonstration. Tests focus on schema adaptation, read-only behavior, source integrity, status distinctions and selected-frame consistency. Test cancellation and concurrency when live actions are actually added.
