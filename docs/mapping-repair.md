# Bounded LED mapping repair

The dashboard can investigate a confirmed LED mismatch with the existing fixed
GPIO25/26 probe, ask Muse Spark 1.3 Contributor for a mapping correction, and
offer a reviewed firmware candidate. Local camera measurements must support the
exact proposed mapping. The model does not choose the probe or execute commands.

Implementation is validated with offline model, HTTP, integrity and UI tests.
The new complete repair sequence has **not yet been validated with a real Meta
request and fresh hardware captures**. Historical passes and wiring-fault
recordings remain separate evidence.

## Dashboard flow

1. Review a supported LED/OLED plan. SparkBench freezes its logical colors,
   labels and three-second timing in `contract.json`, excluding pin assignments.
2. Run a fresh camera test. After a confirmed LED mismatch, the approved bench
   workflow performs one fixed probe. It first checks current firmware, devices,
   camera geometry and the idle LEDs. Unknown LED readings, changed geometry or
   an OLED-only mismatch cannot trigger a mapping repair.
3. The protected runtime briefly tests off, GPIO25, off, GPIO26, off. Local code
   requires complete settled measurements and a unique one-to-one mapping.
4. One Contributor request receives measured LED states, frame references and
   the installed firmware's mapping assumption. It does not receive hidden fault
   labels, an inferred answer, or experiment titles. It returns a mapping,
   explanation and citations. Local validation checks all three.
5. Review the two-row mapping diff. **Approve mapping repair and retest** is the
   explicit gate before the corrected application is built, installed and tested.
   Declining keeps the current application. No-change, uncertain or rejected
   proposals cannot produce an installation.
6. The repaired candidate uses the original contract and measurement policy.
   A fresh camera pass is required. The original failed test remains linked;
   compilation, flash verification and UART identity are separate evidence.

Opening a saved result never starts a probe, model request or installation. A
saved eligible failure also has a manual probe action. There is one repair
investigation per original proposal, with no retry loop and no repair of a repair.
A failed or cancelled investigation stays recorded. Old tests that predate the
contract require a new test; they are not retroactively treated as frozen trials.

## Boundaries and retained evidence

Only the two permitted pin assignments can change. Steps, OLED text, timing,
GPIO allowlists, runtime source, calibration and verification thresholds stay
fixed. GPIO27 is unused. A mapping correction does not repair a disconnected or
damaged component, an unreadable display, or arbitrary firmware.

Each derived proposal retains its parent, exact contract bytes, failed-test
manifest hash, probe/calibration/policy hashes and model trace. Before approval,
build, installation and verification, the service rechecks the chain. A newer
parent test, changed firmware context, changed camera policy, inconsistent
capture identity or altered evidence blocks continuation. The project keeps
the accepted brief and both parent and candidate proposal links.

The repair shares the existing single-owner bench lock, cancellation and runtime
lease. Its diagnostic log includes the probe journal, measured mapping, sanitized
model request/result and candidate binding. Interrupted jobs do not resume by
themselves after a server restart.

## Validation and next live session

The 4 November implementation suite passes 309 host tests, including 20 repair
integration tests and 10 simulated frontend scenarios. These use synthetic
hardware adapters and mocked Meta transport; none is camera verification.

The remaining live check is a stable-view session with a deliberately disclosed
mapping fault, the fixed probe, a real Contributor proposal, operator approval,
and a fresh passing test against the unchanged contract. Include an unreadable
probe control that produces no candidate. Keep the servo supply off. Record
actual durations, API usage and all incomplete attempts rather than presenting
the simulated sequence as a physical result.
