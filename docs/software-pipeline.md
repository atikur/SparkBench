# LED/OLED software pipeline

October 30, 2026: the bounded runtime, restricted Meta plan generator, acquisition
workflow, camera-based LED discovery logic and offline regression command are
implemented. The user subsequently authorized installation and live trials;
the generated green-first runtime is now installed and all four LED/OLED stages
pass. See [live-validation.md](live-validation.md) for current evidence and the
explicit repeat command. GPIO27 remains unavailable; no servo actuation is implemented.

The prior independent Contributor result remains a scoped 47-frame LED/OLED pass.
That original camera result is preserved. New live evidence covers the
generated LED/OLED behavior and approved-pin discovery, while full Behavior A/B,
continuous behavior, voltage, polarity and shaft angles remain unverified.

## Trust boundary and runtime

Meta returns JSON data only: schema version, a one-to-one red/green mapping onto
GPIO25/26, and 1–8 ordered steps. Each step has two boolean LED states and an
uppercase ASCII label of 1–16 characters. Labels permit letters, digits, spaces
and hyphens. Duration is always 3000 ms after OLED transfer. Extra fields, code,
paths, GPIO27, other GPIOs, nonboolean states and unbounded sequences are rejected.

The host compares the plan exactly to an independent servo-free specification
and the supplied mapping. A trusted renderer creates a C++ data table; generated
C++ is never accepted. Each build directory contains copied trusted runtime
sources, the table, input hashes, compiler log and binary hash. The model has no
file-writing tools. Trusted specifications, reader, calibration, runtime adapter
and compiler configuration are outside the model's output language. This is a
data boundary, not a claim that a hostile local user cannot edit project files.

The adapter uses GPIO25/26 and the fixed OLED bus SDA21/SCL22, address 0x3C,
U8g2 SH1106 128x64 profile. IC identity remains unconfirmed. LEDs boot and finish
off. There are no PWM or servo calls. Fixed serial protocol at 115200 baud:

| Command | Effect |
| --- | --- |
| `ID` / `STATUS` | Version, plan SHA-256, idle/running, OLED ACK, servo unused |
| `VISUAL` | Execute the compiled bounded table once; busy starts are rejected |
| `DISCOVER` | Off → pin25 → off → pin26 → off, independent of assumed LED mapping |
| `PING` | Renew the running lease |
| `STOP` | Immediately stop the state machine and turn both LED outputs off |

The host renews the lease every 0.4 seconds. A 1500 ms lease timeout or 30-second
overall deadline stops outputs; serial input work is bounded per loop. Timing
uses unsigned subtraction across millis rollover. These paths have native
simulation tests. Subsequent live camera shutdown tests passed; reported timing
is UART receipt timing, not a measured GPIO waveform or exact electrical latency.
The firmware is not a hard real-time safety system. `RUN` and unknown commands
are rejected. Camera acquisition never sends commands itself.

## Independent commands

All outputs must be new directories. Commands reject overwrites. None uploads
firmware. Run from the project root using the fresh local `.venv`.

Offline compile of an example data plan:

```sh
.venv/bin/python -m sparkbench build \
  --plan examples/led_oled_plan.json --output runs/software/my-build
```

`--render-only` validates/renders without invoking PlatformIO. Initial compilation
may need network access to fetch the pinned U8g2 dependency. A sandbox network
failure is retained as a compiler failure, not a board failure.

Generate and compile through Meta Contributor using the current manually
established mapping (the example mapping is **not discovery evidence**):

```sh
.venv/bin/python -m sparkbench generate \
  --spec specs/led_oled_only.json \
  --mapping examples/led_oled_mapping.manual.json \
  --max-repairs 1 --output runs/software/my-generation
```

This uses the existing `.env` selection `muse-spark-1.3-contributor` and key.
No new credential/provider is needed. Contributor's existing training terms
continue to apply. Structured generation uses the documented
[Meta JSON Schema endpoint](https://dev.meta.ai/docs/structured-output).
The generator sees the behavior specification; the separate OLED reader sees
only image crops and its unchanged generic transcription prompt.

Repairs are limited to rejected model output: default one repair, hard maximum
two (at most three requests). Refusal, HTTP errors, rate limits, service errors
and connection failures stop the run without retries. Valid data followed by a
compiler failure stops for a trusted build fix; the model cannot edit runtime
sources to repair it. Each request/response/rejection is retained. No automatic
physical repair, flashing or unlimited retry loop is implemented.

## One-command camera test

For the historical LED/OLED diagnostic, explicitly select freshly
enumerated serial and camera IDs:

```sh
.venv/bin/python -m sparkbench workflow \
  --port 'FRESH_CP2102_PORT' --device-id 'EXPLICIT_IPHONE_ID' \
  --output runs/workflows/my-test
```

This checks the frozen reader policy before hardware access, verifies the exact
diagnostic idle identity/OLED ACK and increasing heartbeat, waits for live camera
frames, sends one `VISUAL`, measures saved pixels, calls Meta only for text,
compares to the independent specification, and retains a workflow report plus
integrity manifests. Existing diagnostic acquisition and its servo prohibition
are unchanged. A missing/uncertain measurement remains incomplete. A conclusive
mismatch fails. The full-rig status remains incomplete without actual servo angles.

`--run SAVED_RUN` performs a new analysis of saved frames and **makes Meta
requests**. Use `replay` below for an entirely offline recheck.

After a separately authorized, hash-verified runtime installation, add
`--artifact GENERATED_ARTIFACT_DIRECTORY`. That requires the exact runtime
version/plan identity; it refuses the installed diagnostic or an unrelated saved
run. The binary SHA in acquisition is the expected local artifact, not camera
evidence or independent flash readback. Every runtime capture renews the lease
and attempts STOP on completion/error. No upload command is exposed here.

## LED discovery

After runtime installation/qualification, live discovery is:

```sh
.venv/bin/python -m sparkbench discover \
  --artifact GENERATED_ARTIFACT_DIRECTORY \
  --port 'FRESH_CP2102_PORT' --device-id 'EXPLICIT_IPHONE_ID' \
  --output runs/discovery/my-probe
```

The approved probe pool is only GPIO25/26. Power, ground, OLED wiring and servo
stay fixed. The five probe phases use fresh DISCOVER timing markers and calibrated
LED camera pixels only, with the same 0.65/0.45-second settling guards, minimum
five frames, maximum 0.65-second sample gaps and endpoint coverage limits.
UART state values are ignored for inference. No Meta requests or OLED text
recognition are needed to infer the two LED connections.

All off baselines must settle off. Each pin must produce one stable, unique LED
response; the other lens must remain off. Missing, uncertain, unstable, duplicate
or multiple responses leave the mapping null/incomplete. No fallback to the known
manual wiring exists. `--run SAVED_DISCOVER_RUN` analyzes a saved probe without
hardware. A successful recorded discovery JSON can later serve as `--mapping`
for generation. Synthetic/replay regressions are labeled and do not count toward
blind physical mapping qualification.

## Regression and evidence

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m sparkbench replay \
  --analysis runs/vision/contributor-validation-2026-10-30-v1 \
  --output runs/software/my-replay
```

Replay checks saved integrity, reconstructs readings from recorded independent
pixel/Meta records and calibration, reruns comparison, and exercises wrong LED,
wrong OLED and missing-reading controls on passing datasets. It uses no camera,
serial or API and creates no new physical evidence. Earlier incomplete results
remain incomplete and unchanged. Native C++ tests execute the production adapter
against fake serial/GPIO/display, including lease expiry, stop, rejected commands,
input flooding and rollover. Those tests are synthetic software evidence.

Real development evidence for this stage:

- `runs/software/meta-generated-v1/generation.json`: one actual Contributor
  request, valid first response, local ESP32 compile, no repair or upload.
- `runs/software/meta-generated-v1/attempt-01/artifact/artifact.json`: hashed
  trusted inputs and compiled binary.
- `runs/software/replay-contributor-v1/replay.json`: saved 47-frame result and
  digital controls reproduced without new API calls.
- `runs/software/runtime-local-v1/`: initial sandbox dependency-fetch failure,
  retained rather than relabeled as a hardware failure.

The subsequent [live stage](live-validation.md) completed runtime installation,
sequence/STOP/lease qualification, real discovery and a scoped generated LED/OLED
cycle. Physical LED-swap negative test, blind wiring trials, proper servo bracket
and measured angles, and full-rig acceptance remain pending. There is no temporary
servo mount.
