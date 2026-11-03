# SparkBench: the story, the scope, the claims

This is the single source of truth for the hackathon submission. If a screen, a sentence in the
README, or an hour of work does not serve this story, it goes.

## The story in one breath

AI can write firmware in seconds and say "done". Nobody checks whether the board actually did it.
SparkBench makes the AI prove it. You describe what the board should do. Muse Spark turns it into a
plan. Trusted code builds and installs it. An iPhone watches the board while it runs. Muse Spark
reads the display without being told what to expect, and an independent verifier compares what
happened with what was planned. When it fails, Muse Spark explains why from the evidence. Unknowns
stay unknown. **Proof beyond the build.**

## Who it is for

Makers, students and educators who use AI to build small hardware and have no way to tell "it
compiled" from "it works". The gap is real and growing: the easier AI makes firmware, the more
boards get flashed with code nobody verified. SparkBench is the verification layer that closes it,
with nothing more than a board, a phone and a Meta key.

## The loop, and where Meta works

| Beat | What the judge sees | Meta's role |
| --- | --- | --- |
| 1. Describe | A sentence about a desk status light | Muse Spark clarifies it, picks parts from the kit, writes a brief |
| 2. Plan | A step table: red, green, OLED label, 3 s each | Muse Spark turns the brief into at most 8 steps, or asks one question |
| 3. Build & install | Compile, connect, install, identity confirmed over USB | None. Trusted code only; Meta never writes C++ |
| 4. Verify | The camera test passes: 45 samples, 0 mismatches, 0 unknown | Muse Spark reads each OLED frame blind |
| 5. Catch | Two LED wires swapped on purpose; the verifier flags 36 mismatches | None. The verifier is deterministic |
| 6. Explain | "Why?" Muse Spark reads the evidence and names the swap, with the frames it used | Muse Spark reasons over expected steps, measurements and images |

Four distinct Meta roles in one loop, and two deliberate places where Meta is kept out. That contrast
is the point: the model plans and perceives, trusted code acts, and nothing grades its own work.

## What we claim

- Meta Muse Spark plans supported embedded behaviours and reads the physical display.
- An independent camera verifier checks what the hardware actually did, catches a real wiring
  fault, and reports incomplete instead of pass when it cannot read the display.
- When a run fails, Muse Spark explains the failure from the recorded evidence and proposes one next
  check. The explanation is advisory and cannot change a verdict.
- Every Meta request and every hardware action is an explicit button, audited to disk with hashes.

## What we do not claim

- No arbitrary firmware generation. Meta proposes data; a trusted renderer writes the C++.
- No servo, no sensors, no other boards. One kit: ESP32, two LEDs, one OLED.
- No continuous verification. Verdicts cover sampled settled windows in the recorded view.
- No autonomous repair. The explanation proposes; a person acts and the camera re-checks.

## Scope for the submission

**Keep, as built:** Projects flow with one action per stage; Plan, build, verify page; Evidence
with proof cards; the Limits dialog.

**Add, in this order:**

1. **Explain a failure with Muse Spark.** One button on a failed or incomplete run, on the run page
   and in the Verify card. Meta receives the frozen expected steps, the per-sample measurements and
   two or three frames, and returns a structured explanation with the evidence it cited, a
   confidence, and one bounded next check. It never receives the verdict logic and cannot mark
   anything passed. This closes the loop and is the strongest single answer to "went beyond a
   basic integration".
2. **A camera pass on the hero project.** Refresh the camera reference and run the test on the
   installed READY/BUSY/DONE firmware so the project a judge opens first ends in a verified pass,
   not "installed".
3. **A fresh wiring-swap run on the hero project, if time allows,** so the caught fault and its
   explanation belong to the same project the demo starts with.

**Cut:** SAM 3.1 segmentation, servo calibration, full-rig acceptance, new peripherals, any planner
benchmark expansion. All remain documented as future work.

## Demo script, 2 minutes 30 seconds

1. 0:00 Problem in one line over the home page. "AI builds it. Who checks it?"
2. 0:15 New project. Type the desk-light sentence. Muse Spark's brief appears. Accept and plan.
3. 0:45 The plan table. Compile, connect, install. "Identity confirmed over USB" is not a pass.
4. 1:10 Run camera test. The phone watches the board. Verdict: passed, with the numbers.
5. 1:35 Swap the two LED wires. Run again. "Behavior mismatch, fault correctly detected." Open the
   frame: expected green, observed red.
6. 2:00 Press Explain. Muse Spark names the swap and cites the frames. One next check.
7. 2:20 Evidence tab: pass, caught fault, and an honest incomplete side by side. Tagline.

Record the dashboard at desktop width with the phone's view in a corner. Label recorded footage.

## How the rubric reads this

- **Impact 30%.** A concrete trust gap with a concrete user, solved with hardware people already
  own. The honest incomplete state is the credibility that makes the pass believable.
- **Use of Meta AI tooling 25%.** Four roles, including blind perception and evidence-grounded
  reasoning, with every input and output on disk. Judges can see what the model saw.
- **Demo 25%.** Six beats, each one screen, the last one a payoff.
- **Technical depth 20%.** A trust boundary that keeps the model out of the actuation path, a
  deterministic verifier, integrity-checked evidence, 232 tests. Say it once, show it in the Limits.
