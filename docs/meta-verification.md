# Meta-backed LED/OLED verification

Current live state: a camera-discovered mapping was used for Contributor
generation, compilation and hash-verified runtime installation. All 47 final
settled LED/OLED samples passed. The camera-position calibration was refreshed
and independently validated. See [live-validation.md](live-validation.md) for
the installed artifact, current repeat command and preserved incomplete runs.
The original validation and diagnostic commands below retain their stage scope.

The selected OLED text reader is **Meta API only**. Current runs use
`muse-spark-1.3-contributor`, selected explicitly in local `.env` with
`META_MODEL=muse-spark-1.3-contributor`. The endpoint is `https://api.meta.ai/v1/chat/completions`. The key in local `.env` was
successfully checked against Meta's models endpoint. No additional SDK is
needed; requests uses the existing project environment.

Meta documents [image input](https://dev.meta.ai/docs/image-understanding) and
[JSON Schema output](https://dev.meta.ai/docs/structured-output) on this endpoint.
Contributor was requested by the user for lower cost; submitted crops, prompts
and responses may be used by Meta for training. See
[pricing and terms](https://dev.meta.ai/docs/pricing-rate-limits). Existing
validation records used Standard `muse-spark-1.3` and are preserved unchanged.
The model is available in the authenticated model catalog, not assumed from
the old Llama endpoint. `META_MODEL` can select an explicitly configured Meta
image-understanding model. There is no other-provider fallback.

## Latest independent validation — LED/OLED-only pass

`runs/led-oled/20261030T061710.065777Z/` contains a new 105-frame capture.
With the reader settings frozen before capture, all 47 selected settled frames
match both LED states and the independently specified OLED labels. Contributor
made 47 requests, with no retries, unknowns or mismatches. Result:
`runs/vision/contributor-validation-2026-10-30-v1/verification.json`.

| Step | Red | Green | Meta reading | Samples |
| --- | --- | --- | --- | --- |
| 1 | off | off | DARK | 9 |
| 2 | on | off | RED | 9 |
| 3 | off | on | GREEN | 10 |
| 4 | on | on | BOTH | 9 |
| 5 | off | off | DARK END | 10 |

Wrong LED or OLED expectations fail in derived software controls; removing a
reading produces incomplete. The synthetic blank development crop remains
unknown. These controls are not physical fault-injection evidence. Earlier
incomplete reports and their null readings remain unchanged.

This pass covers sampled settled LED/OLED windows only. Full-rig verification
remains incomplete because actual servo measurements are missing. No reflash,
RUN command or servo actuation occurred in this validation.

## Frozen Contributor reader preparation

`runs/vision/contributor-development-2026-10-30-v1/` tested six saved crops:
the two previously uncertain labels, three consistency controls, and a synthetic
blank. The full-width crops left one label unknown. These were development
results, not a replacement for the earlier incomplete validation.

The second development set, `contributor-development-2026-10-30-v2/`, applies
deterministic margin trimming. All five text crops were read correctly and the
blank remained unknown. `integration-check/checks.json` confirms that the
production preparer reproduces all six tested image hashes exactly.

`tools/macos_vision/prepare_label.swift` finds foreground bounds at pixel-score
threshold 48 and adds 24 pixels of padding where the source permits. A narrow
component spanning the entire crop height is excluded from the bounds as an
OLED frame edge. All other components, including small marks, contribute to the
bounds. The output is a rectangular crop of the original pixels; it does not
paint, synthesize, threshold or spell-correct glyphs. Blank input is retained.
The original crop, prepared crop, source/output hashes and preparation geometry
are auditable in each Meta request directory.

The Contributor model, unchanged blind prompt, 1024-token cap, preprocessing
source and LED calibration were frozen in `hardware/oled-reader.policy.json`
before the new live capture. Source snapshots are retained under
`runs/vision/contributor-policy-2026-10-30-v1/`. The model receives only prepared
image bytes and the generic instruction; local development reference answers
are never included.

## Previous Standard-mode evidence

- Calibration: `runs/vision/calibration-meta-2026-10-30-v3/calibration.json`.
- Fresh capture: `runs/led-oled/20261030T053415.529742Z/`, with 107 real camera
  frames, raw UART bytes and timestamps. Only `ID` and `VISUAL` were sent.
- Historical result:
  `runs/vision/meta-validation-2026-10-30-v3-budget-fix/verification.json`:
  **incomplete**. All 47 settled LED measurements match; Meta read 45 of 47
  labels and marked two unreadable. Both remain null. There are no conclusive
  mismatches. Capture completion alone is not a pass.
- The original `meta-validation-2026-10-30-v3/` result is preserved. Its five
  server-truncated responses were retried with a higher token limit, reusing
  the 42 completed readings. Three retries produced text; two returned
  unreadable. Unreadable answers were not retried to seek a passing result.
- `pixels.jsonl` retains the quantitative pixel measurements and geometry checks.
- `crops/` retains rectified OLED images and label-only PNGs.
- `meta/*/request.json`, `response.json`, and `reading.json` retain each request
  description, raw model response, usage and parsed reading. Requests omit the
  secret and represent image bytes by their hash; original crops remain local.
- `reader.jsonl` joins the independent Meta readings with their pixel records.
  `integrity.json` covers saved artifacts. Hashes do not authenticate a scene.
- The resumed result references original pixel/crop artifacts through
  `pixel_artifacts_directory`. `digital-controls.json` records deliberately
  wrong expectations failing and a synthetic blank crop remaining unknown;
  these are software controls, not physical fault-injection evidence.

Earlier Apple OCR experiments are retained as historical development artifacts;
they are not the accepted reader and are not used as a fallback. The current
native helper contains no text recognizer or learned image-registration model.
It performs only pixel matching, image rectification, cropping and LED metrics.

## Measurement rules

Red and green LED circles are defined in `hardware/vision.geometry.json`.
Thresholds were fitted from prior agent-inspected real frames in the original
capture, independently of the fresh validation capture. The dark/on pixel
score intervals have a gap; intermediate, nonfinite or unsupported readings
remain null. Scores are weighted gamma-encoded sRGB JPEG values, not voltage,
current, optical power or linear radiometric intensity.

Registration matches the static OLED border pixels to the reference using
bounded scale and translation. It never reads the display text or LED states
to decide alignment. Scale is limited to 0.88–1.12, image-center translation
to 12 pixels, total target displacement to 80 pixels, and mean matching error
to 35 pixel-score units. Each of four OLED edges must retain at least 85%
bright-border support. Changed scene geometry can therefore produce unknowns.

Only the label band is sent to Meta. The generic prompt requests literal visible
text and null when unreadable. It provides no expected label, allowed-label
vocabulary, step number, UART state, prior answer or independent specification.
There is one bounded request per selected crop, without redirects or hidden
retries. The completion limit is now 1024 tokens, since a 256-token cap sometimes
ran out before Meta returned text. `resume-truncated` explicitly retries only
server-truncated responses with the same crop, prompt and model, preserving the
original report. Completed wrong or unreadable answers are not eligible.
Access, rate-limit, service and connection errors stop further batch
requests and leave readings unknown. They do not diagnose geographic causes.

The comparator uses UART **timing and step IDs only**, never its state/text
values as measurements. It excludes the first 0.65 seconds and last 0.45 seconds
of each dwell, requires at least five samples per step, checks temporal coverage,
and rejects gaps above 0.65 seconds. Every selected frame must agree. Case and
whitespace normalization are allowed; spelling correction toward an expected
answer is not. Conclusive mismatches fail; missing/uncertain evidence cannot pass.

This verifies sampled settled LED/OLED windows. It does not verify behavior
between samples, all transitions, servo angles, electrical characteristics,
discovery or generated firmware. The new protected LED/OLED runtime is compiled
but not installed/physically qualified; see [software-pipeline.md](software-pipeline.md).
The full
Behavior A/B verifier still requires actual servo measurements.

## Repeat the historical diagnostic profile

For the currently installed generated runtime, use the explicit command in
[live-validation.md](live-validation.md). The following command requires the
historical `led_oled_test` image, which is no longer installed. Refresh the
camera/serial IDs when reconnecting. Run the existing capture orchestrator:

```sh
PYTHONPATH=src .venv/bin/python -m sparkbench.led_oled --port '/dev/cu.usbserial-0001' --device-id '618E8741-BCAC-4C8E-AB5E-897800000001'
```

Use its new output directory as RUN_DIRECTORY, choosing a new ANALYSIS_DIRECTORY:

```sh
PYTHONPATH=src .venv/bin/python -m sparkbench.vision analyze --run RUN_DIRECTORY --calibration runs/vision/calibration-meta-2026-10-30-v3/calibration.json --output ANALYSIS_DIRECTORY
```

Camera and native image processing may require execution outside the file
sandbox. Meta access requires network access. The image analyzer never opens
serial or flashes firmware; acquisition alone never sends serial commands.
No servo actuation or temporary mounting is authorized during this stage.

The full raw `.env` is ignored and must not be copied into evidence or handover
artifacts. `doctor` reports only whether a local key is configured and never
requests camera access or calls Meta.

All 36 host tests pass. The full Behavior A/B verifier remains unchanged and
rejects missing servo measurements. The latest scoped LED/OLED result passes;
no full-rig camera-verification pass has been recorded.
