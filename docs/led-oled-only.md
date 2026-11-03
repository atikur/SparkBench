# LED/OLED-only diagnostic

This diagnostic is historical and is no longer installed. The current generated
runtime, live qualification and repeat command are in [live-validation.md](live-validation.md).

On 30 October 2026 the user authorized installing `firmware/led_oled_test` and
running it with camera capture. Upload completed with all segment hashes
verified. It is now the installed firmware; the previous `firmware/rig_test`
record is preserved in `hardware/board.json` under `firmware_history`.

The current diagnostic uses only GPIO25, GPIO26 and the fixed SDA21/SCL22
OLED bus at 7-bit address 0x3C. It preserves the working SH1106 128x64 profile;
the actual controller identity remains unconfirmed. It contains no servo GPIO
writes or PWM calls. LEDs are off at boot. It accepts `ID`, `STATUS`, `VISUAL`
and `STOP`, rejects `RUN`, and completes the bounded sequence with LEDs off.
This is a hand-written diagnostic, not the pending protected runtime or
generated firmware. Do not actuate the servo without its proper bracket.

| Step | Red | Green | OLED label | Dwell after display transfer |
| --- | --- | --- | --- | --- |
| 1 | off | off | DARK | 3 seconds |
| 2 | on | off | RED | 3 seconds |
| 3 | off | on | GREEN | 3 seconds |
| 4 | on | on | BOTH | 3 seconds |
| 5 | off | off | DARK END | 3 seconds |

The independent expected sequence is `specs/led_oled_only.json`. Its values
are expectations, not observations. It has no invented servo angle and is
not a full-behavior verifier input.

## Recorded run

Evidence is local under `runs/led-oled/20261030T043224.829848Z/`:

- `run.json`: completed acquisition and passing UART-reported sequence.
- `preview.mp4`: 24.32-second video-only playback made from the saved JPEGs;
  durations follow sample PTS, while originals remain authoritative evidence.
- `uart.jsonl`: raw received bytes, parsed lines, command events, host uptime
  and Unix receipt timestamps. Startup/replay bytes are retained.
- `camera/`: 110 JPEGs at 1920x1080, `frames.jsonl` with camera PTS and host
  timestamps, and a completed video-only `capture.json` for 25 seconds.
- `inspection_selection.json`: settled frames selected about 1.5 seconds
  after each UART step receipt, away from transitions.
- `visual_review.json`: agent readings of the actual LED lenses and OLED
  text in five saved frames, plus the final COMPLETE/LEDs off frame.
- `spec.snapshot.json`, `runner.snapshot.py`, `integrity.json`: execution
  inputs and SHA-256 manifest. The manifest is integrity evidence, not
  authentication of physical behavior.

Only `ID` and one `VISUAL` command were sent. The runner required the exact
fresh idle identity `SPARKBENCH LED_OLED_TEST MODE:IDLE OLED:ACK SERVO:UNUSED`,
increasing idle heartbeats, and three fresh saved camera frames before starting.
The UART step intervals were 3129, 3128, 3128 and 3128 ms, including display
transfer time. All five steps, completion and subsequent idle heartbeats were
recorded. The independent camera helper still has no serial access; the
orchestrator manages the serial connection separately.

In the five inspected frames, the LED lenses show off/off, on/off, off/on,
on/on and off/off, and the OLED labels read DARK, RED, GREEN, BOTH and DARK END.
The final frame reads COMPLETE with LEDs off. This is **agent inspection of
saved camera frames**, with the specification available to the reader. It is
not a blinded OLED reading, calibrated LED extraction, continuous transition
verification, or a full automatic physical pass.

Installation is recorded in
`runs/bringup/led-oled-install-macbook-2026-10-30.json`. Copies of the installed
binary segments are under `runs/firmware/led-oled-installed-2026-10-30/`.
All 20 host unit tests pass; those tests use no physical camera or serial I/O.

## Repeat without reflashing

Keep the phone fixed in the accepted framing. Refresh camera/serial discovery
on the actual host; do not silently use a built-in camera or historical port.
Then select their exact IDs:

```sh
PYTHONPATH=src .venv/bin/python -m sparkbench camera list
.venv/bin/python -m serial.tools.list_ports --verbose
PYTHONPATH=src .venv/bin/python -m sparkbench.led_oled --port '/dev/cu.usbserial-0001' --device-id '618E8741-BCAC-4C8E-AB5E-897800000001'
```

The orchestrator requires a CP2102 10C4:EA60 at the selected path, creates a
new output directory, settles startup, checks firmware identity, and starts
the camera before sending `VISUAL`. It never uploads firmware. A camera or
identity failure before the start gate sends no `VISUAL`. Errors after identity
verification attempt `STOP`. Partial evidence remains marked incomplete.
Run outside the file sandbox when the sandbox denies camera/device access;
denied/empty sandbox enumeration does not establish host unavailability.

Compile only, if needed (no upload):

```sh
PLATFORMIO_CORE_DIR="$PWD/.platformio" .venv/bin/pio run --project-dir firmware/led_oled_test --environment classic-led-oled-test
```

## Current automatic verifier

See [Meta-backed verification](meta-verification.md). Meta API access now works;
the selected text reader is Meta Contributor only. The new capture under
`runs/led-oled/20261030T061710.065777Z/` contains 105 frames. All 47 selected
settled LED/OLED measurements pass with no unknowns or retries, using reader
settings frozen before capture. Earlier incomplete reports remain unchanged.
Local-OCR experiments are historical and are not a fallback. All 36 host tests pass.

## Remaining verification work

Camera host uptime and UART monotonic receipt time share the host time basis
in the recorded run. Retain sample PTS: receipt time is not exposure time.
The implemented verifier excludes transition windows, measures LEDs against a
frozen dark/lit calibration, and sends actual OLED label crops to Meta without
the expected answer. Deterministic label-margin trimming resolved the development
cases, and the frozen reader then passed a separate fresh capture. Keep future
uncertain readings null; the sampled result does not establish continuous behavior.

The existing full `verify` command still requires measured servo angles.
An LED/OLED-only result cannot establish overall Behavior A or B success.
Servo bracket/calibration, continuous visual extraction, discovery, protected
runtime, generated firmware and Meta API integration remain pending.
