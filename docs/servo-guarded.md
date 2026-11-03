# Fixed servo diagnostic

## First explicitly authorized trial

The user explicitly authorized one fixed test. Fresh CP2102 and exact iPhone
selection, exact guarded idle identity and camera freshness gates completed.
One SERVO_TEST requested1500,1300,1700,1500us at50Hz with2s per step. UART reports
all four steps and COMPLETE/PWM:OFF, then acknowledges cleanup STOP/PWM:OFF.
No RUN, arbitrary pulses, automatic retries, firmware upload or Meta calls.
Camera capture saved131real frames. UART is not waveform or angle measurement.

Agent inspection of frames7,16,26,35 shows changed horn direction at the offset
phases and return near the initial visible pose. These samples were selected
approximately0.8s after UART receipt, not by measured settling latency. This is
agent review of real images, not automatic camera verification. No gross case
shift is apparent in these selected frames; loaded mount stability is unmeasured.

The frozen automatic tracker localizes0/131frames. All three frames saved before
the start command also reject registration; mismatch was present before movement.
All points/previews remain null. This does not establish a movement-induced
tracking fault or prove its physical cause. No limits relaxed, no reference
retuning on this run and no powered retry. Full Behavior A/B and actual angle
verification remain incomplete. Generic metadata from the offline static tracking
tool does not qualify the moving sequence.

User subsequently reports: "Servo power off; no shifting or persistent buzzing
noticed". This operator report is separate from camera/UART evidence. The guarded
diagnostic remains installed, now idle by UART; no further actuation authorized.
OLED may retain previous LED/OLED text because guarded firmware neither initializes
nor clears that display; retained text is not firmware identity evidence.

No source changes or repeated tests in this hardware/data-only trial; last117host
tests passed. Saved raw UART, timestamps, camera frames, frozen reference/source,
incomplete automatic analysis, operator report and assessment remain available.
Next investigate current-view registration/moving tracking offline while servo
power stays off. No automatic repeat. LED/OLED restoration file remains preserved.

Evidence: runs/servo-motion/guarded-fixed-2026-11-02-v1/report.md and assessment.json.
Earlier records below retain their historical firmware/view/authorization scope.

`firmware/servo_guarded` compiles for the classic ESP32 with the cached local
toolchain. It was installed on 2 November with explicit user authorization.
The application and unchanged boot layout were flash-verified; only `ID` was sent
to verify exact idle/PWM-off/available identity and fresh heartbeats. The working
LED/OLED application is saved for restoration. Actuation remains outside the
installation authorization; keep the external servo supply unplugged.
See `runs/firmware/servo-guarded-installed-2026-11-02-v1/report.md`.
The earlier compile-only preparation did not open serial. The initial preparation predated the bracket. On 2 November the
user fitted the servo to its flat acrylic plate and accepted a temporary taped
table-edge mounting, reporting it stable while unpowered. Powered/load stability
is unverified. The fixed phone view passed a scoped sixty-second static check;
this does not qualify moving-servo tracking or measured angles.

The current readiness review is in
`runs/servo-prep/readiness-2026-11-02-v1/review.json`. It confirms unchanged
prepared source/binary hashes, matching bootloader/partition layout and an intact
local LED/OLED restoration application. This is local file verification, not a
new flash readback. The user confirms the centre screw is fitted, swing clearance
checked, and the same separate nominal 5 V / 2 A supply/common-ground/GPIO27 wiring
is unchanged. These are user reports; supply voltage/polarity remain unmeasured.
The bounded host runner below is now prepared and tested offline. Installation is now complete; powered movement still requires explicit authorization.

This separate diagnostic holds GPIO25/26 off and does not initialize the OLED.
GPIO27 starts LOW with no PWM attached. Only an explicit `SERVO_TEST` would start
the fixed historical sequence: 1500, 1300, 1700, 1500 microseconds at 50 Hz, with
two seconds per step. There is no arbitrary pulse/hold interface, generated
servo program. `RUN`, `CENTER` and `TEST` are rejected.

The sequence is available once per boot, including aborted attempts. `STOP`,
a 1500 ms keepalive lease and a separate 10000 ms maximum deadline stop the
sequence, request zero duty, detach PWM and drive the signal LOW. A late `PING`
cannot revive an expired lease. Parser work is bounded per loop. Driver errors
latch a fault and prevent another start; telemetry reports FAULT rather than
claiming PWM is off after a failed driver operation. These are software controls,
not an independent electrical cutoff or a guarantee under hardware failure.

The actual source is exercised with fake GPIO/PWM/serial in
`tests/native_servo/servo_guarded_test.cpp`: boot without PWM, command rejection,
fixed duty sequence, STOP, lease expiry, late keepalive, serial flooding, driver
faults, single-use latch, deadline and timer rollover. These tests and the ESP32
build do not measure waveform, servo movement, angles or physical shutdown.

Build-only command (no upload):

```sh
PLATFORMIO_CORE_DIR="$PWD/.platformio" PLATFORMIO_SETTING_ENABLE_TELEMETRY=no \
  .venv/bin/pio run --project-dir firmware/servo_guarded \
  --environment classic-servo-guarded
```

Preparation, binary/source hashes and build/test logs are retained under
`runs/servo-prep/guarded-2026-10-30-v1/`. No Meta requests or new dependencies
were needed. Calibrated angle and full Behavior A/B verification remain incomplete.

## Bounded host runner — one authorized trial now recorded

`python -m sparkbench.servo_capture --help` documents the separate runner.
Import/help performs no hardware access. `acquire` refuses before I/O unless
`execute_fixed_sequence=True`; CLI execution additionally needs the explicit
`--execute-fixed-sequence` flag. The runner never flashes firmware, changes power
or calls a model. Do not invoke it merely to inspect a connected board.

It freshly enumerates the selected CP2102 and exact camera, validates/freeze-records
the saved view identity, then opens UART with bounded read/write timeouts. After
retaining startup it requires the exact available guarded idle identity and two
increasing idle heartbeats. The LED/OLED runtime cannot satisfy this identity.
It starts video-only capture and requires fresh timestamped image files from the
selected camera before sending `SERVO_TEST` once. This is acquisition freshness,
not a live visual tracking or mounting-quality gate.

During the fixed sequence it checks camera freshness and sends keepalive at
400 ms intervals, with a separate ten-second host deadline. Wrong/repeated steps,
unexpected dwell telemetry, firmware reset/error/fault, camera exit or stale
frames fail the run. Cleanup attempts `STOP` after any verified connection,
including failures, and requires a bounded UART STOP/PWM-off acknowledgement
for success. Serial writes do not use an unbounded flush. Partial start writes
consume the host start latch because hardware might have received them.

UART continues recording through bounded camera post-roll. The runner closes
serial and terminates/kills unfinished camera work on failure. A disconnected
host cannot guarantee STOP delivery; firmware lease/deadline are additional
software fallbacks, not an electrical cutoff. All journals and incomplete results
are retained. `captured_uart_sequence_complete_unverified` only means capture and
UART sequence completion; actual motion, waveform, angle and mount stability are
not verified. No automatic rerun/reset or installation occurs.

Ten runner tests exercise simulated serial/camera/clock paths, including normal
completion, wrong/consumed identity, stale/wrong camera, camera loss/hang, reset,
driver fault, bad pulse, deadline, STOP failure/missing acknowledgement, partial
write, buffer bounds and once-only start. The full suite passes 117 tests. These
fixtures are synthetic software evidence, not physical verification.
Sources, log and hashes: `runs/servo-prep/readiness-2026-11-02-v1/`.
