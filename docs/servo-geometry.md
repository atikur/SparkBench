# Passive servo reference

## Current square-plane preview — 3 November 2026

The50x50mm reference grid is now visible with all corners. User says paper flat
and horn mostly aligned with the tabletop, possibly downward at front. Current
horn/reference parallelism is unconfirmed. Saved-image grid-plane preview and
manual body overlay are under `runs/servo-reference/mounted-grid-2026-11-03-v1/`.
They use1:1square geometry and display UNVERIFIED/no calibrated angle. This is
not a verified horn-plane perspective correction. Pixel tracking can continue;
strict plane transform, mechanical zero and actual angle remain null.
Reference notes now preserve possible tilt instead of claiming parallelism.
All121tests pass; no new capture, hardware operation or model call in this update.

Automatic passive pixel tracking is now implemented separately. It detects the
hub and horn tip, checks the body reference and saves timestamped unverified
traces with rejected frames left unknown. See [servo-tracking.md](servo-tracking.md)
for initialization, saved-frame evaluation and remaining physical qualification.
The static preview below remains available; calibrated shaft angles stay unknown.

## Current mounted-rig calibration preparation — 2 November 2026

The printed-grid records below belong to earlier views. The servo is now on its
flat plate in a temporary taped table-edge mount. Offline motion tracking has
improved, but actual angles remain unverified. Current calibration needs measured
outer print width/height, a flat reference with confirmed parallel relation to
the horn face in this mount, and a fresh view of all four reference corners.
Historical print-scale and plane reports are not upgraded or transferred to this
new placement. No physical/angular zero is inferred from1500us or a case axis.
See `runs/servo-reference/calibration-prep-2026-11-02-v1/pending.json`. External
servo supply stays off during reference setup; no actuation or flash is needed.

## Printed grid — provisional reference

The user has supplied the printable reference and confirmed that it is flat and
parallel to the white horn face. The print was made at 100% but has not been
measured. `hardware/servo.grid.provisional.json` preserves both reports separately:
parallel placement is user-confirmed; actual print dimensions/aspect are not
independently verified. No measured size is inferred from the printed 50 mm label.

Using the nominal 1:1 square design, the current provisional unit-square
homography and watermarked rectified view use the final saved view,
`runs/camera/grid-framing-2026-10-30-v4/frame-000010.jpg`. Approximate manually
initialized corners A/B/C/D and shaft/tip/case landmarks are retained. Final
images and `reference.json` are under
`runs/servo-reference/printed-grid-current-2026-10-30-v1/images-host/`
and its parent directory. Both final images say UNVERIFIED and no calibrated
servo angle. Native Core Image rendering runs outside the sandbox; earlier
failed and superseded layouts remain in the previous provisional directories.
No geometry or calibration gate was changed.

The nominal-grid horn heading from the printed top-edge direction is stored
only under `preview_estimates`. It uses manually initialized points
outside the grid, extrapolated through assumed print geometry. It is **not a
measured servo position or mechanical zero**. Unit-square coordinates are not
millimetres. Corner reprojection is an algebra check, not physical validation.
The strict `plane_reference` and metric `image_to_plane` remain null, as do
`angle_deg` and `measured_angle_calibration`; full Behavior A/B remains incomplete.

Keep the current phone view fixed. Actual print dimensions/aspect, corner/plane
accuracy, lens distortion, extrapolation and mechanical angular zero still need
qualification before measured shaft angles. Unverified previews can continue
without re-requesting print measurements. Reference construction reused saved
frames. The tracker was then initialized to this final view without changing
numerical limits. Frozen independent checks localized 39/41 frames over 12 seconds
and 265/267 over 60 seconds; both retained two startup unknowns. The long run had
262 readiness-qualified frames and no loss after readiness. These are static
pixel-localization results for this view, not angular calibration or between-frame
verification. All 105 host tests pass. See `validation.json` beside the reference.
Only camera acquisition occurred; no model API, serial, firmware or servo operation.
The passive command's optional default now uses this view. `hardware/servo.grid.preview.json`
and `hardware/servo.tracker.grid.pending.json` provide explicit current inputs;
previous views and the older long-run failure remain preserved.

## Earlier unverified card preview mode

The user authorized proceeding with the rectangular card unmeasured, keeping
estimates unverified until a printable grid is used later. Configuration:
`hardware/servo.preview.json`; result:
`runs/servo-reference/unverified-preview-2026-10-30-v1/analysis/preview.json`.
This mode uses the latest saved card capture, with newly selected current-view
shaft, tip and case landmarks. It does not reuse old-view pixel coordinates.

```sh
.venv/bin/python -m sparkbench.servo_preview \
  --config hardware/servo.preview.json \
  --output runs/servo-reference/new-unverified-preview
```

The rendered illustration explicitly assumes a 3:2 card, without claiming that
ratio is measured. Other illustrative ratios show sensitivity:

| Assumed card width / height | Unverified horn heading from card top edge |
| --- | --- |
| 1.25 | 97.1 degrees |
| 1.50 | 98.5 degrees |
| 2.00 | 101.3 degrees |
| 2.50 | 104.0 degrees |

These are illustrative scenarios, not confidence/error bounds or commanded servo
positions. The actual ratio remains unknown and can lie outside those scenarios.
The raw image heading is 109.9 degrees from image-right, clockwise. The apparent
horn/projected-case-axis offset is 11.7 degrees. These values use different,
explicit image/preview references; none establishes physical angular zero or an
actual shaft position. Horn points lie outside the card, so the assumed card map
is extrapolated. The user described the card as only approximately parallel.
Landmarks are manually selected on a soft image; this is a static preview, not
automatic moving-horn tracking or independent camera verification.

Preview values are nested under `preview_estimates`, with
`eligible_for_verifier: false`. `angle_deg` and `measured_angle_calibration` remain
null. The strict metric `perspective()` path is unchanged and still refuses to
calibrate without confirmed dimensions/aspect and plane relation. Behavior A/B
remains incomplete. Both annotated geometry and assumed card-plane images carry
UNVERIFIED labels. No new camera session, serial command, firmware change, servo
actuation or model/API request occurred. The printable grid can replace the
assumptions later without relabeling the current preview as calibrated evidence.

## Earlier body-reference establishment

The servo was not moved. No serial port, camera session, firmware uploader or
model API was used during reference establishment. The inputs were six previously
saved real frames from `runs/camera/servo-passive-2026-10-30-v2/`.

The reference configuration is `hardware/servo.geometry.pending.json`. Results
are in `runs/servo-reference/static-body-2026-10-30-v1/analysis/reference.json`.
The annotated real crop is `analysis/images/body-reference-overlay.png`.

## Established image reference

- **S**: manually selected shaft center, at image pixel (1328, 700).
- **T**: manually selected distal horn tip in its present static pose.
- **L1/R1, L2/R2**: samples on opposite visible case edges.
- **A–B**: projected midpoint line between the case-edge samples.

The reference transform moves S to the origin and rotates image coordinates so
A–B defines the positive image-reference Y direction. Units remain image pixels.
It does not remove optical perspective, establish mechanical zero, identify a
90-degree position, or measure an actual shaft angle. The projected case axis
is not asserted to lie in the horn's rotation plane. Landmark precision is not
independently measured; the image is soft.

Static patch comparisons found zero best-fit translation in frames 2–6, with
mean absolute luma differences 0–3.53 against frame 5. Frame 1's best fit reaches
the four-pixel search boundary and has difference 28.85; it is retained as an
outlier diagnostic. These comparisons do not establish pose/angle accuracy,
stability during motion, or automatic full-rig verification.

## Perspective correction still needs physical reference information

The visible case silhouette contains different depths and surfaces. Choosing
four silhouette corners and stretching them into a rectangle would not establish
the horn's true rotation plane. A perfect four-corner fit is also compatible with
different output aspect ratios, which produce different angles.

The correction path accepts four ordered corners of a known rectangle/square,
known dimensions or aspect ratio, and an explicitly confirmed relation to the
horn plane. A reference in the horn plane, or a confirmed parallel plane, can
provide the planar geometry. A parallel plane's offset changes scale/translation
after metric rectification; it does not supply mechanical angular zero or prove
that a moving servo body preserves that relation. See the primary
[homography reference](https://docs.opencv.org/4.x/d9/dab/tutorial_homography.html).

The current `plane_reference` is null, so **no calibrated perspective warp or
angle is produced**. The implementation checks convex ordered corners, solves a
normalized four-point homography, verifies algebraic correspondences and renders
a metric-aspect reference-plane image only when the required provenance and
plane information are present. Synthetic tests recover independent interior
points, demonstrate aspect-ratio ambiguity and reject missing/degenerate inputs.
Those tests are software evidence, not physical calibration.

Even with a supplied plane, the result remains validation-pending. Lens
distortion, corner uncertainty, horn-plane relation, angular zero and movement
tracking must be qualified before accepting Behavior A/B's ±6-degree tolerance.
`angle_deg` and `measured_angle_calibration` stay null. Full behavior remains
incomplete. No pulse command or earlier manual movement observation is used as
an angle measurement.

## Repeat offline

```sh
.venv/bin/python -m sparkbench.servo_geometry \
  --geometry hardware/servo.geometry.pending.json \
  --output runs/servo-reference/new-reference-output
```

The native Swift helper compiles locally and reads only saved image files. It
uses deterministic pixel math and Core Image; no OCR, alternative inference
provider or additional package is installed. Existing evidence directories are
not overwritten. A successful process exit means reference artifacts were
written; inspect their explicit status before interpreting calibration progress.

To complete perspective setup without moving or mounting the servo, supply a
known square/grid beside the horn in the same or a confirmed parallel plane,
or measured geometry of a suitable flat case surface parallel to the horn.
Placement and plane relation need to be established physically; neither can be
inferred reliably from the current silhouette alone. No servo actuation is
authorized by this passive task. The camera has moved from the accepted LED/OLED
view, so that stored calibration must be revalidated before new LED/OLED tests.
