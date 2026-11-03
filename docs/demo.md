# SparkBench evidence demonstration

Use the recorded demonstration while servo calibration is pending. Keep the external servo supply off. The installed LED/OLED-only runtime never drives GPIO27. No new firmware installation, paid API request or powered servo sequence is needed to review these results.

1. Open `runs/live/led-oled-resume-2026-11-03-v1/report.md` and `summary.json`. The latest independent LED/OLED run passed 45 settled samples with zero unknowns or mismatches. Results apply to sampled windows in the recorded view.
2. Open `blind-trials.report.md` in that directory. Five operator-withheld wiring choices matched frozen camera results. There were 11 attempts and six incomplete attempts; this is not a double-blind reliability estimate.
3. Show `physical-led-swap-negative.summary.json`: the intentional wrong wiring caused 36 wrong-channel readings across 47 samples, with no unknowns. Show `restored-positive-control/result.json`: original wiring passed 48 LED samples.
4. Open the current static-tracking report under `runs/servo-reference/current-view-exposure-2026-11-03-v2/`. Keep startup, rejected frames, development and held-out evaluation separate. Image heading repeatability is not mechanical angular accuracy.
5. Show the host test log and `runs/software/full-rig-prep-2026-11-03-v1/report.md`. Full-rig candidates compile but have not been installed or physically qualified. Synthetic A/B fixtures are disabled for hardware use.

## What remains before full acceptance

Independent physical angle observations, a confirmed horn/reference-plane relationship and angular zero, and safe coverage of the required 45–135 degree range are missing. Then generate A/B via the Meta API, install a verified application, run integrated camera acceptance and qualify shutdown on that servo-enabled runtime. Prior UART acknowledgements, the historical fixed servo test and user observations do not satisfy those angle measurements.

The physical protractor/ruler has not arrived and a printed protractor is unavailable. Keep these measurements incomplete. The current LED/OLED shutdown evidence does not establish electrical PWM-off or servo stopping latency.

## Package scope

The source archive omits credentials, local environments and private raw camera evidence. The separate review bundle contains selected reports and demonstration frames with SHA-256 hashes. It is a review aid, not a complete portable replay archive; full raw evidence and retained failures remain in the local project at their recorded paths.
