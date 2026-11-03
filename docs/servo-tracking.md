# Automatic passive servo tracking

## Grid-corner current references — 3 November 2026

`hardware/servo.tracker.grid-corners.pending.json` uses all four visible reference
square corners as camera patch anchors. Mounted-grid/taped/passive-default aliases
now select it. The grid must stay fixed relative to the tabletop/servo. All patch
sizes and numerical gates remain unchanged; no anchor is omitted at runtime.

Saved development42frames:37to41localized. Fresh60-second requested session:
260/261localized,1startupunknown,257preview-ready,zero losses after readiness,
endedtracking. Same-image old wood references259/261with no losses: only one-frame
fresh gain, not evidence of universal dropout removal. Eight digital controls
reject; no physical fault injection. Source/settings froze before capture and no
tuning afterward. Current grid/horn parallelism remains unconfirmed, so actual
angles/zero and full Behavior A/B stay incomplete. No new source/firmware/servo
or model operations in this task. See the comparison report under
`runs/servo-reference/grid-corner-tracker-2026-11-03-v1/`.

## Mounted-grid current view — 3 November 2026

Current explicit configuration: `hardware/servo.tracker.mounted-grid.pending.json`;
passive default and taped alias now select this view. Preview reference is
`hardware/servo.mounted-grid.preview.json`. All patch sizes and numerical limits
match the prior larger-background candidate. Earlier static grid/taped views are
historical and their overlays do not initialize this view.

Fresh independent check:37/42localized,5unknown,29preview-ready,one loss and
recovery,endedtracking. The first0/49failed reference mismatch is preserved;
coordinates alone were refreshed before the second capture, with no post-result
tuning. Possible downward horn tilt remains unconfirmed plane relation, so no
verified horn-plane warp, measured angle or mechanical zero. Last121tests passed;
no production source or hardware/model operation changed beyond passive capture.
See `runs/servo-reference/mounted-grid-tracker-2026-11-03-v2/report.md` for scope,
raw evidence and remaining limitations. Keep servo power off and scene fixed.

## Offline recorded-motion replay — 2 November 2026

The optional `camera_registration.patch_radius` overrides background matching
window size only. Absent means the legacy `settings.patch_radius` (5,11x11).
The replay candidate uses9(19x19), with the same numerical rejection thresholds.
Independent-anchor separation accounts for the largest configured patch radius;
invalid radii still reject through the production matcher. No anchors are dropped.

Set `recorded_motion_analysis:true` for explicitly retrospective motion recordings.
Reports then leave static span/scope null, describe the replay role, and expose
`apparent_image_heading_circular_span_deg`: shortest arc covering accepted image
directions. It is not shaft angle or total travel. Overlay labels distinguish
saved motion from static repeatability. Missing flag keeps legacy reporting.
Actual measured angles and verifier eligibility remain null/false.

Saved replay reference is pre-command frame3.116/131frames localize, including
20/20phase-window samples;15unknown remain, all null. Case residual metrics are
conditional image translation checks only. Source motion capture was exposed in
initialization/development; no independent motion-verification pass or live-default
promotion.120tests pass,8digital controls reject. All intermediate/frozen failures
are preserved. No hardware/model operation occurred in this task.

See `runs/servo-motion/guarded-replay-2026-11-02-v4/report.md`, phase-analysis.json
and assessment.json. Keep servo power off; fresh independent validation and actual
angle calibration remain future work.

## Fixed-stand view — sixty-second static check

User authorized the60-second passive check with servo power off. One fresh iPhone
capture saved271frames:270localized,1startupunknown(frame2),266preview-ready.
Zero tracking losses after readiness, final state tracking; no gaps above1second.
Sample timestamps span59.14394seconds. Same reference/settings as the prior short
fixed-stand check; source/settings frozen and unchanged, no post-result tuning.
All8digital controls reject. Agent inspected early/late pixel overlays. Center
Stage and Portrait inactive in all271saved samples. This is scoped static tracking
for this recorded view only: not calibrated angle accuracy, moving-shaft behavior,
between-frame verification or powered/load mounting stability. Actual angle null,
full Behavior A/B incomplete. Earlier failed views/runs remain preserved.

No code changes/tests rerun in this data-only task; last107tests passed. No serial,
firmware upload, Meta calls or servo actuation. Installed LED/OLED firmware SHA
unchanged. Evidence: runs/servo-tracking/taped-fixed-long-2026-11-02-v1/assessment.json
and report.md. Keep phone/scene fixed. Next review mount/power readiness before
separately authorized guarded movement. No historical RUN, automatic installation
or actuation. Taped-mount stability remains user-reported while unpowered.

## Fixed-stand view — latest check

The user confirms the iPhone is in a stand, then confirms its adjustment is fixed.
New reference features come from four supervised clear tabletop regions rather
than loose desk objects. Existing detector, registration and rejection limits
are unchanged. Saved initialization18/20 is development, not validation.

An independent12-second requested capture saves53frames:51localized,2startup
unknown,48preview-ready,zero losses after readiness; final state tracking. No
post-result tuning. All eight digital controls reject; not physical fault proof.
This is one short static check, not long-duration or moving-servo qualification.

Read-only Center Stage and Portrait diagnostics were added to native camera
reports and saved frame journals. Both effects are inactive in all sampled frames
of this check and three earlier captures from this task. Earlier captures without
these fields cannot establish their historical settings. No effects were changed.

Earlier tabletop attempts remain preserved: one low-texture initialization,
a32/34 exposed replay and an independent0/54 after visibly rotated framing.
These results do not establish the physical cause of camera-image rotation.

All107 host tests pass; the updated helper compiled locally and captured actual
samples with the new fields. Camera availability/permission is working. No serial
commands, firmware upload, servo actuation or Meta calls. The installed LED/OLED
application is unchanged. Mount stability remains user-reported and unpowered.
Actual angle, plane correction and mechanical zero remain unverified; full
Behavior A/B incomplete. Keep phone and scene fixed.

Evidence: runs/servo-reference/taped-fixed-2026-11-02-v1/assessment.json and
runs/servo-tracking/taped-fixed-live-2026-11-02-v1/report.md. Current passive
default uses this view; earlier grid/taped results retain their saved-view scope.

## Latest registration diagnosis — 2 November 2026

The saved-frame diagnosis supports ambiguity on the repeating screw-thread
background patch. A nearby patch improves retrospective localization from35/40
to39/40 without changing any numerical rejection limit. The auxiliary matcher
replay is diagnostic, not a claim of bit-identical reproduction of every prior
fractional fit or of physical scene motion.

A new independent12-second iPhone session saves53frames, all unknown with both
candidate and original configuration on the same frames. The saved image shows
changed image positions and rearranged loose items. This is successful camera
acquisition with failed reference registration, not a camera permission failure.
The physical cause of image displacement is unconfirmed. The candidate remains
unpromoted, no post-result tuning. Prior partial35/40 result remains historical.

No production source changes or repeat test suite in this task; last107 tests
passed. The new saved-image diagnostic harness compiled and executed. Eight
digital controls reject; no physical fault injection or servo movement. No serial,
firmware upload or Meta calls. Actual angle remains null and full Behavior
verification incomplete. Mount stability remains user-reported while unpowered.

Next confirm the iPhone support arrangement, avoid movable loose-object anchors,
and establish a stationary scene/reference before further passive checks.

Earlier records below retain their saved-view scope.

The tracker now localizes the horn hub and distal tip from saved camera pixels,
checks the body reference, and writes timestamped **unverified** estimates.
There is no camera capture, serial, firmware or model/API operation in this tool.
The servo was not moved during development or evaluation.

## Current taped mount — 2 November 2026

The servo is screwed to its acrylic plate and temporarily taped at the table
edge. Unpowered stability is user-reported, not automatic or loaded-motion proof.
The grid is obscured; explicit image-only geometry avoids inventing a card map.
No perspective correction, measured shaft angle or angular zero is available.

New reference v1 initialized13/15 exposed frames, but its independent capture
localized0/51 because current image positions differed beyond registration bounds.
The failed run remains preserved. Reference v2 refreshed only supervised points
and ROIs on that capture (50/51 retrospective initialization, not validation).
All numerical detector/rejection limits and native code are unchanged.

A second independent12-second requested capture saved40frames:35localized,
5unknown,25preview-ready,2tracking losses,1recovery; ended recovering. Unknowns
include camera-model fit residual rejection. Sustained tracking remains incomplete;
no tuning followed this final result. Eight digital controls reject; no physical
fault injection. All107 host tests pass, including explicit image-only/null-plane
and registration/unknown handling. No servo motion, serial/model calls or firmware
change. Full Behavior A/B remains incomplete.

Current passive default aliases `hardware/servo.tracker.taped.pending.json`, with
`hardware/servo.taped.preview.json`; this selects the present view and does not
qualify sustained or moving tracking. Old grid configs and results are historical.
Evidence: `runs/servo-tracking/taped-mount-live-2026-11-02-v2/report.md` and
`runs/servo-reference/taped-mount-2026-11-02-v2/assessment.json`.

## Image-only geometry mode

When no usable planar reference is visible, explicitly set the preview config's
`geometry_mode` to `image_only` and `preview_card` to null. Tracking then reports
apparent image heading and projected case-relative heading only. Card-plane
scenarios are empty, extrapolation is null, and no homography is computed.
Missing card data without the explicit mode is rejected. Actual `angle_deg`,
calibration and verifier eligibility remain null/false. The plane preview renderer
requires a card; image-only visualization uses the tracker pixel overlays.
Camera/body registration, native detectors, rejection limits, temporal gates and
strict measured-plane validation are unchanged. Camera movement beyond those
limits requires a new reference, followed by an independent fresh capture.

## Physical scene obstruction — latest check

A real card obstruction and return to readiness have now been recorded using
three separate five-second camera captures. A visibly changed phone view required
supervised reference refresh first; all numerical detector/rejection settings and
source code were then identical across the three phases. That stage’s passive
default pointed to its refreshed view. The earlier final-grid-view checks below
belong to the prior framing and remain preserved.

| Actual capture phase | Frames | Localized | Unknown | Preview-ready |
| --- | ---: | ---: | ---: | ---: |
| Clear before card | 18 | 16 | 2 | 13 |
| Card held in view | 7 | 0 | 7 | 0 |
| Clear after removal | 13 | 11 | 2 | 8 |

Agent inspection of the saved covered frame confirms that the card blocks the
horn, case, OLED and part of the grid. The unchanged automated tracker rejects
all seven covered frames with null points/previews; the independent after-removal
capture regains tracking and readiness. No previous values are carried forward.
This is a scoped pass for **broad scene obstruction and return to readiness**,
not an isolated horn-only rejection test. Because these are separate captures,
the gaps and physical transition boundaries are unobserved; exact loss/recovery
latency is not measured. The test does not validate shaft angles or moving-servo
performance. User confirmations are separate operator reports, not camera proof.

The initial timed attempt lacked a valid clear baseline and has no established
obstruction interval. A subsequent clear baseline failed after another substantial
framing change. Both remain incomplete under `physical-occlusion-2026-10-30-v1/`
and `v2/` in `runs/servo-tracking/`. The successful fixed-reference phased trial,
raw images, unchanged outputs, source freezes, `assessment.json` and `report.md`
are under `runs/servo-tracking/physical-occlusion-2026-10-30-v3/`. Reference changes
occurred before the successful phases, with no tuning from covered/after results.

No software code changed; the last 105-test suite remains recorded. No servo
movement, serial commands, firmware installation or model API request occurred.
Actual angles remain null; full Behavior A/B remains incomplete. Keep the phone
and rig fixed. The previous provisional overlay is from an older view; current
reference coordinates/configurations have been refreshed without upgrading them
to calibrated measurements.

## Earlier final grid view — independent static checks

The provisional reference and tracker now use the final framing from
`runs/camera/grid-framing-2026-10-30-v4/frame-000010.jpg`. Initialization changes
only the current-view ROI, hub neighborhood and case/background patch locations.
All detector, camera-model, rejection and temporal limits are unchanged. The
nominal printed square remains unmeasured, with flat parallel placement confirmed
by the user. Preview notes now preserve that provenance accurately; metric
calibration and every `angle_deg` remain null.

After 15/17 frames localized in the initialization capture, source/settings were
frozen before two independent camera-only sessions, with no result-based tuning:

| Fresh final-view session | Localized | Unknown | Preview-ready | Losses after readiness |
| --- | ---: | ---: | ---: | ---: |
| 12 seconds, 41 frames | 39 | 2 | 36 | 0 |
| 60 seconds, 267 frames | 265 | 2 | 262 | 0 |

Both unknowns are startup frames; the long run ended in tracking. All eight
digital controls reject, and all 105 host tests pass. This supports static
tracking for this view during those sessions. It does not establish physical
angle accuracy, moving-body tracking, real obstruction handling or behavior
between frames. The earlier long-run 112/267 failure remains retained below;
its cause was not independently isolated or declared universally fixed.

The passive command's default `hardware/servo.tracker.subpixel.pending.json` now
aliases the current final-grid configuration. To select it explicitly use
`--config hardware/servo.tracker.grid.pending.json`. The legacy
`hardware/servo.tracker.json` and previous frozen inputs remain unchanged.
Evidence: `runs/servo-reference/printed-grid-current-2026-10-30-v1/validation.json`,
`runs/servo-tracking/grid-current-live-2026-10-30-v1/` and
`runs/servo-tracking/grid-current-long-2026-10-30-v1/`. Keep the phone fixed.

## Camera-only session command and readiness reporting

One command now captures up to 60 seconds from an explicitly selected camera,
runs the frozen passive tracker, and saves a readable report plus per-frame
session states. It never opens serial, installs firmware or calls a model API:

```sh
.venv/bin/python -m sparkbench passive \
  --device-id 'EXACT_IPHONE_ID_FROM_CAMERA_LIST' \
  --config hardware/servo.tracker.subpixel.pending.json \
  --seconds 60 --fps 5 \
  --output runs/servo-tracking/new-passive-session
```

The selected ID must match the initialized reference. The command saves fresh
camera enumeration, copied reference/configuration, source snapshots and locally
built helper hashes before capture. It uses a new output directory and never
substitutes another camera. Capture or analysis failures leave an incomplete
record and preserve partial evidence. An empty/denied execution context is
reported separately from a claim that the host camera is unavailable.

Readiness is **post-capture reporting**, not a live preview or hardware-control
gate. The unchanged raw tracking trace is retained under `analysis/`. The new
`session-trace.jsonl` preserves every source row and adds causal session fields:

| State | Readiness-qualified preview |
| --- | --- |
| `starting` | Hidden until at least three consecutive valid frames span 0.5 seconds |
| `tracking` | Available from the current accepted frame only |
| `lost` | Hidden immediately on any invalid frame or timestamp/gap violation |
| `recovering` | Hidden until the same consecutive-frame/span requirement is met again |

Only `session_preview_estimates` with `preview_available=true` is the qualified
preview. Original per-frame estimates remain separate audit data, including good
frames that do not yet satisfy readiness. No readiness is backdated, no raw frame
is dropped, no previous value is carried forward, and every `angle_deg` stays
null. Camera timestamp alignment retains the original [0,1] second host-minus-PTS
gate; the original maximum frame-gap limit also stays unchanged.

`quality.json` reports raw localized/unknown counts, readiness-qualified counts,
state transitions, losses/recoveries, unknown sample intervals, observed sample
rate, timestamp offsets and capture gaps. Interval accounting uses adjacent
samples only; gaps above the frozen limit are uncredited, and nothing is
extrapolated before the first or after the last sample. These metrics do not
verify between-frame motion. `report.md` provides the readable summary, while
`session.json` records completion or failure and `integrity.json` hashes evidence.
Neither readiness nor acquisition completion can produce a physical behavior pass.

### First longer session

The new command completed one 60-second explicitly selected iPhone capture with
267 real frames. The frozen tracker localized 112 frames and left 155 unknown;
83 frames qualified for the session preview. States total 5 starting, 83 tracking,
153 lost and 26 recovering. There were seven tracking losses and six recoveries;
the session ended lost. The final 139 frames, beginning at frame 129, remained
unknown over a 30.17 second sampled span. Registration/model limits, especially
background fit error/residual, displacement and body-patch agreement, explain
the rejections; no limit was relaxed and no reference was automatically reset.

Camera timestamp offsets remained within the unchanged gate, approximately
0.058–0.403 seconds. No sample gap exceeded one second; observed sample rate was
4.55 FPS. The longer session therefore exposes registration reliability that the
shorter 39/43 result did not establish. The root cause remains unresolved. Agent
inspection of early and final frames still shows the case/horn/card; the final
image appears darker. This does not prove physical movement of phone or servo.

All 103 host tests pass, including readiness timing, immediate loss suppression,
recovery streaks, gaps, rejected controls, explicit camera identity, failed
capture preservation and source/policy freeze checks. Eight digital controls
still reject. Real physical obstruction/recovery tests were excluded from this
request and were not performed. No servo, serial, firmware or Meta operation
occurred; actual angles remain null. The three requested software/acquisition
tasks are complete, while reliable continuous tracking remains incomplete.

Evidence: `runs/servo-tracking/passive-session-live-2026-10-30-v1/report.md`,
`quality.json`, `review.json`, copied frozen inputs/source and all raw frames.
The test log and saved short-capture replay are under
`runs/servo-tracking/passive-session-prep-2026-10-30-v1/`. Next software diagnosis
can use the saved longer sequence to assess sensitivity to image/lighting changes
without further capture or servo movement.

## What is automatic

Manual initialization defines a search region, a small hub neighborhood and three
textured case-reference patches in `hardware/servo.tracker.json`. The detector
does not receive a manually marked horn tip. It independently processes each frame:

1. Match body patches against the saved reference within an eight-pixel search.
   Small translations are compensated; displacement above two pixels, patch
   disagreement, insufficient texture and excessive matching error are rejected.
   Rotation, scale and out-of-plane movement are not compensated.
2. Find the unique bright, low-chroma connected horn silhouette near the hub
   neighborhood. Reject missing, ambiguous, clipped or implausible shapes.
3. Resolve the darker central hub feature from local intensity contrast and
   estimate the distal tip from the silhouette's principal axis and end cap.
   The pivot and tip therefore come from pixels, not copied initialization points.
4. Reject low detail, unresolved pivot, implausible length, shape changes and
   component-area changes consistent with obstruction. Focus is compared with
   the reference image; this is not an independent optical-resolution calibration.
5. Join the pixel results to original sample PTS, host uptime and Unix timestamps.
   Invalid alignment, time reversal, gaps or abrupt heading jumps become unknown.

This is a tracker for the declared, initialized view. It is not general discovery
of an arbitrary servo. Quality gates are conservative development checks, not
guarantees that every obstruction or pose change will be detected.

## Subpixel matching — method and earlier-view evaluation

`hardware/servo.tracker.subpixel.pending.json` is the current optional passive
tracker configuration; its locations now follow the final grid view above. The
development results in this section belong to the earlier phone view. The method
keeps the background similarity model described below,
with every previous rejection setting unchanged. The case patches expand from
11x11 to 19x19 pixels at the same initialized features, providing more local
context. Background patches stay 11x11. An explicit `patch_matching` option adds
bilinear sampling around the integer match: offsets within +/-0.75 pixels are
tested at quarter-pixel increments using actual mean absolute pixel error. The
integer solution remains if no fractional candidate has lower error. An integer
search-boundary optimum still rejects. Existing configurations without the new
options retain the previous matcher and patch sizes.

Pixel interpolation is confined to sampling the current image. There is no
interpolation of the trace, reuse of rejected points or discarded patch outliers.
The unchanged texture, error, two-pixel body residual/agreement, camera, horn and
timestamp limits still apply. Per-patch integer and refined shifts are recorded
in trace quality fields. This grid spacing is an algorithm parameter, not a
physical subpixel-accuracy guarantee.

Exposed development captures localize 43/46, 45/48 and 44/48 frames; all 43
room-view frames stay unknown. Then source and settings were frozen before a
new twelve-second explicitly selected iPhone capture:

| Method on the same fresh 43 frames | Localized | Unknown |
| --- | ---: | ---: |
| Previous small-patch integer background matcher | 30 | 13 |
| Larger case patches with subpixel matching | 39 | 4 |

Nine frames gain localization and none of the previously accepted frames are
lost. Frames 1–3 remain unknown under registration/camera bounds; frame 9 remains
unknown because camera timestamp alignment is unsupported, even though its native
pixel overlay can show a localized horn. The joined trace is authoritative. No
settings or source changed after the fresh result. The apparent image-heading
span is 2.2 degrees among accepted static images, not angular accuracy.

All 91 host tests pass. The production native test now additionally exercises
smooth analytic synthetic textures with known fractional shifts, search-boundary
rejection, common camera shift, independent body movement and horn obstruction.
All eight digital negative controls still reject on each saved/fresh evaluation.
Synthetic and digital controls are software evidence only; no physical faults
were injected. Calibrated `angle_deg` remains null and every row is ineligible
for the full verifier. This is improved independent static localization, not
moving-servo validation or a continuous behavior pass.

Evidence: `runs/servo-tracking/subpixel-2026-10-30-v1/` contains pre-change sources,
development results and host tests. `runs/servo-tracking/subpixel-live-2026-10-30-v1/`
contains preflight hashes/source snapshots, the actual 43 frames, paired traces,
and `review.json`. The default `hardware/servo.tracker.json` is unchanged; use
the optional candidate explicitly:

```sh
.venv/bin/python -m sparkbench.servo_tracking \
  --config hardware/servo.tracker.subpixel.pending.json \
  --output runs/servo-tracking/new-subpixel-replay
```

The phone stayed fixed. One passive video-only camera session occurred; no
serial/model calls, firmware installation or servo actuation occurred. The
known planar grid/reference and mechanical zero remain requirements for later
calibrated shaft angles, not prerequisites for continuing unverified previews.

## Optional background registration — earlier candidate

`hardware/servo.tracker.background.pending.json` enables an earlier, unverified
camera-registration model. The legacy `hardware/servo.tracker.json` configuration
keeps the absolute body-displacement gate. That earlier candidate uses four
manually initialized background patches outside the horn and case: three OLED
mounting features and one card corner. They are assumed stationary; their
physical stationarity is not independently measured.

All four patch matches participate in a least-squares translation/rotation/uniform
scale fit; no disagreeing anchor is discarded. Existing patch texture and matching
error limits still apply. The fit rejects anchor residuals above two pixels,
rotation above 0.5 degrees, scale change above 1%, or displacement above four
pixels anywhere at the horn ROI, pivot or case-reference patches. The original
two-pixel body-displacement limit applies to the body's residual after this
camera transform. Body-patch agreement is likewise checked after correction at
the original two-pixel limit; raw spread is also recorded. Horn shape/focus,
timestamp and temporal limits are unchanged. Invalid anchors cause unknowns,
with no fallback to accepting a body shift as camera movement.

The joined preview transforms case-axis endpoints and card corners consistently;
case residual translation applies only to the case axis. Detected horn points
remain in current image coordinates. Trace quality records include camera matrix,
camera shift at the pivot, fit residual, body residual and raw patch spread.
This image model does not establish a physical perspective plane, mechanical
zero or calibrated shaft angle, and cannot distinguish coordinated scene motion
from camera motion. Depth parallax, larger reframing, focus/shape changes and
nonuniform image warps remain limitations.

Offline command, using a new output directory:

```sh
.venv/bin/python -m sparkbench.servo_tracking \
  --config hardware/servo.tracker.background.pending.json \
  --output runs/servo-tracking/new-background-replay
```

On the saved 48-frame corrected-view capture, localization increases from 5 to
28 frames; 20 remain unknown, primarily residual body-patch disagreement. There
are 25 newly localized frames and two previously accepted frames now rejected
by the additional camera checks. The reference capture remains 43/46 localized;
all 43 room-view frames remain unknown. Eight digital controls reject original
horn/body faults plus excessive camera shift and missing/inconsistent background
anchors. Generated RGB fixtures exercise common camera shift versus independent
body motion, legacy limits and missing anchors; synthetic matrix tests cover the
similarity fit and coordinate handling. None are physical fault or angle evidence.
All 91 host tests pass.

The evaluation history is retained under `runs/servo-tracking/registration-2026-10-30-v1/`,
`v2/` and `v3/` (each has the full `registration-2026-10-30-` prefix). The first
translation-only model failed its reserved retrospective subset. The next
similarity model with a newly introduced 0.5% scale envelope localized only 1/48;
47 frames exceeded that envelope. The observed scale change was about 0.65%, so
the new camera scale envelope was expanded to 1% for the final candidate. The
old body/error/texture/horn/temporal limits were not relaxed. Both captures had
already been inspected, and the final envelope used their results: **28/48 is a
retrospective development result, not an independent or held-out validation**.
Fresh camera validation is pending. Frozen source/settings, failed attempts,
null traces, controls and tests are retained. No further tuning followed the
final result, and this candidate was not promoted to the default configuration.

No camera acquisition, serial/model calls, firmware changes or servo actuation
occurred during this offline registration stage. The installed LED/OLED runtime
and compile-only guarded servo preparation are unchanged.

### Subsequent independent static check

One fresh twelve-second iPhone capture was then saved after final code/settings
freeze, with no post-result tuning. Preflight hashes and results are retained in
`runs/servo-tracking/registration-live-2026-10-30-v1/`. The candidate localized
28/48 frames and left 20 unknown. The unchanged absolute-body method evaluated
on these **same fresh frames** localized 27/48 and left 21 unknown. The large
development gain did not generalize into a large gain on fresh data. Nineteen
frames have residual body-patch disagreement; no threshold was relaxed to accept
them. Both traces and a paired comparison are retained in `review.json`.

This is independent evidence of partial static pixel localization, not reliable
continuous tracking, actual servo motion or measured shaft angles. The apparent
3.1 degree image-heading span is static repeatability only. The candidate remains
optional and was not promoted. A next software task is improving case-patch
distinctiveness and subpixel agreement from saved data before freezing again.
No serial/model calls, firmware installation or servo actuation occurred; the
one camera session recorded JPEG frames without audio. All source hashes still
match the final 91-test version. Keep the phone fixed for further passive work.

The implementation uses deterministic Swift pixel processing with native ImageIO
decoding. It installs no new package or inference provider and makes no Meta
requests. Connected-component and shape concepts are described in the primary
[shape-analysis reference](https://docs.opencv.org/4.x/d3/dc0/group__imgproc__shape.html);
the project implements its own small detector and does not depend on OpenCV.

## Trace and unknowns

Run offline with a new output directory:

```sh
.venv/bin/python -m sparkbench.servo_tracking \
  --config hardware/servo.tracker.json \
  --output runs/servo-tracking/new-passive-replay
```

`trace.jsonl` preserves every input frame's timestamps and image hash. Accepted
frames have detected image coordinates and estimates under `preview_estimates`:
image heading, apparent offset from the projected case axis, illustrative card
ratio scenarios, and change from the first accepted image heading. That first
pose is an arbitrary reference, not a known mechanical zero or 90-degree position.

Rejected frames have null `localized_points` and `preview_estimates`, with explicit
reasons. No interpolation or prior-value carry-forward is used. Native pixel
overlays describe pixel localization; the joined trace additionally enforces
timestamp/temporal gates and is authoritative for usable estimates.

`angle_deg` remains null and `eligible_for_verifier` remains false for every row.
Unknown card dimensions, only approximately parallel placement, manual reference
initialization, soft imagery, lens distortion, plane extrapolation and mechanical
zero remain unresolved. The trusted metric calibration and Behavior A/B verifier
were not changed. A full behavior pass still requires actual calibrated angles.

## Recorded evaluation

The settings and source were frozen in
`runs/servo-tracking/frozen-settings-2026-10-30-v1/` before final replay and the
different-view rejection run. The positive replay reuses development images; it
is not a new independent live validation.

| Evidence | Result |
| --- | --- |
| Saved current-view capture, seven frames | Six automatically tracked; one early low-detail/reference-mismatch frame unknown |
| Apparent heading span among six static frames | 1.6 degrees; repeatability only, not accuracy |
| Different earlier saved camera view, six frames | All six unknown; old reference not accepted |
| Five digital controls | Full/partial horn obstruction, blur, five-pixel body shift and covered body patches all unknown |
| Native synthetic RGB fixtures | Production detector checks clean directions, hub localization, missing hub, moved body and occlusion |
| Host regression suite | 87 tests pass, including timestamp handling and proof that preview fields cannot make Behavior A pass |

Current-view results:
`runs/servo-tracking/passive-validation-2026-10-30-v1/tracking.json` and `trace.jsonl`.
Different-view rejection:
`runs/servo-tracking/different-view-rejection-2026-10-30-v1/`.
Digital controls are under each run's `pixels/digital-controls.json`; their images
are labeled DIGITAL CONTROL - NOT PHYSICAL. They are derived from a saved frame,
not new camera observations or physical fault injection. Synthetic fixture tests
are also software evidence only.

The first development run remains incomplete: one initial candidate body patch
had reference texture standard deviation 1.46, below the unchanged minimum 4.
That patch was discarded; the remaining three non-collinear case patches have
standard deviations about 15.1, 18.6 and 20.6. No rejection thresholds were relaxed.
Both development runs and the early rejected frame are retained.

## Fresh passive capture attempt — October 30

Two new twelve-second captures explicitly selected the iPhone Continuity Camera.
No serial commands, model requests, firmware installation or servo movement
occurred. Results are retained under `runs/servo-tracking/live-passive-2026-10-30-v1/`
and `live-passive-2026-10-30-v2/`.

The original frozen reference rejected all 46 frames of the first capture. A
visible change in the view exceeded its registration limits. Manual reference,
ROI and hub-neighborhood initialization was refreshed using frame 20; all quality
thresholds and detector code stayed unchanged. Replaying that initialization
capture localized 43 frames and left three unknown, with a 4.0 degree apparent
heading span. This is development data reuse and static image repeatability,
not independent validation or angular accuracy.

The refreshed configuration was frozen before the second capture. Inspection
shows that its 43 frames point at the room rather than the rig; all stayed
unknown. This is an incomplete independent check, not a tracking pass. Both
rejections and the intermediate initialization are preserved. The unvalidated
refresh was not promoted to the default hardware configuration. Reframe the
phone on the case and horn and keep it fixed before further acquisition.

All 88 host tests pass, including the separate compile-only guarded diagnostic
described in [servo-guarded.md](servo-guarded.md). No live angle is verified.

The user then corrected the phone. Capture `live-passive-2026-10-30-v3` shows the
full case and horn and four card corners, with readable READY/Servo unused OLED
text. Current-view initialization localized 43/46 frames. All detector and
temporal thresholds were unchanged and frozen before a new independent capture,
`live-passive-2026-10-30-v4`: 5/48 frames localized; 43 stayed unknown. Most
rejections have a (-2,-2) pixel body-reference translation, whose 2.83-pixel norm
exceeds the frozen two-pixel limit. Eleven also have patch disagreement. This
measures an image-registration difference, not physical movement of the case.
The five accepted static poses span 0.7 degrees in image heading, not calibrated
angular accuracy. See v4 `review.json`, `tracking.json` and `trace.jsonl`.

Framing is usable; no further reframe is requested for passive work. Reliable
tracking across the full independent capture remains incomplete. Candidate view
settings were not promoted to defaults. Registration robustness can next be
assessed offline from saved data without servo actuation. No tracker source or
measurement thresholds were changed, no tests needed rerunning for this data-only
stage, and no serial, model or firmware operations occurred.

## Remaining physical qualification

Actual servo motion, speed, repeatability across a motion range, physical body
movement and obstruction tests are untested. The installed firmware remains
LED/OLED-only and the earlier no-actuation instruction remains in effect.
The printable grid can later replace assumed geometry; it does not alone supply
mechanical angular zero or prove the six-degree acceptance tolerance.
The camera was repositioned, so the stored LED/OLED calibration must also be
revalidated before collecting new LED/OLED verification measurements.
