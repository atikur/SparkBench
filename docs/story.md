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
| 3. Approve and run | One approval; the agent compiles, connects, installs and confirms identity, skipping what the records already prove | None. Trusted code only; Meta never writes C++ |
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

## Demo script, 3 minutes

The rules allow three minutes, require that the video show only work built during the hackathon,
and say judges must be able to tell what that is. All of SparkBench was built between 27 October
and 4 November, so say it once at the start, keep it on screen, and label recorded footage.

1. 0:00 Title card: "SparkBench. Built from scratch, 27 Oct – 4 Nov 2026." One line over the home
   page: "AI builds it. Who checks it?"
2. 0:15 On the home page, type the desk-light sentence into the box and press "Plan it with Muse
   Spark". A panel opens: Muse Spark's brief, then the step table.
3. 0:45 Press "Approve plan and run on the bench" in the panel. The project opens on the running
   screen: the camera frame, five phases and one chip per plan step, filling in as the agent works.
4. 1:10 The phone watches the board. Verdict: verified on camera, with the numbers and the frame.
5. 1:40 Swap the two LED wires. Press "Run again". The result screen shows mismatch, with the failing steps marked.
6. 2:05 The agent asks Muse Spark to explain; its explanation names the swap and gives one next check,
   and the plan stays unchanged.
7. 2:30 Evidence tab: pass, caught fault and an honest incomplete side by side. Limits dialog for
   two seconds.
8. 2:45 Closing card: what Meta does (plans, reads the display, explains) and what it never does
   (write the firmware, grade itself). Tagline. Repository link.

Record the dashboard at desktop width with the phone's view in a corner.

## Submission checklist, from the participant guide

Deadline: Wednesday 4 November, 9:00 PM ET (Thursday 5 November, 8:00 AM in Dhaka), on the
Cerebral Valley platform. Late submissions are not considered.

- [ ] **Problem statement:** Push the Frontier. Say it in the form and in the README (done).
- [ ] **Track:** Indie Developer or Startups, one only. The Representative submits for the team.
- [ ] **Repository public** before submitting. It is private now.
- [ ] **Everyone who worked on the project listed** on the submission page.
- [ ] **Three-minute video** at an accessible link, showing only hackathon-built work, opening with
      the built-from-scratch card.
- [ ] **New work only, clearly identified.** The README states it and `docs/history.md` is the
      dated log. Repeat it in the form's description.
- [ ] **Meta Model API use stated plainly:** `muse-spark-1.3-contributor` (Muse Spark series) for
      the brief, the plan, the blind OLED read and the explanation; every request saved on disk.
- [ ] **$150 Meta credits** claimed by each participant individually by the same deadline.
- [ ] **Bonus prizes to tick:** Best Agentic Use-Case (the bench agent: one click runs compile,
      install, identity and camera test, skips what the records already prove, reads a non-pass
      result with Muse Spark and decides the next step, stopping wherever a person is needed); Community Vote (share the gallery
      link after submitting); Most Viral (post the video on X and submit the post link).
- [ ] **Do not claim:** Best Build on Meta Open Weight Models (we use the hosted API, not Muse
      Glimmer or Muse Spark Open) and Best Creative Build (no Muse Image or Muse Wonder).

Optional, only with hours to spare after everything above: route the Explain step through Muse
Spark Open on Baseten (`meta-models/muse-spark-open-1026`, which accepts images) as a selectable
provider, which would make the open-weight bonus eligible. It needs a Baseten key and about three
hours, so it is not in the plan.

## How the rubric reads this

- **Impact 30%.** A concrete trust gap with a concrete user, solved with hardware people already
  own. The honest incomplete state is the credibility that makes the pass believable.
- **Use of Meta AI tooling 25%.** Four roles, including blind perception and evidence-grounded
  reasoning, with every input and output on disk. Judges can see what the model saw.
- **Demo 25%.** Six beats, each one screen, the last one a payoff.
- **Technical depth 20%.** A trust boundary that keeps the model out of the actuation path, a
  deterministic verifier, integrity-checked evidence, 250 tests. Say it once, show it in the Limits.
