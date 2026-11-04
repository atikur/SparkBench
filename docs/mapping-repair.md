# Bounded LED mapping repair

The dashboard can investigate a confirmed LED mismatch with the existing fixed
GPIO25/26 probe, ask Muse Spark 1.3 Contributor for a mapping correction, and
offer a reviewed firmware candidate. Local camera measurements must support the
exact proposed mapping. The model does not choose the probe or execute commands.

The complete sequence ran on real hardware on 4 November 2026, with a real Meta
request and fresh captures. See [Live validation](#live-validation) below.

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

## Live validation

On 4 November 2026 the operator deliberately swapped the two LED signal wires, with
the servo supply off. Muse Spark was not told. The extract is in the
[evidence bundle](evidence/repair-run.json).

| Stage | Recorded result |
| --- | --- |
| Fault test | Mismatch: 38 mismatched field readings across 28 samples, 0 unknown |
| Fixed probe | GPIO25 lit green and GPIO26 lit red, with no unknowns |
| Muse Spark proposal | Red 26, green 25, in one request of 5.5 s and 3,817 tokens. Local code accepted it against the probe. |
| Operator approval | Approved the two-row mapping diff. The behavior contract was unchanged. |
| Retest, wires still swapped | Pass: 27 samples, 0 mismatches, 0 unknown |

A second plan was run the same night through the hand-fix route: a mismatch of 36
readings across 27 samples, then **Keep current firmware**, then restoring the wires
by hand. Two camera checks stopped because the operator had moved the LEDs instead
of the wires. After the LEDs were put back, two tests stayed incomplete with 10 and 9
unknown readings, because the red LED no longer sat at its saved position. A new
camera setup then gave a pass with 27 samples, 0 mismatches and 0 unknown.

These are single runs on one bench. They do not establish general reliability. The
unreadable-probe control, which should produce no candidate, has not been run on
hardware. It remains covered only by the simulated tests, which use synthetic
hardware adapters and mocked Meta transport.
