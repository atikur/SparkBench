# Submission form answers

## Team name

SparkBench

## Track

Indie Developer Track, solo entry.

## Problem statement

Push the Frontier.

## Project description

SparkBench helps makers and students verify that the firmware they built does what they asked
for on a physical board. A user describes a behavior in plain language. Muse Spark drafts a brief
and a plan of up to eight steps for a classic ESP32 with two LEDs and an OLED. After the user
approves the plan, the bench agent checks the camera, uses trusted local code to build and
install the application as needed, verifies its identity, and records the board as it runs.

The verifier measures LED states from pixels and compares them with the plan alongside Muse
Spark's transcription of the OLED. The recorded READY/BUSY/DONE project passed all 26 sampled
observations with zero mismatches and zero unknowns. In a separate intentional wiring-swap test,
the verifier recorded 36 wrong-channel findings across 47 samples. Unreadable or missing
observations leave a test incomplete.

Muse Spark also gives an advisory explanation of saved evidence and proposes a check the operator
can perform. The dashboard can wait for the operator and re-test the same plan. The recorded
explanations shown in the demo come from incomplete captures. The evidence bundle documents these
runs separately. The repository includes the engineering log from the hackathon and a host test
suite.

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
   approves. A fresh camera pass is the only thing that counts as recovery.
3. **Evidence analyst (vision and reasoning).** Reads the frozen expected steps, the measured
   findings and up to three saved frames, then names a likely cause, cites frames, states what it
   cannot determine and proposes one check. Citations outside the supplied frames are rejected.
4. **Intent planner (text).** Turns the brief into a plan of up to eight steps, or one question.
   It never sees the test oracle.
5. **Build guide (text).** Drafts the brief from the idea and the supported parts
   catalog, or asks for clarification.
6. **Frame checker (vision).** When the camera check is blocked, says which parts are cut off and
   how to move the phone. It cannot clear the check.
7. **Idea suggester (text).** On request, suggests three projects for this bench. Each carries steps
   that must pass the same validator as a real plan, and it only fills the idea box.
8. **SAM 3.1 region proposer.** During camera setup, proposes the screen and lens regions from a
   fresh capture. A separate capture validates the resulting reference with the frozen thresholds.
   SAM never takes part in a verdict.
9. **Muse Voice transcriber.** Turns a spoken idea of up to 30 seconds into editable text in the
   idea box. The audio is never stored, and nothing is planned until the person has reviewed the text.

The local runtime validates every plan, renders the firmware, controls the bench and computes the
verdict. The models plan, perceive, interpret and propose; they never grade their own work.

## Why are Meta's models important to your solution?

Muse Spark connects a plain-language request to physical evidence. It plans a bounded behavior
that a beginner can inspect, then reads the display without being given the expected text. That
separation lets local code compare an observed value with the approved plan. When a capture is
incomplete, Muse Spark can explain what the frames show and give the operator a concrete check
without changing the recorded result.

## Optional fields

- **Most Viral X post link.** Enter the post URL if a video is published on X.
- **Partner technology feedback.** The hosted Meta Model API supplied runtime inference.
- **Development tools.** The author used Codex and Claude Code during development.
- **Model feedback.** An early frame inspection spent its 1,024-token budget before answering.
  Some lone OLED digits were also difficult to read at small text sizes. Enlarging the rendered
  digits helped address the latter in subsequent recordings.

## Before submitting

Confirm the repository and demo links are accessible from a signed-out browser. Replace the
README's video note with the final link and use the same URL in the form. Review required fields
and permissions in the signed-in form. See the [demo script](demo.md) and
[evidence index](evidence/README.md).
