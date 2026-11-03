# Full-rig preparation and joint-session checklist

Prepared 3 November 2026. This is a separate candidate path. The existing
LED/OLED runtime, generator, calibrated reader and historical results remain
intact. None of the new full-rig artifacts has been installed or physically
qualified. The user subsequently authorized restoring the previously verified
LED/OLED-only runtime while awaiting measuring tools; that restoration and new
fixed-view LED/OLED checks pass under runs/live/led-oled-resume-2026-11-03-v1/.
The guarded diagnostic is preserved as the previous application. Servo supply
stays off. Five operator-withheld choices, the physical LED-swap negative,
restored LED control and latest-view45sample LED/OLED check are complete with
retained failures; actual angle calibration and full-rig acceptance remain pending.


## Six-hour critical path - latest priority

LED work is closed. Target21:50Dhaka on3November2026 from the new six-hour
request; plan recorded under runs/software/six-hour-finish-2026-11-03-v1/.
Purchased protractor/ruler arrival is unknown, and a printed protractor is unavailable.
Current within-session static tracking is recorded in
`runs/servo-reference/current-view-exposure-2026-11-03-v2/report.md`; it does not
qualify cross-session geometry, physical angles or motion. Any independent angular
reference must meet alignment, legibility and validation requirements. Absolute ruler scale is not itself needed
to measure angles. Confirm reference aspect/plane and zero without substituting
a pulse command for an angle observation.

First30minutes: stabilize peripherals/cable slack and finalize one view/reference.
Byhour2: independent angle calibration and safe required range must pass.
Hours2-3: MetaContributor A/B generation, compile, verified application install.
Hours3-4.5: integrated A/B camera acceptance. Hours4.5-5: servo-runtime shutdown
qualification. Finalhour: essential fixes, regression, demonstration and package.
Batch physical instructions and authorize exact bounded movements only once
concrete/reviewable. No new features or routine LED-only reruns. Missing physical
measurements still leave full acceptance incomplete; report the exact blocker
at the hour2checkpoint rather than silently consuming the remaining window.

## Software prepared independently

- `sparkbench.fullrig`: restricted Meta behavior generation and trusted rendering/
  compilation. The model supplies target angles, LED states and labels only.
  A local measured calibration supplies pulses; the model cannot choose pins,
  pulse widths, dwell, source code or paths. Repair is bounded to 0-2 attempts;
  service/auth/rate errors do not retry. Meta is the sole provider.
- `sparkbench.servo_calibration`: independent protractor/image qualification and
  measured pulse interpolation, with no extrapolation. Physical records require
  image hashes and accepted automatic tracker evidence. The pending record has
  no physical measurements or confirmed zero/plane.
- `firmware/full_runtime`: classic ESP32, GPIO25/26 LEDs, GPIO27 servo, existing
  SH1106 profile at SDA21/SCL22/0x3C. Outputs off at boot; no initial centering.
  Fixed compiled tables, 3 s dwell, 1500 ms lease, 30 s deadline, 50 Hz PWM,
  bounded input work, driver-fault latch, late-PING rejection and one sequence
  per boot. `RUN`, generic PULSE/HOLD, malformed and oversized commands reject.
- `sparkbench.fullrig_install`: application-only write at 0x10000, previous
  application and boot-layout verification, post-write application/boot checks,
  rollback on failure. Requires explicit external-servo-power-off confirmation.
- `sparkbench.fullrig_capture`: exact artifact/profile identity, two fresh idle
  heartbeats, fresh CP2102/camera enumeration, three fresh image samples, one
  start, bounded serial writes, keepalive, stale-camera abort and acknowledged
  cleanup STOP. Camera freshness is not live visual/mount verification.
- `sparkbench.fullrig_verify` and `sparkbench.fullrig_workflow`: join independent
  automatic image angles, LED pixels and Meta-read text on the same images.
  Keep the existing 0.65/0.45 s settling guards, five-sample minimum and 0.65 s
  maximum gap. Missing/rejected angle, coverage or tracker controls skip paid text reading.
  Every required sample must be measured. No averaging, interpolation or
  expected-value substitution can hide an unknown.
- `sparkbench.fullrig_discovery`: camera-only GPIO25/26 mapping and separate
  servo-free LED comparison. OLED bus and servo signal stay fixed; they are
  not automatically discovered by this implementation.
- `sparkbench.fullrig_shutdown`: separate STOP/lease camera checks for energized
  and off LEDs plus two seconds of sampled post-shutdown angle stability. Uses
  no text requests and makes no electrical PWM-off claim.

All live commands remain explicit. Importing or compiling does not access the
board/camera. Synthetic behavior artifacts compile with `kEnabled=false` and
are rejected by the hardware loader. The default calibration artifact contains
only the historical 1500/1300/1700/1500 us sequence, now with 3 s dwells; that
dwell difference is explicit and does not inherit past motion authorization.

## Acceptance and calibration gates

Original expectations remain in `specs/behavior_a.json` (45,60,75,90,105,120,135)
and `specs/behavior_b.json` (135,90,45), each with 6-degree tolerance. An angle
label or 1500 us command never establishes the measured horn direction.

Calibration requires a fixed physical zero baseline and confirmed horn-plane
geometry, a stated independent reading uncertainty greater than zero and no
larger than 1.5 degrees, at least three separated fit angles, and three different
held-out image observations covering both endpoints and midpoint. Camera error
plus reading uncertainty and held-out pulse/angle repeatability must each fit a
3-degree budget. This is empirical qualification for the view/range, not an
authenticated metrology certificate or a universal confidence bound.

For final behavior comparison, the 3-degree measurement budget must fit inside
the original 6-degree tolerance. A reading whose budget overlaps the tolerance
boundary is incomplete; a reading clearly outside fails. The calibrated range
should include margin around 45 and 135 degrees; observations outside the
validated range remain unknown.

The initial 1300-1700 us range has not demonstrated 45-135 degrees. A wider
envelope requires separately agreed bounded diagnostic steps and clearance
checks. The software's absolute 500-2500 us rejection limits are not evidence
that this servo can safely use those endpoints. No automatic range expansion,
reboot, repeat or installation is authorized by this document.

## Joint session: physical steps for the user

1. Leave servo supply off. Have the printable angular reference ready at 100%
   scale. We will agree its placement before moving paper, phone or mount.
   The paper must stay flat, with a confirmed parallel horn plane and a fixed
   zero direction relative to the case. The horn may be at a different height.
   Its shaft axis must align with the protractor centre without reading parallax.
   Do not rotate the horn by hand or obstruct its travel.
2. Check the centre screw, mount, wire slack and clearance while unpowered.
   Frame the entire horn/case, reference, both LED lenses and OLED. If framing
   changes, initialize a fresh reference/ROI covering the needed travel, then
   freeze it before calibration/evaluation. The old static ROI is not proof it
   covers all future orientations. Preserve old failures; do not tune on the
   final acceptance capture.
3. Agree one bounded calibration sequence explicitly. I enumerate devices,
   verify/install the agreed candidate if needed, capture and analyze. You
   connect/disconnect external servo power as directed, watch for shifting or
   binding, and give independent scale readings at the specified poses.
4. Freeze the fit/geometry before the separate validation observations. If the
   same safe range is too narrow, stop and agree the next small extension; no
   blind jump to nominal SG90 endpoints. If physical reference accuracy cannot
   meet the gate, calibrated acceptance stays incomplete.
5. With servo supply off, obtain fresh LED/OLED calibration at the final fixed
   camera view. I use the existing pixel reader and Meta-only text policy;
   camera moves do not inherit the old calibration.
6. Conduct the five blind LED mappings. With power disconnected, you privately
   choose which LED signal goes to GPIO25 versus GPIO26, keeping each resistor,
   power, ground, OLED and servo wiring intact. I run/freeze camera inference
   before you reveal the map. Only these two signal assignments change. Each
   new one-shot sequence requires an explicit planned reset; no retry loop.
7. Generate/build/install the normal behaviors from the observed LED mapping
   and qualified physical calibration. Run A and B with camera capture under
   fresh explicit motion authorization. I perform all software operations.
8. Check the physical LED-swap negative using `LEDS`, with servo supply off,
   then restore/reveal wiring. Separately authorize STOP/withheld-keepalive
   trials. UART PWM-off acknowledgements are command/driver reports; camera
   LED shutdown and visible motion are separate evidence, not electrical PWM
   waveform measurements. Disconnect servo power after the powered session.

## Prepared command sequence (operator reference)

Use fresh IDs and NEW output directories. Paths below in uppercase are parameters,
not existing qualified artifacts. These commands are not a request for the user
to execute them now. `--execute-sequence` and `--servo-power-off` reflect actual
operator decisions; do not set them merely because they appear here.

```sh
# Offline: create pending record. Fill geometry/zero/uncertainty jointly later.
.venv/bin/python -m sparkbench.servo_calibration template \
  --tracker TRACKER.json --output NEW-PENDING.json

# Offline: fixed diagnostic build, no upload. Default envelope stays 1300-1700.
.venv/bin/python -m sparkbench.fullrig calibration-build --output NEW-ARTIFACT

# Only after an agreed installation, with external servo supply disconnected:
.venv/bin/python -m sparkbench.fullrig_install \
  --artifact ARTIFACT --port FRESH_PORT \
  --previous-application RECORDED_CURRENT_APPLICATION.bin \
  --previous-sha256 RECORDED_CURRENT_SHA256 --servo-power-off --output NEW-INSTALL

# Only after explicit authorization for the compiled fixed sequence:
.venv/bin/python -m sparkbench.fullrig_capture \
  --artifact ARTIFACT --port FRESH_PORT --device-id EXACT_IPHONE_ID \
  --execute-sequence --output NEW-CAPTURE

# Track that saved capture with the frozen view/settings, then attach readings:
.venv/bin/python -m sparkbench.servo_tracking --config SAVED-CAPTURE-TRACKER.json \
  --output NEW-TRACKING
.venv/bin/python -m sparkbench.servo_calibration add-observation \
  --record CALIBRATION.json --trace NEW-TRACKING/trace.jsonl --file FRAME.jpg \
  --role fit --pulse-us OBSERVED_COMMAND --reference-angle-deg INDEPENDENT_READING \
  --output NEXT-CALIBRATION.json
.venv/bin/python -m sparkbench.servo_calibration check \
  --record COMPLETED-CALIBRATION.json --output NEW-QUALIFICATION.json

# Meta request occurs here, only after calibration/range checks pass:
.venv/bin/python -m sparkbench.fullrig generate \
  --spec specs/behavior_a.json --mapping DISCOVERY/discovery.json \
  --calibration COMPLETED-CALIBRATION.json --output NEW-GENERATION-A

# Install separately, then authorize one integrated live sequence:
.venv/bin/python -m sparkbench.fullrig_workflow \
  --artifact GENERATED-ARTIFACT --tracker TRACKER.json --policy READER-POLICY.json \
  --spec specs/behavior_a.json --port FRESH_PORT --device-id EXACT_IPHONE_ID \
  --execute-sequence --output NEW-BEHAVIOR-A

# Discovery and negative LED checks do not actuate servo:
.venv/bin/python -m sparkbench.fullrig_capture \
  --artifact ARTIFACT --port FRESH_PORT --device-id EXACT_IPHONE_ID \
  --action DISCOVER --execute-sequence --output NEW-PROBE
.venv/bin/python -m sparkbench.fullrig_discovery \
  --run NEW-PROBE --artifact ARTIFACT --policy READER-POLICY.json --output NEW-MAPPING
# For the physical negative: use --action LEDS with the behavior artifact,
# then fullrig_discovery with --spec specs/behavior_a.json to compare LED states.
# For deliberate shutdown acquisition: fullrig_capture --fault stop or --fault lease.
# Analyze it with fullrig_shutdown --run CAPTURE --artifact ARTIFACT --tracker TRACKER.json
#   --policy READER-POLICY.json --spec specs/behavior_a.json --output NEW-QUALIFICATION
```

The unchanged old `sparkbench workflow` and installer still expect their old
LED/OLED artifact type. Never pass new full-runtime artifacts to those commands.
New modules have explicit `python -m sparkbench.MODULE --help` entry points.

## Completion report

Record A, B, independent calibration, each physical negative, shutdown scopes,
and the five blind mappings separately. Missing required measurements remain
incomplete. Software tests, mock Meta responses, compile-only artifacts, UART
and user observations never count as automatic physical camera acceptance.
Retain initial dependency/build failures alongside corrected results. Package
source, commands, hashes, selected demonstration frames and recovery image
locations; omit credentials and label all synthetic fixtures explicitly.
