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

The runtime uses the Meta Model API with `muse-spark-1.3-contributor`. Responses use JSON Schema.
Planning and explanation have separate bounded requests. During testing, the OLED reader can make
multiple requests, each for an eligible display crop. The workstation records model inputs,
outputs, latency and reported token usage. The evidence bundle includes selected records.

1. **Build guide.** Uses the idea and optional photos to draft a brief from the supported parts
   catalog, or asks for clarification.
2. **Intent planner.** Converts the brief into a structured plan of up to eight steps that the
   user reviews.
3. **OLED reader.** Transcribes one cropped display frame at a time without the expected label.
   An unreadable frame is recorded as unknown.
4. **Frame checker.** Advises the operator when the camera view is blocked. Local checks decide
   whether the view is usable.
5. **Evidence analyst.** Reads the expected steps, measured findings and up to three saved frames.
   It returns a likely cause, frame citations, uncertainty and one next check. Local validation
   rejects citations outside the supplied frames.

The local runtime validates the plan, renders firmware, controls the bench and computes the test
verdict. The model supplies planning, perception and interpretation.

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
