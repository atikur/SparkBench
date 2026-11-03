# SparkBench dashboard

Start from the project folder using the existing local environment:

```sh
.venv/bin/python -m sparkbench dashboard
```

Open **http://127.0.0.1:8765**. To use another local port, add `--port 8766`. Stop the server with Ctrl-C. The command binds only to the Mac's loopback address and needs local network-listening permission if launched from a sandbox.

Open **Projects → New project** for idea planning, a saved parts checklist, assembly references, progress-photo guidance and a handoff to firmware planning. The project page shows a four-step tracker: Describe, Plan, Build & install, Verify. Caveats that used to sit under every control now live behind the **Limits** link in the footer.

The Projects page opens with the one-line pitch, the four-step loop and three proof cards drawn from real recorded runs: a pass, the caught wiring fault and an incomplete run. Each card opens its evidence. Every place a Meta model contributes carries a blue Muse Spark mark. A run page opens on the frame that tells its story: the first mismatch for a fault, the first unknown reading for an incomplete run. See [the build-guide walkthrough](build-guide.md). Guidance and photo capture are explicit actions; browsing saved projects makes no model calls. Compiled proposals also offer source/binary downloads and a source viewer.

Open the **Evidence** tab, select a run, then choose a measured step or scrub through frames. The evaluated-only checkbox hides frames outside recorded comparison windows. “Full frame” opens the original image at a larger size. Expand Provenance for source files, report hash and recorded findings.

The initial catalog includes:

- LED + OLED check: 45 sampled observations, scoped behavior pass.
- Wiring swap test: 47 sampled LED observations, 36 wrong-channel findings. “Behavior mismatch” and “Fault correctly detected” describe different outcomes; this is not a correct-wiring pass.
- Unreadable OLED: 48 sampled observations with 45 unknown OLED readings. Unknown stays distinct from off, empty text and failure.

Source report, frozen specification, camera metadata and frame index are checked against local integrity manifests. Each image is checked before display, including its measurement hash when evaluated. Changed, missing or inconsistent evidence becomes unavailable. These are local integrity checks, not origin authentication or proof of continuous behavior.

## Run the bench (autopilot)

On a reviewed plan, **Run the bench** runs the same explicit jobs a person would click, in order: compile, install, identity check, camera test. It skips a step only when the saved records show it is done (a compiled build for this plan hash; the board record showing that firmware; a confirmed identity) and reinstalls when the board record shows a different application. It enumerates devices and picks a port or camera only when there is exactly one; otherwise it stops and asks. If the camera test does not pass it asks Muse Spark to explain the evidence, then decides: a camera view that no longer matches the frozen reference means "refresh the reference, wiring untouched"; a behaviour mismatch means "check the wiring, the plan is not changed to match a fault"; unknown readings mean "no pass and no fail". It never changes wiring, mappings or limits, and **Stop** cancels the current job through the existing owner. Every step is an ordinary saved job; the decision log is shown on the page.

## Explain a failed or incomplete run

A failed or incomplete run page has a **Why did this happen?** card. **Explain with Muse Spark** sends one bounded request: the frozen expected steps, the counts, the per-sample findings and up to three frames (the first mismatch or unknown frames, plus one matching frame as contrast). Meta never receives the verifier's thresholds or pass logic, and its reply cannot change the verdict. The reply is strict JSON: a diagnosis, a confidence, the frames it cited (which must be among those supplied, or the reply is rejected), what the evidence suggests, one bounded next check, and what cannot be determined. Cited frames are buttons that jump the viewer to that frame. Requests, responses, latency, token usage and integrity hashes are saved under `runs/diagnosis/{run_id}/{job_id}/`. Opening a run shows its saved explanation without a model call; **Explain again** makes a new explicit request. Passing runs have no explanation card.

The catalog is explicit in `src/sparkbench/dashboard/catalog.py`; the incomplete analysis intentionally references its original `restored-positive-control/capture` images. No current calibration/default file is substituted for a recorded run's frozen specification.

The plan page is the [Meta intent planner](intent-planning.md). It opens from a project's **Open plan & bench →** button. Every plan belongs to a project: the planner receives the accepted brief's firmware intent, and changing that intent means revising the brief. Saved proposals and recorded evidence remain read-only to browse. **Prepare firmware plan** on a project makes a planning request; **Run camera test** makes separate Meta OLED-reading requests. The current servo angle and full-rig acceptance remain unmeasured/incomplete. Evidence-grounded failure diagnosis remains pending.

## Run a reviewed LED/OLED plan

Keep the external servo supply off. The trusted LED/OLED runtime never configures or drives GPIO27.

1. Open a saved ready proposal, inspect its steps, and mark that exact plan reviewed.
2. Select **Compile**. Model output is validated data; trusted local source supplies the runtime.
3. Select **Find devices**, then explicitly choose the fresh CP2102 USB port and iPhone Continuity Camera. There is no built-in-camera fallback. Camera enumeration errors describe the current host context; sandbox denial/empty discovery does not establish host camera unavailability.
4. Select **Install**. The installer verifies the existing application and boot layout, preserves a recovery image, writes only the application, and verifies the result. An identical installed image is verified without reflashing. After a successful transaction, a bounded UART check sends only `ID` and requires the exact idle plan identity, OLED ACK and servo-unused marker. Installation does not run a behavior test. A missing identity reply leaves the flash verification recorded and identity visibly unconfirmed; **Check identity** can repeat that read-only check without reflashing.
5. Select **Run camera test**. Preflight checks the exact runtime/plan identity, selected camera and frozen reader policy. The worker captures a bounded sequence, requests STOP, then reads sampled OLED images through Meta Contributor and compares them with the reviewed plan.
6. When the test finishes, its verdict, counts and key frame appear on the same page. Select **Open full evidence →** for every frame. Pass, mismatch and incomplete are separate outcomes. Failed/unreadable attempts remain in history. The comparison checks the reviewed AI plan against hardware; it does not independently certify that the AI understood the original instruction.

One execution worker owns the bench at a time. Reloading the browser restores saved job state and never restarts hardware. **Stop test** requests cancellation through the existing worker and serial owner. During analysis it stops remaining model calls; an already in-flight request may still be charged. Compile cancellation waits for the bounded compiler step; install cancellation waits for the firmware transaction and verification/recovery to finish. A STOP acknowledgement is UART evidence, not a camera measurement of output shutdown. Missing acknowledgement is displayed as unconfirmed; cancelled tests never receive a behavior pass.

Jobs, compiled artifacts, installation backups, captures, analysis and frozen test expectations are retained under `runs/dashboard-execution/{job_id}/`. Endpoints remain loopback-only with a local session token and same-origin checks for actions. No raw serial or servo action is exposed.

The project page's **Status** card shows the accepted brief, current linked proposal, compiled binary hash, recorded installed version, UART identity check and separate camera result. A new accepted brief does not inherit an earlier version's installation or test status. These are saved records; viewing them does not contact the board or establish current connectivity.

Select **Job logs** on the plan page, or a recent job under the project's Status details, to inspect build/flash/identity/test logs. Failed compilation logs remain accessible even when no binary was produced. Installation details distinguish a successful new application, an identical image verified without writing, a restored previous image, and unconfirmed recovery. A successful restoration is not shown as a successful installation of the new program. Log text is bounded to the last 256 KiB. Recovery guidance is derived from transaction records and never starts another hardware operation automatically.

The portable source snapshot may omit raw camera evidence. On such a checkout the dashboard can start, but catalog entries remain unavailable until their original evidence is deliberately migrated. It does not silently substitute synthetic data.
