# SparkBench contest readiness audit — 3 November 2026

**Implementation update:** the natural-language intent workspace is now implemented and passed an eight-case real Contributor software benchmark plus one dashboard end-to-end request. See [the planning evidence and limits](intent-planning.md). The audit below describes the pre-improvement state; physical diagnosis/repair and full-rig acceptance remain pending.

The user confirmed the Meta Global AI Developer Hackathon (26 October–4 November 2026). This audit reviews current code and recorded evidence plus the official public rules. It is not an organizer eligibility ruling or an estimate of winning probability. No model requests, firmware uploads or hardware commands were issued for this audit.

## Rules and judging

The [official rules](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/waiver), dated 25 October, score Impact 30%, Use of Meta AI Tooling 25%, Demo 25%, and Technical Depth and Execution 20%. Meta usage is judged on creativity and going beyond basic integration. The public rules require Meta AI products; no explicit exclusion of Contributor mode or non-Meta coding assistants was found. Third-party technical assistance and open-source components are allowed subject to original-work, ownership and licensing conditions. This does not amount to a specific organizer ruling on Codex.

The [official event page](https://dev.meta.ai/events/global-hackathon) lists a submission deadline of 4 November at 9 PM ET: 5 November at 8 AM in Dhaka. The submission form redirects to login, so required video duration, repository visibility and other submission fields remain unverified. Check the authenticated form before final packaging. Keep the user's tighter completion target.

[Meta's pricing documentation](https://dev.meta.ai/docs/pricing-rate-limits) describes Contributor as the same models at discounted prices in exchange for training-use permission. There is no evidence-based reason to change model tier just for eligibility. Runtime Meta use and Codex-assisted development must be described separately.

## What AI actually does

| Function | Current implementation | Demonstrated evidence |
| --- | --- | --- |
| OLED text perception | Muse Spark 1.3 Contributor sees cropped images without expected labels | Latest independent LED/OLED run: 45 settled samples, zero unknowns/mismatches |
| Behavior generation | Meta returns bounded JSON from a complete step specification and a supplied mapping | One real first-attempt generation compiled; no physical repair demonstrated |
| LED wiring discovery | Deterministic camera-pixel inference from approved GPIO25/26 probes | Five operator-withheld choices confirmed; 11 attempts, six incomplete retained |
| Servo localization | Deterministic native image processing with supervised initialization | 46/46 held-out static frames within one recording; angles remain unverified |
| Pass/fail and runtime limits | Deterministic independent verifier and trusted adapter | Software tests and scoped LED/OLED results; full-rig acceptance incomplete |
| Full-rig A/B generation | Implemented but requires measured calibration | Only disabled synthetic A/B builds exist so far |

Primary local references: `src/sparkbench/meta.py`, `generation.py`, `plans.py`, `fullrig.py`; `runs/live/qualification-2026-10-30-v1/11-discovered-generation/generation.json`; `runs/live/led-oled-resume-2026-11-03-v1/summary.json`; and `runs/servo-reference/current-view-exposure-2026-11-03-v2/summary.json`.

The generation weakness is concrete: `plans.expected_plan()` and `fullrig.requested_behavior()` already construct the exact answer. The generation prompts ask the model to copy step values. This is real API use, but modest reasoning demand. Existing repair is rejected-JSON/spec correction; it is not a closed loop diagnosing and correcting a physical failure. Do not describe the product as unrestricted firmware code generation, AI wiring discovery, or an autonomous hardware engineer.

## Competitive assessment

Strongest existing value: independently checking the physical result of an AI-assisted embedded workflow, with retained failures and an explicit unknown state. The target user should be an embedded developer, educator or prototyper who needs to distinguish a successful build/UART acknowledgement from correct visible hardware behavior.

A public self-described entrant, [RobotForge](https://www.abelxmendoza.com/), describes natural-language/photo/parts input, structured model specifications, deterministic robot simulation and a repair loop. This is its author's description, not independently reproduced performance or an official ranking. It shows that AI plus verification alone is not enough differentiation. SparkBench should demonstrate its actual physical bench, camera evidence and detection of a real wiring fault. There is no reliable basis here for ranking SparkBench against the whole field or estimating prize odds.

## Prioritized improvements

1. **Meaningful intent-to-plan generation.** Add a separate Meta-only entry point taking compact natural-language intent and the supported hardware capability contract, rather than the completed answer table. Example: count zero through three, show the count, use green for even counts and red for odd counts, finish with outputs off and DONE. Freeze an independently authored test oracle before model calls; never derive the oracle from the model output. Preserve fixed duration, bounded steps, GPIO allowlist and trusted rendering. Test unseen paraphrases, unsupported requests and ambiguity; ambiguity should ask for clarification. Report all outcomes. Keep original A/B acceptance specifications unchanged.
2. **Evidence-grounded fault explanation and bounded repair proposal.** Start from retained LED-only failures. Give Meta the request, measured outcomes and linked frames; require evidence references, uncertainty and one permitted next probe or plan/mapping patch. The independent OLED reader still receives no expected answer. Schema checks, measured mapping and the verifier govern any proposed repair; Meta cannot change limits or mark its own answer passed. Offline diagnosis is possible while waiting for instruments. A claimed physical repair requires an actual subsequent authorized bench run and camera verification; do not fabricate a failure or relabel deterministic mapping as an AI discovery.
3. **A coherent demonstration and clear entry point.** Replace the judge-facing wall of historical README updates with current setup, user problem, AI roles, evidence and limitations; preserve history elsewhere. Show request → model plan → physical result → deliberately introduced fault → evidence-based diagnosis/proposal → verified recovery. Label recorded footage, time cuts and offline replay. A 2–3 minute cut is an editorial target, not a confirmed contest requirement. Make the current verified LED/OLED path demonstrable while servo calibration remains pending; this is a scoped demonstration, not completion of original full-rig scope.
4. **Measure useful outcomes.** Compare the same tasks against a simple deterministic/table-entry baseline. Report task success, rejected/unknown results, real model calls, recorded latency and token usage; estimate cost only from returned usage and cited rates. Do not claim reduced debugging time without a timed comparison. The existing 155 host tests support engineering quality but do not measure product impact.

Implement one complete LED/OLED intent/diagnosis demonstration before expanding peripherals or adding models. Contributor is the appropriate starting point; evaluate its settings against frozen tasks rather than paying for a different tier without evidence. Work on the planner, read-only diagnosis and presentation can proceed independently of the protractor. Physical calibration, moving-range tracking and integrated A/B acceptance remain separate required work.

## Submission claim boundary

Use: “SparkBench uses Meta AI to plan supported embedded behaviors and read the physical display, while an independent camera verifier checks what the hardware actually did.” The planning claim should remain scoped to the current structured-spec input until the intent interface is implemented and tested.

Current defensible shorter claim: “Meta-assisted behavior generation with independent camera verification of LEDs and OLED text.” Keep actual servo angles, general board discovery, arbitrary firmware generation, autonomous physical repair and production safety qualification out of completed claims.
