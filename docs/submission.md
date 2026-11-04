# Submission form answers

Draft text for the Cerebral Valley submission form, matched to its fields. Copy each block in as
it is, or trim it. Everything stated here is true of the repository as of 4 November 2026.

## Team name

SparkBench

## Track

Indie Developer Track. A solo entry, judged on creativity, technical ambition and whether it works.

## Problem statement

Push the Frontier.

## Most Viral X post link

Only if you post the video on X. Paste the post's link here after posting.

## Project description

SparkBench is proof beyond the build for AI-written firmware.

AI coding agents can write embedded firmware in seconds and report success. For a board on a desk,
success usually means the code compiled and the serial port printed DONE. Nobody checks whether the
red LED is actually red, whether the OLED says READY or REAOY, or whether two wires are swapped.
Beginners cannot tell the difference, and experienced engineers lose hours finding out.

SparkBench closes that loop on a real bench: a classic ESP32, two LEDs and a small OLED. You type
what the board should do in plain words. Muse Spark turns it into a brief and an 8-step plan that
you approve. An agent then builds the firmware with trusted local code, flashes the board, confirms
the board's identity over USB, checks that the phone camera is in position, and records the board
while the plan runs. A deterministic verifier measures the LEDs from pixels, Muse Spark reads the
OLED text from each frame without being told what to expect, and the verdict comes from comparing
those measurements with the frozen plan. When the board does something else, such as two LED wires
swapped, the camera catches it and Muse Spark explains the likely cause from the recorded frames.
When the display cannot be read, the result stays incomplete rather than becoming a pass.

Everything was built during the hackathon, from the first board bring-up on 27 October. The
repository has a dated engineering log, 250 host tests, and every Meta request saved on disk.

## Describe your use of Meta products to build the submitted project

All model calls go to the Meta Model API with muse-spark-1.3-contributor (the Muse Spark series),
using structured output through JSON Schema, one bounded request per action, and no retries.
Every request, response, latency and token count is saved under runs/ with integrity hashes, so a
judge can see exactly what the model was given and what it returned.

Muse Spark plays five distinct roles:

1. Build guide (text and up to three photos): turns the idea into a brief, asks at most one
   question when the ambiguity changes the plan, and refuses hardware outside the supported bench.
2. Intent planner (text): returns the plan as strict JSON, up to 8 steps, or a clarification. It
   never sees the test oracle.
3. Blind OLED reader (vision): transcribes one cropped OLED frame at a time and is never told the
   expected label. An unreadable frame stays unknown.
4. Frame checker (vision): when the camera check fails, compares the calibrated view with the
   current frame and tells the person which parts are cut off and how to move the phone. It
   cannot clear the check.
5. Evidence analyst (vision and reasoning): on a failed or incomplete run, receives the frozen
   expected steps, the measured findings and up to three recorded frames, then names the likely
   cause, cites the frames and proposes one safe next check. It cannot change the verdict.

The model proposes data, never code, and never grades itself. Trusted local code renders the
firmware, enforces a pin allowlist and step limits, and an independent verifier decides the result.

## Why are Meta's models important to your solution?

Two of the five roles are only possible with a capable vision model, and both are at the heart of
the proof. The OLED reader has to transcribe small, blurry display text from a phone frame without
knowing the answer, so that its reading is independent evidence rather than confirmation. The
evidence analyst has to look at real frames of a breadboard and explain a physical fault in words
a beginner can act on. Muse Spark's structured output lets every one of these calls return strict
JSON that local code validates, which is what keeps the model out of the actuation path and out of
the verdict. The planner and build guide make the whole loop usable by someone who has never written
firmware: plain words in, an approved plan out, and the camera decides whether it worked.

## Partner technologies feedback

Optional. Baseten credits were issued but SparkBench did not use Baseten, Modal or Fireworks: the
hosted Meta Model API covered every call. Say that, or leave the field empty.

## Survey questions

These ask for your own opinion and are not judged. Two notes:

- The Muse Code question is optional (no asterisk). SparkBench was not built with Muse Code, so
  leave it blank rather than guessing.
- For the biggest obstacle, the one real one we hit was reasoning tokens using up the completion
  budget: the frame checker's first live call ran out of its 1,024-token budget before answering
  even at low reasoning effort, and the OLED reader spends most of its budget on reasoning at
  minimal effort. "Something else" with that one sentence is useful feedback. The other candidate
  is the reader declining some lone digits at small text sizes, which we fixed by enlarging the
  firmware's text.

## Before pressing Submit

- Public GitHub repository: make https://github.com/atikur/SparkBench public first. The form
  needs the link, and the rules require it public.
- Demo video: upload to YouTube and paste the watch link. Put the same link in README.md.
- Tick the permission box. The form will not submit without it.
- Claim the $150 Meta credits separately, by the same deadline.
