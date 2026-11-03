# SparkBench project history (October 27 – November 3, 2026)

This is the original running log that used to be the README. Newest entries are at the top of each section; later entries supersede earlier ones. The judge-facing overview now lives in [the README](../README.md). Paths under `runs/` refer to local evidence that is not committed to the repository.

---

# SparkBench

**Build with me:** describe an idea, get a supported parts list, save your inventory,
follow assembly references, and ask Meta about progress photos in the local dashboard.
An accepted project brief carries into the existing firmware planning and test workflow.
Compiled applications have source/binary downloads and a source viewer.
The desk-status project has now been compiled and installed through the dashboard;
flash bytes and its idle UART identity are confirmed. Project status and job logs
show each stage separately. This compiled version has not yet had a camera test.
[Installation evidence](../runs/software/project-installation-2026-11-03-v1/report.md).
[Build-guide walkthrough](build-guide.md). First release supports the known
ESP32 LED/OLED kit; photo advice remains distinct from measured test evidence.

**Local evidence dashboard:** run `.venv/bin/python -m sparkbench dashboard` and
open **http://127.0.0.1:8765**. Browse real pass, wiring-fault and incomplete runs,
inspect recorded frames, and compare expected/observed results. Choose **New AI proposal** to interpret an instruction through Meta Contributor
and review/save a bounded LED/OLED plan. Only explicit submissions call Meta;
browsing evidence is read-only. A reviewed plan can now be compiled, installed
as an application-only update, and tested with the explicitly selected iPhone
camera. Each stage is a separate action; results cover sampled LED/OLED windows.
[Dashboard guide](dashboard.md).
Latest dashboard checks: **222 host tests pass**. The current reviewed-plan
camera run is **incomplete** because the changed view rejects the frozen geometry;
refresh the reference before retesting. Servo angles remain unmeasured.

**Current tracking update, 3 November:** camera-only tracking localizes all 46
held-out frames after a predetermined within-session startup reference. Image
heading repeatability is 0.5°, with mechanical angles still unknown. A reference
from a different camera session remains unqualified; global defaults were not
promoted. All 155 host tests pass. See the [tracking report](../runs/servo-reference/current-view-exposure-2026-11-03-v2/report.md)
and [recorded demonstration guide](demo.md). Earlier tracking/view notes
below are historical and do not establish current calibration.

Discover supported hardware connections, generate behavior, and verify the
physical result on camera.

**Latest live update, 3 November:** LED checks are complete and original wiring
is restored. Five operator-withheld choices were confirmed across11captures,
with6incomplete captures retained; this is not5perfectfirst-attemptsuccesses.
The physical signal-swap negative is detected in47settled samples with36wrong
channel readings and0unknowns. Restored-wiring LED control passes48samples.
Latest-view full LED/OLED verification passes45samples with MetaContributoronly,
0mismatches/unknowns, frozen before fresh capture. A prior clipped-crop run remains
incomplete. Servo supply stays off; this runtime never drives GPIO27. Physical
protractor/ruler are still awaited for actual servo angles and full Behavior A/B.
[Current report](../runs/live/led-oled-resume-2026-11-03-v1/report.md).

**Earlier 3 November: independent full-rig software preparation is complete.** A separate
candidate path now supports measured servo calibration, bounded full-rig firmware,
Meta-only behavior data generation, explicit capture/installation, sampled full-rig
verification, servo-free LED checks/discovery and shutdown qualification. The
155-test suite passes; fixed calibration and disabled synthetic A/B fixtures
compile locally. These are software results, not physical full-rig acceptance.
The board/camera were untouched; the guarded diagnostic remains installed and
servo power stays off. Physical calibration, new-view LED/OLED measurements,
blind mappings and full Behavior A/B tests are still pending.
Start the joint session with [the bench checklist](full-rig.md).


Moving to the MacBook Pro? Start with [HANDOVER.txt](../HANDOVER.txt). It contains
the current state and portable setup commands. The current software workflow is
documented in [software-pipeline.md](software-pipeline.md).

Latest grid-corner reference: one fresh60-second static capture localizes
260/261frames,1startupunknown,257preview-ready and no losses after readiness.
Old wood references on the same frames localize259/261, also no losses; fresh
gain is modest. Grid corners are now the current default; all limits unchanged.
No movement/firmware/Meta calls; horn tilt and actual angles remain unverified.
[Comparison report](../runs/servo-reference/grid-corner-tracker-2026-11-03-v1/report.md).

Earlier mounted-grid view: refreshed tracker localizes37/42fresh frames,29preview-ready,
with one loss/recovery and final state tracking. Prior0/49changed-reference failure
is preserved. Same limits and patch sizes; no motion/firmware/Meta calls. Possible
horn tilt and actual angles remain unverified. Current passive default selects
this view; last121tests passed, no source change in this update.
[Refresh report](../runs/servo-reference/mounted-grid-tracker-2026-11-03-v2/report.md).

Earlier offline replay: refreshed pre-command reference and optional larger
background windows localize116/131 saved frames, including20/20samples in the
four post-command windows.15unknowns remain; original0/131 trial is preserved.
This is retrospective development, not independent verification or calibrated
angles. All120hosttests pass; no new capture/movement/firmware or Meta call.
[Replay report](../runs/servo-motion/guarded-replay-2026-11-02-v4/report.md).

Earlier guarded trial: one explicitly authorized fixed sequence completed with
UART STOP acknowledgement and131camera frames. Agent sees horn movement/return,
but frozen automatic tracking localizes0/131, rejecting all3pre-start frames.
Angles and full Behavior A/B remain incomplete. User reports servo power now off;
diagnostic remains installed, no further movement authorized.
[Trial report](../runs/servo-motion/guarded-fixed-2026-11-02-v1/report.md).

Current firmware: the separately authorized guarded servo diagnostic is now
installed and flash-verified. Exact idle/PWM-off/available identity and increasing
heartbeats verified via UART; initial idle verification used only `ID`; the subsequent one-shot trial is recorded above.
Keep the external servo supply unplugged until a separately authorized test.
The working LED/OLED restoration application is saved.
[Installation report](../runs/firmware/servo-guarded-installed-2026-11-02-v1/report.md).

Earlier60-second fixed-stand capture: **270/271 localized**, one startup unknown,
266preview-ready, no tracking losses after readiness; ended tracking. Same frozen
reference/settings as the short check, no tuning afterward. This qualifies only
the recorded static view; angles and powered mounting remain unverified. No
servo movement or firmware changes. [Report](../runs/servo-tracking/taped-fixed-long-2026-11-02-v1/report.md).

Earlier fixed-stand check: after the user secured the phone stand, a new tabletop
reference localizes51/53 fresh frames,2startupunknown,48preview-ready and no
loss after readiness. Center Stage/Portrait are inactive in all saved samples;
read-only diagnostics are recorded per frame. All107 host tests pass. This is
a short unpowered static check; actual angles and powered mounting remain
unverified. [Current report](../runs/servo-reference/taped-fixed-2026-11-02-v1/report.md).

Earlier follow-up: a revised background patch improves saved-data localization,
but a fresh53-frame capture rejects with both old and new references after the
scene changes. Current-view registration remains incomplete; keep servo power
off. See [diagnosis](../runs/servo-reference/taped-registration-2026-11-02-v1/report.md).

Earlier update (2 November): the servo is attached to its plate and temporarily
taped at the table edge; stability is user-reported while unpowered. Current
tracking uses explicit image-only geometry because the grid is obscured. A fresh
static capture localizes35/40frames, with25preview-ready, two losses and an end
state of recovering; sustained tracking remains incomplete. All107 host tests
pass. No actuation or firmware changes occurred; actual angles stay unverified.
See [current-view tracking](servo-tracking.md#current-taped-mount--2-november-2026).
The earlier view-specific results below retain their historical scope.

Earlier passive servo work established an image-space body reference and a provisional
printed-square perspective preview. The user confirms flat parallel placement;
the 100% print remains unmeasured. Metric calibration and actual shaft angles
remain unverified. Preview values are excluded from verification and do not
authorize servo movement. See the [printed-grid reference](servo-geometry.md#printed-grid--provisional-reference).
Automatic passive hub/horn localization and timestamped traces are also available;
see [servo tracking](servo-tracking.md). Moving-servo qualification remains pending.
The corrected passive camera view now shows the full case/horn and card.
A fixed guarded servo diagnostic is
[installed and verified idle](servo-guarded.md); powered testing remains pending.
The current optional matcher uses larger case patches and subpixel matching,
previously initialized to the final printed-grid view. After code/settings freeze, its
fresh 60-second static check localizes **265/267 frames**, retaining two startup
unknowns; 262 frames are readiness-qualified with no loss after readiness.
A separate short check localizes 39/41. These results belong to that recorded
view; a later framing change required a new reference for the physical test below.
Rejection limits are unchanged. This is
static pixel localization for this view; calibrated
angles, moving-servo qualification and continuous verification remain incomplete.
That stage passed all 105 host tests, including native fractional-shift and provenance checks;
eight digital negative controls reject. See the
[recorded tracking notes](servo-tracking.md#earlier-final-grid-view--independent-static-checks).
The latest real card-obstruction check, using a refreshed fixed reference,
records clear-before 16/18 localized, covered 0/7, and clear-after 11/13 with
eight preview-ready frames. This qualifies broad scene obstruction and return
to readiness; isolated horn-only rejection and exact recovery timing remain
unmeasured. See the [physical test](servo-tracking.md#physical-scene-obstruction--latest-check).
`sparkbench passive` now combines explicit-camera capture, frozen tracking and
post-capture startup/loss/recovery reporting in one camera-only command. It keeps
every raw frame and unknown. Its earlier 60-second session saved 267 frames:
112 localized, 155 unknown, 83 readiness-qualified. It ended lost, exposing
longer-term registration instability in that earlier view; that failure remains
preserved alongside the new final-view result above. See the
[session workflow and result](servo-tracking.md#camera-only-session-command-and-readiness-reporting).
See [servo geometry](servo-geometry.md). The phone has been repositioned;
revalidate the stored LED/OLED calibration before new camera measurements.

## Current hardware — October 30, 2026

**Current live milestone:** all four LED/OLED stages pass: integrated capture,
runtime qualification, camera-based GPIO25/26 discovery, and Contributor
generation → compilation → hash-verified installation → camera verification.
The installed image is now the trusted runtime with a generated green-first
data table. All 47 final settled samples match; servo angles remain null and
full Behavior A/B remains incomplete. See [live validation](live-validation.md)
for commands, recovery images, calibration changes and retained incomplete runs.

The new 38-pin USB-C board is an ESP32-D0WD-V3 revision v3.1 with 4 MB flash,
identified on the originating Mac using esptool through its CP2102 bridge.
Fresh MacBook Pro enumeration on October 30 independently found
`/dev/cu.usbserial-0001` (VID:PID 10C4:EA60, USB serial 0001, location 1-1).
Camera-only setup did not open serial; the authorized LED/OLED test now records
UART separately. Use classic-ESP32 build profiles; the installed image
is tracked in `hardware/board.json`. The carrier boots correctly. The original S3 record is
preserved in `hardware/boards/original-esp32s3.json`.

Individual peripheral checks passed: red GPIO25 and green GPIO26 blink patterns
were manually observed; the OLED at I2C 0x3C on SDA21/SCL22 renders the expected
text and border with the SH1106 128x64 profile; the SG90 on GPIO27 moved both ways
and returned by user observation. Servo commands tested were 1300–1700 us at
50 Hz. Exact shaft angles, supply voltage and cable polarity remain unmeasured.
The OLED's exact controller identity is unconfirmed. See `hardware/rig.pending.json`
and the captures under `runs/bringup/` for scope and evidence.

The earlier image was `firmware/led_oled_test`, deliberately uploaded on
October 30 for LED/OLED-only testing with hash verification. It boots with LEDs
off, accepts `VISUAL`, and performs five bounded steps without any servo GPIO
writes or PWM calls. A 25-second iPhone capture saved 110 frames with UART
receipt timestamps. Agent inspection of one settled frame per step shows the
expected LEDs and OLED labels, followed by COMPLETE and LEDs off. Evidence:
`runs/led-oled/20261030T043224.829848Z/run.json` and `visual_review.json`.
This is a saved-frame review, not continuous or deterministic automatic visual
verification. Servo angle measurements and overall Behavior A/B verification
remain incomplete. See [the diagnostic workflow](led-oled-only.md).

`firmware/rig_test` is the previous hand-written combined test. Its upload was
hash-verified, and six idle heartbeats plus OLED I2C ACK passed. It waits for `RUN`,
executes four steps with a two-second dwell plus display-update time, then turns
LEDs and servo pulses off. The first combined serial sequence passed with 2123 ms
between reported steps, completion, and return to idle. The user confirmed that
LEDs, servo movement and OLED labels all matched during the requested replay
(`runs/bringup/rig-combined-replay-2026-10-30-01.json`). This is manual physical
verification. At that earlier stage video evidence, automatic camera verification
and discovery were pending; the current scoped camera result is below.

Its full original 4 MB flash was backed up before upload. The serial-only image
was uploaded with hash verification and produced 11 increasing heartbeat ticks
with 1000 ms spacing. Capture:
`runs/bringup/heartbeat-classic-2026-10-29-settled.json`. Opening this UART bridge
produced a reset and duplicated startup bytes; these are retained separately
from the heartbeat measurement series. Use 115200 baud: the first 460800-baud
backup attempt encountered serial corruption.

## Original S3 bring-up — October 27, 2026

The previously connected ESP32-S3 has 16 MB quad flash and 8 MB PSRAM, identified using
esptool. Native USB Serial/JTAG is working. The serial heartbeat firmware has
been compiled, flashed with hash verification, and checked over live serial:
nine heartbeat messages, with 1000 ms between each pair. The original full flash
is backed up locally. Exact carrier board and external pin assignments remain
unconfirmed; PSRAM is not enabled or tested by this bring-up image.

The original S3 check did not test peripherals. The trace evaluator still uses
supplied measurements. Current LED/OLED camera extraction and Meta interpretation
are separate from that original S3 bring-up evidence.

## iPhone camera acquisition — October 30, 2026

The selected camera is the spare **iPhone 15**, using a USB data cable and native
Continuity Camera on the **MacBook Pro**. The user reports that this works there
without extra camera software. SparkBench has now saved real local frames from
its explicitly selected Continuity Camera device on this Mac.
Use a rigid overhead phone clamp, turn off
video effects/automatic reframing, and frame the two LEDs and OLED clearly.
Leave servo actuation/angle verification until a proper mount is available.
The acquisition tool never opens serial ports, flashes firmware, or sends `RUN`.

On the originating Mac, the native helper compiled and video permission was
granted, but no rear-camera device appeared; QuickTime showed the phone screen
and FaceTime did not list the iPhone. Those observations are historical and do
not describe the MacBook Pro. They are preserved in `hardware/camera.json` along
with the latest user report. Camo was researched but not installed; the selected
route on the MacBook Pro is native Continuity Camera.

The fresh Python 3.11.13/OpenSSL environment passes all 36 offline tests, and
the native helper was rebuilt locally with Apple Swift 6.2.1. Sandboxed discovery
returned denied/empty; the host check returned authorized and listed the iPhone
and built-in FaceTime camera. The selected iPhone ID is
`618E8741-BCAC-4C8E-AB5E-897800000001`; the built-in camera was not selected.
Re-enumerate if the camera changes. Permissions, device IDs, virtual environments
and compiled binaries do not transfer between Macs.

Initial camera-only samples and readability reviews are under `runs/camera/`;
failed framing attempts are retained. The final framing check,
`20261030T042732.737364Z`, shows both complete LED lenses and readable OLED text
with its full border. The subsequent recorded test is under `runs/led-oled/`.
Current capture and review pointers are in `hardware/camera.json`. Acquisition
and agent inspection of still frames do not establish automatic physical
behavior verification. Initial host setup is recorded in
`runs/host/macbook-pro-2026-10-30.json`.

The LED/OLED expected sequence remains independent in `specs/led_oled_only.json`;
its measurements are null. Full behavior verification still requires measured
servo angles; the evaluator has not been weakened.

The [Meta-backed verifier](meta-verification.md) now has an independent
**LED/OLED-only pass**. The latest fresh capture has 105 frames; all 47 selected
settled samples match both LED states and OLED labels with no unknowns or retries.
Reader settings were frozen before capture. Meta Contributor alone reads the
text; local processing only aligns/crops images, trims empty label margins and
measures LED pixels. No alternate OCR provider is used. Earlier incomplete
reports and null readings remain unchanged. Wrong expectations fail in derived
software controls, and missing readings remain incomplete; these controls are
not physical fault injection. Full-rig verification still lacks servo measurements.

The native macOS AVFoundation backend discovers Continuity Camera explicitly.
It needs Apple's Command Line Tools to compile once; OpenCV is not required.
The helper includes the camera usage description and Continuity Camera opt-in.
`doctor` stays read-only and never requests permission or opens a camera.

```sh
# Enumerate only; this may be empty before camera permission is granted.
PYTHONPATH=src .venv/bin/python -m sparkbench camera list

# Ask macOS for video permission; no recording. Accept the native prompt.
PYTHONPATH=src .venv/bin/python -m sparkbench camera authorize
PYTHONPATH=src .venv/bin/python -m sparkbench camera list

# Replace CAMERA_ID with the exact iPhone ID shown by list.
PYTHONPATH=src .venv/bin/python -m sparkbench camera capture \
  --device-id 'CAMERA_ID' --seconds 10 --fps 5
```

If the iPhone is connected by USB but absent from the camera list, unlock it to
accept Trust, then lock it again. Check the same Apple Account, Wi-Fi/Bluetooth
and Continuity Camera settings. QuickTime Player > File > New Movie Recording >
camera menu is an independent availability check **only if its preview actually
shows the rear-camera view**. A source showing the phone screen is not suitable.
Close the preview before SparkBench capture. The Mac's USB inventory alone does not prove that Continuity
Camera is ready. On macOS 26, USB inventory is `SPUSBHostDataType`.

Select the device explicitly: a missing/disconnected iPhone does not silently
fall back to the Mac's built-in camera. If macOS denies camera access, allow the
launching app in System Settings > Privacy & Security > Camera and retry.
Sandboxed runners may need to run camera commands outside their file sandbox;
an empty device list alone does not establish that the iPhone is disconnected.

Each capture uses a new directory under `runs/camera/` (or a new `--output`
directory), containing local JPEG samples, `frames.jsonl` with frame sizes,
sample-buffer presentation timestamps and host timestamps, and `capture.json`.
Capture is bounded to 1–60 seconds and samples 1–10 frames/second. It does not
record audio or upload images. Interruptions can leave a partial capture marked
`recording`; only a completed report describes the finished acquisition.
Acquisition success means images were saved, **not** that physical behavior
passed. The separate LED/OLED orchestrator now retains UART receipt timestamps
alongside camera PTS. Quantitative LED extraction and Meta reading without
expected labels are implemented, with the scoped LED/OLED pass described above.
The existing `verify` command still rejects missing
measurements; camera acquisition does not bypass it.

API references: [Continuity Camera](https://developer.apple.com/documentation/avfoundation/avcapturedevice/devicetype-swift.struct/continuitycamera)
and [video sample buffers](https://developer.apple.com/documentation/avfoundation/avcapturevideodataoutput).

## Start now

The [Day-1 checklist](day1.md) and
[pending rig configuration](../hardware/rig.pending.json) reflect the separate
5 mm LEDs with 330 ohm resistors and the manually established pin map.
The original S3 record is historical.
A classic-ESP32 serial-only build is available alongside the S3 build.
Peripheral diagnostics are implemented. The bounded LED/OLED runtime is
installed and has scoped camera, STOP and keepalive-timeout qualification.
Meta Contributor generation, bounded plan repair,
camera discovery logic and an integrated test command are now implemented; see
[the workflow, trust boundary and qualification limits](software-pipeline.md).

1. On a new Mac, follow `HANDOVER.txt`; local setup does not upload firmware.
2. Run offline tests and use `hardware/board.json` for the active classic ESP32.
   The original S3 record is historical. Re-enumerate serial ports after transfer.
3. On a new host authorize and enumerate the iPhone 15 before selecting it.
   This Mac already has a calibrated, scoped LED/OLED camera pass.
4. Keep servo testing deferred until its proper bracket is available. The
   current generated runtime has a 47-sample automatic LED/OLED pass. Use its
   explicit artifact and specification arguments in the live-validation guide.
   The historical combined diagnostic's
   `RUN` command drives the servo; never use it during this stage.
5. Use `sparkbench workflow` for integrated LED/OLED capture/Meta verification,
   or `sparkbench replay` for offline regression. One scoped real discovery and
   generated-behavior cycle passed. Physical LED-swap negative test, blind wiring
   and full Behavior A/B acceptance remain pending.

## Offline commands

These commands run with Python 3.9+ and no third-party dependencies:

```sh
PYTHONPATH=src python3 -m sparkbench doctor
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m sparkbench verify \
  --spec specs/behavior_a.json --trace examples/synthetic_behavior_a.json
```

The example is explicitly **synthetic**. A pass validates the assertion engine
on that fixture; it is not evidence that a physical rig works. Missing readings
cannot produce a passing result. Trace provenance is reported, not authenticated.
OLED text is supplied by the separate Meta reader; this evaluator only
compares that reading against the expected text.

For a local toolchain, use Python 3.11+ with OpenSSL, create `.venv`, and install
PlatformIO there. This avoids the old LibreSSL backend of the system Python on
this Mac. Use a project-local PlatformIO core directory for downloaded tools:

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
PLATFORMIO_CORE_DIR="$PWD/.platformio" .venv/bin/pio device list
```

## Repeat the board bring-up check

```sh
PLATFORMIO_CORE_DIR="$PWD/.platformio" .venv/bin/pio run --project-dir firmware/bringup --environment classic-uart
.venv/bin/python tools/check_heartbeat.py --port /dev/cu.usbserial-0001 --connection uart --seconds 8 --output runs/bringup/heartbeat-classic-latest.json
```

The original S3 capture is `runs/bringup/heartbeat.json`; the command above uses a
separate capture for the new classic board. The check passes after at least three
heartbeats with increasing uptime and approximately one-second spacing. This
confirms firmware execution and USB output, not physical behavior verification.

Original flash backup: `runs/backups/esp32s3-before-bringup-2026-10-27.bin`.
Its size (16,777,216 bytes) and SHA-256 are recorded in
`runs/backups/manifest.json`. Backups and captures are ignored by version control.

The new classic ESP32's 4,194,304-byte backup is
`runs/backups/esp32-classic-before-bringup-2026-10-29.bin`, with size and SHA-256
in `runs/backups/manifest-esp32-classic-2026-10-29.json`.

## Minimum parts to obtain

| Part | Quantity | Purpose |
| --- | --- | --- |
| USB data cable matching the board | 1 | Programming and UART |
| Breadboard and male/male + male/female jumper wires | 1 set | Repeatable connections |
| Red and green 5 mm LEDs | 2 of each | Indicator tests plus spares |
| 330 ohm resistors | 4 | One series resistor per LED |
| SG90 positional servo with horn and screw | 1 | Observable movement; check its actual range; select positional rather than continuous rotation |
| Regulated 5 V supply rated at least 2 A, with suitable breakout/connector | 1 | Servo power; share ground with ESP32 |
| 128x64 four-pin I2C OLED, 3.3 V compatible, with identified controller (SSD1306 or SH1106) | 1 | Visible state independent of UART |
| iPhone 15, USB data cable and rigid overhead phone mount | 1 set | Selected camera via Continuity Camera; UVC webcam is an alternative |
| Stiff pointer, paper protractor, colored markers, tape/base | 1 set | Angle measurement and fixed geometry |

Use pre-soldered headers if soldering equipment is unavailable. Confirm the
actual module pin labels before wiring. The servo needs its own suitable 5 V
rail; do not power it from the ESP32 3.3 V pin. A spare servo is useful after the
first working run. An expansion shield is optional and must match the board.

Example local listings checked October 27 (confirm exact variant and availability):
[180-degree MG90S](https://www.engineeringelectronics.com.bd/home/105-mg90s-metal-gear-servo-motor-180.html)
and [SSD1306 I2C OLED](https://techshopbd.com/product/oled-display-blue-i2c-128x64-096-inch/).

## ESP32-S3 board identification

This section applies to the original S3 only, not the active classic ESP32 board.

Original board details are stored in `hardware/boards/original-esp32s3.json`. Read the full module
marking, including a suffix such as N8R8, and the development board name. On
boards with separate USB and UART sockets, identify which socket is connected.
Native USB and a USB-to-UART bridge need different serial-output configuration.

The original plan's classic-ESP32 pin assignments must be replaced. The S3 has
GPIO0–21 and GPIO26–48: GPIO22 and GPIO25 do not exist. GPIO26–32 are normally
reserved for memory; some memory variants also reserve GPIO33–37. GPIO19/20
serve native USB. Pin assignments will be validated against the actual board
before the rig is wired.

References: [S3 GPIO restrictions](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/gpio.html),
[USB CDC setup](https://docs.espressif.com/projects/arduino-esp32/en/latest/tutorials/cdc_dfu_flash.html).

## Milestones and acceptance

- **Bring-up:** board identified, USB serial visible, firmware heartbeat repeats.
- **Verification foundation:** Behavior A executes and the camera measurements
  pass; an LED swap fails the LED assertions. Record raw evidence.
- **Discovery:** fixed power/ground and OLED bus; discover unknown signal maps
  among pins validated for the actual board. Preserve unknowns.
- **Day-4 gate:** one recorded discover/generate/flash/verify run plus five blind
  mappings. If discovery is unreliable, retain the working verification system.

Behavior A and B use the same per-step schema in `specs/`. The trusted runtime,
specification, and measurement engine stay outside the future generator's
write-set. A fresh targeted probe is required before attributing a newly observed
failure to wiring or generated behavior. Future API failures are classified as
access/configuration failures unless evidence establishes a geographic cause.
