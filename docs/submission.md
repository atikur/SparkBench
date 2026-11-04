# Submission form answers

## Team name

SparkBench

## Team members

Md Atikur Rahman, solo entry.

## Track

Indie Developer Track.

## Problem statement

Push the Frontier.

## Most Viral X post link

Optional. Enter the post URL only if the video is published on X.

## Project description

SparkBench proves that the firmware an AI wrote does what you asked for on a physical board. A build that compiles and flashes says nothing about what the LEDs and the display actually did, and checking by eye is slow and unreliable. SparkBench closes that gap for makers, students and small hardware teams who use AI to write firmware.

You type or speak an idea for a classic ESP32 with two LEDs and an OLED. Muse Spark turns it into a reviewable plan of up to eight steps. After approval, the bench agent takes over: SAM 3.1 outlines the display and both LEDs in the camera view, trusted local code builds and installs the firmware and confirms its identity, and an iPhone records the board as the plan runs. Local code measures the LEDs from pixels, and Muse Spark reads the OLED without being told what to expect. A deterministic verifier compares both with the frozen plan and returns pass, mismatch or incomplete. Missing or unreadable measurements never count as a pass.

When the camera finds a mismatch, the agent investigates. In the recorded session on 4 November I swapped the two LED wires and did not tell the model. The test failed with 38 mismatched readings across 28 samples. The agent ran a fixed pin probe, Muse Spark worked out the swapped mapping from the measurements alone, local code checked the proposal against the probe, I approved the exact change, and a fresh test passed 27 of 27 samples with the wires still swapped. The steps, labels and timing never changed. The same night a second plan's fault was fixed by hand and passed on retest, and two incomplete tests from that session stay on record.

This is Push the Frontier in a small, honest form: Meta's models give a machine the ability to check its own work in the physical world, with an explicit trust boundary. Models plan, perceive and propose; local code controls the hardware and computes every verdict. Everything in the repository and the video was built during the hackathon, 27 October to 4 November 2026, with development assistance from Codex and Claude Code. The supported bench is one ESP32 with two LEDs and an OLED; the mounted servo is not verified.

## Public GitHub repository

https://github.com/atikur/SparkBench

## 3-minute demo video

https://www.youtube.com/watch?v=y6KSh-sNYX0

Public on YouTube, 2 minutes 56 seconds. The README links the same video as https://youtu.be/y6KSh-sNYX0. The [demo video guide](demo.md) lists what each part shows.

## Describe your use of Meta products to build the submitted project

SparkBench uses three Meta products through the Meta Model API: Muse Spark
(`muse-spark-1.3-contributor`) in seven roles, SAM 3.1 for camera setup, and Muse Voice
(`muse-voice-transcribe-1.0`) for spoken ideas. Every Muse Spark
call returns strict JSON through JSON Schema, one bounded request per action with no retries, and
the workstation records each request, response, latency and token count with integrity hashes.
The evidence bundle in the repository includes selected records.

In order of weight in the proof:

1. **OLED reader (vision).** Transcribes one cropped display frame at a time without the expected
   label. Its reading is independent evidence, not confirmation. An unreadable frame stays unknown.
2. **LED mapping analyst (reasoning).** After a confirmed LED mismatch, local code runs a fixed
   pin probe on camera. Muse Spark receives the settled measurements, never the images or the
   hidden answer, and proposes a one-to-one pin mapping with cited frames. Local code accepts the
   proposal only if it matches the complete probe, and nothing is flashed until the operator
   approves. A fresh camera pass is the only thing that counts as recovery. This ran on the real
   board on 4 November with a disclosed wire swap: one request, 5.5 seconds, and the retest passed.
3. **Evidence analyst (vision and reasoning).** Reads the frozen expected steps, the measured
   findings and up to three saved frames, then names a likely cause, cites frames, states what it
   cannot determine and proposes one check. Citations outside the supplied frames are rejected.
4. **Intent planner (text).** Turns the brief into a plan of up to eight steps, or one question.
   It never sees the test oracle.
5. **Build guide (text).** Drafts the brief from the idea and the supported parts
   catalog, or asks for clarification.
6. **Frame checker (vision).** When the camera check stops and needs a person, compares the view with
   the saved one and says what to fix. It cannot clear the check.
7. **Idea suggester (text).** On request, suggests three projects for this bench. Each carries steps
   that must pass the same validator as a real plan, and it only fills the idea box.
8. **SAM 3.1 region proposer.** Camera setup is the first thing a new plan does. SAM outlines the
   screen and both LED lenses in a fresh capture, and the run shows its boxes on the frame. A
   separate capture validates the resulting reference with the frozen thresholds.
   SAM never takes part in a verdict.
9. **Muse Voice transcriber.** Turns a spoken idea of up to 30 seconds into editable text in the
   idea box. The audio is never stored, and nothing is planned until the person has reviewed the text.

The local runtime validates every plan, renders the firmware, controls the bench and computes the
verdict. The models plan, perceive, interpret and propose; they never grade their own work.

## Why are Meta's models important to your solution?

Muse Spark connects a plain-language request to physical evidence. It plans a bounded behavior that a beginner can inspect, reads the display without being given the expected text, and, after a confirmed fault, works out the pin mapping from probe measurements alone. SAM 3.1 makes camera setup automatic by outlining the parts in a fresh frame, and Muse Voice lets the idea start as speech.

Each role is one bounded, strict-JSON request with no retries. The models interpret, perceive and propose; deterministic local code validates plans, controls the trusted runtime and compares measured outputs with the approved plan. That separation is what makes the verdict trustworthy. A model never grades its own work, missing evidence stays incomplete, and Muse Spark can still explain a failure without changing the recorded result.

## Provide feedback from your experience using partner technologies

Optional. SparkBench runs on the hosted Meta Model API and did not use Fireworks, Modal or Baseten,
so this can stay blank.

## Remaining form fields

The ratings, opinion questions and permission checkbox are the entrant's own, so they are not drafted here.

## Model notes

These are not form fields. An early frame inspection spent its 1,024-token budget before answering.
Some lone OLED digits were difficult to read at small text sizes, and enlarging the rendered digits
helped in later recordings. SAM's red LED outline sometimes took in a neighboring lead and failed the
size check, so each lens is now judged on its own.

## Before submitting

Confirm the repository and demo links are accessible from a signed-out browser. The README and
the form use the same video link. Review required fields
and permissions in the signed-in form. See the [demo video guide](demo.md) and
[evidence index](evidence/README.md).
