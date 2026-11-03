# Live LED/OLED validation — October 30, 2026

All four user-authorized LED/OLED stages passed on the connected classic ESP32
and explicitly selected iPhone Continuity Camera. Evidence root:
`runs/live/qualification-2026-10-30-v1/`; machine-readable summary: `summary.json`.
No servo actuation or historical `RUN` command occurred. Actual servo angles
remain null; full Behavior A/B and full-rig acceptance remain incomplete.

| Stage | Result | Evidence under the root |
| --- | --- | --- |
| Installed diagnostic through integrated workflow | 47 settled samples pass | `03-installed-workflow-recalibrated/` |
| Runtime installation | Previous application and boot layout verified; new application bytes verified | `04-runtime-install/` |
| Runtime normal sequence | 45 settled LED/OLED samples pass | `09-runtime-workflow-fresh/` |
| STOP | Nine energized samples and 16 off samples pass | `06-stop-qualification/` |
| Withheld keepalive | Eight energized samples and 16 off samples pass | `08-lease-qualification-fresh/` |
| Actual camera discovery | Red GPIO25, green GPIO26; 44 settled samples, no unknowns | `10-discovery/` |
| Contributor generation from measured mapping | First request accepted; compiled; no repair | `11-discovered-generation/` |
| Generated application installation | Previous runtime verified; new bytes verified | `12-discovered-install/` |
| Generated behavior camera verification | 47 settled samples pass, zero unknowns/mismatches | `13-discovered-workflow/` |
| Final idle | Exact new plan identity, OLED ACK, two increasing idle heartbeats | `14-final-idle/` |

Final sequence: DARK → GREEN → BOTH → RED → DARK END, with fixed 3000 ms dwell
after OLED transfer. Independent expectations are in `specs/led_oled_discovered.json`.
The generator's actual request was checked against the recorded camera discovery
and independent specification; `11-discovered-generation/generation-inputs.json`
retains both input paths/hashes. The OLED reader received crop bytes and the
unchanged generic transcription prompt, without expected answers or UART states.
All model calls used Meta `muse-spark-1.3-contributor`; no fallback provider or OCR.
All 68 host tests pass. `15-final-replay/` independently reproduces the final
comparison offline; wrong LED/OLED expectations fail, and a missing reading
remains incomplete. Those controls are software regressions, not physical swaps.

## Current installed image and repeat command

The trusted runtime with generated data is installed. Neither `led_oled_test`
nor historical combined `rig_test` is currently installed.

- Artifact: `runs/live/qualification-2026-10-30-v1/11-discovered-generation/attempt-01/artifact`
- Binary SHA-256: `0fd36e9a61a57053e7924ef0744f724dcd6022a3e94b2ea0c0fa658ff295a856`
- Plan SHA-256: `e386287913c33ee1c509835112607679ccd7507265871e282707b687f6da6b32`

After freshly enumerating the serial and iPhone IDs, repeat with a new output:

```sh
.venv/bin/python -m sparkbench workflow \
  --port 'FRESH_CP2102_PORT' --device-id 'EXPLICIT_IPHONE_ID' \
  --artifact runs/live/qualification-2026-10-30-v1/11-discovered-generation/attempt-01/artifact \
  --spec specs/led_oled_discovered.json \
  --output runs/workflows/new-generated-test
```

The default reader policy and geometry now describe the validated current camera
position. Runtime acquisition checks exact plan identity, gates starting on fresh
camera frames, renews the keepalive and attempts STOP afterward. It never flashes.
The default diagnostic workflow without `--artifact` expects the historical
diagnostic identity and refuses the currently installed runtime.

## Calibration and retained incomplete attempts

The first current capture exceeded the prior frozen camera geometry. Its report
remains incomplete with 135 unknown values and no Meta requests. Five saved real
frames were explicitly inspected for supervised LED calibration at the current
view. `02-calibration/` retains that calibration. `reader-policy.frozen.json` was
written before a new independent capture, which passed 47 settled samples.
The validated policy and geometry were then promoted to their hardware defaults.
Text reader code, Contributor model, prompt, settling guards, minimum sample
count, alignment and maximum-gap limits were not relaxed.

Two other incomplete attempts are retained:

- `05-runtime-workflow/`: one 0.7-second sample gap exceeded the 0.65-second
  limit. All 43 text readings were retained, and the temporal result remains
  incomplete. A fresh independent sequence passed the same limits.
- `07-lease-qualification/`: one sample PTS was 0.063 seconds later than host
  receipt, outside the alignment bound. The raw capture remains intact. A fresh
  timeout capture passed unchanged timestamp and measurement limits.

The workflow now rejects known temporal coverage failures before paying for any
OLED requests. No unknown reading was replaced with an expected value.

STOP and lease tests show camera-measured energized/off windows before/after
shutdown, before the natural next probe phase. UART shutdown receipt delays were
approximately 0.136 seconds after STOP and 1.640 seconds after the last PING.
These are host receipt measurements, not electrical waveform latency. The
normal capture module remains separate from the serial orchestrator.

## Recovery and remaining acceptance

Both installations wrote only the application at `0x10000`. Before writing, the
existing bootloader, partitions, boot application data and previous application
were verified against retained images. Boot/partition/NVS regions were not
written by the installer. Each new application was independently verified using
esptool `verify-flash`; logs and application copies are retained under each
installation directory. The installer attempts to restore and verify the previous
application if writing or post-write verification fails; that recovery path also
has mocked tests. Original flash backups remain unchanged.

There is one real approved-pin mapping on unchanged wiring. It does not satisfy
the five blind mappings gate. Physical LED-swap negative test, blind rewiring,
proper servo bracket/calibration and full Behavior A/B remain pending. The live
results cover sampled settled LED/OLED windows and the stated shutdown tests;
transitions, continuous behavior, voltage, polarity and servo waveform/angles
are not qualified. Private images/calibration are omitted from default source
handover archives and require deliberate migration or fresh calibration.
