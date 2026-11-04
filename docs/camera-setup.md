# Guided camera setup

Camera setup is part of the bench agent's pre-test flow. On an existing valid
reference, the agent performs its normal readiness check and continues. When
that check finds unsupported geometry before a plan has been tested, the agent
opens guided setup once. **Set up camera regions** on a ready plan also opens it.

1. Select the iPhone. The agent takes a five-second camera-only capture and
   asks SAM 3.1 to find the screen. It aligns the frame with the commissioned
   view to transfer the OLED corners and both identified lens centers.
2. The agent checks the image around each LED against the commissioned view.
   If alignment fails, it looks for one lens of each color and the lit OLED
   border directly in the new frame. SAM outlines both lenses using the
   detected points. The geometry must agree with those outlines and the screen box.
3. The existing verifier checks a separate capture for stable geometry, border
   support and idle/off LED readings. Muse Spark reads the OLED without expected
   text. Only a successful check saves the reference and resumes the agent.
   No region clicks or confirmation are needed on this path.
4. When automatic setup cannot qualify the reference, the editor shows why.
   Select or adjust the two LED lenses and the four corners of the **lit OLED
   border**, clockwise from top left. **Confirm and check camera** tests the
   edited candidate on another capture.

Closing setup or stopping the agent cancels pending work. A failed or cancelled
check cannot activate its candidate. Automatic and manual attempts retain
separate evidence. There are no automatic model retries. Camera setup sends
no serial commands and does not install firmware.

## Measurement scope

This is a geometry refresh for the **existing commissioned bench**, using its
same camera and resolution. It inherits the existing LED measurement radii,
on/off thresholds, OLED crop, reader settings and rejection limits unchanged.
Readiness establishes that the view can be read while idle. It does not establish
new LED on-state calibration, physical angle calibration or a behavior pass.
A different camera, significantly different lighting or unsuitable inherited
thresholds requires separate on/off calibration. Unknown readings stay incomplete.

Once any test starts for a plan, its camera setup cannot be replaced through the
dashboard. Restore its view to retest it, or create a new plan for a new reference.
Mapping-repair proposals inherit the original plan's reference. Neither failed
test frames nor arbitrary uploaded photos can become guided setup evidence.
Uploaded photo region notes remain a separate advisory tool.

## Saved records

The project retains setup through its linked firmware proposal. Jobs, source
captures, bounded SAM records and fresh validation captures are saved under
`runs/dashboard-execution/<setup-id>/`. The confirmed image, operator selections,
geometry, inherited calibration, frozen reader policy and qualification record
are saved under `runs/camera-setup/<setup-id>/`. A proposal-specific pointer is
written only after validation. Reference and qualification files are checked
against their recorded hashes on reuse. The global hardware defaults and earlier
tests are preserved.

Software tests use synthetic captures and mocked model/reader responses. They
exercise the flow and its evidence boundaries, not physical calibration.

## Recorded live session

On 4 November, setup `9afed681d61f4bf894b4c679555f0d1d` completed with
`setup_mode: automatic` for proposal `82a30d2c71634f02ae5bf6e9df0026ca`.
The subsequent installed LED/OLED application passed test
`f31f0f755bd44adc8a51372dd7d028bb`: 27 sampled settled observations, zero
mismatches and zero unknowns. The OLED reader received no expected labels.
This is one successful session on the commissioned bench, not a general
reliability estimate or servo/full-rig acceptance.

The local records are `runs/dashboard-execution/<setup-id>/job.json` and
`runs/dashboard-execution/<test-id>/workflow/analysis/verification.json`.
The source checkout does not include the local `runs/` archive.
