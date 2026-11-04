# SparkBench dashboard

The bounded [LED mapping repair workflow](mapping-repair.md) is now implemented.
After a confirmed LED mismatch, the fixed probe measures the two allowed pins;
Muse Spark proposes a mapping and local code validates it. The dashboard waits
for **Approve mapping repair and retest** before corrective installation. The
original behavior stays frozen. The complete sequence ran on real hardware on
4 November; see [mapping repair](mapping-repair.md#live-validation).

Start from the project folder using the existing local environment:

```sh
.venv/bin/python -m sparkbench dashboard
```

Open **http://127.0.0.1:8765**. To use another local port, add `--port 8766`. Stop the server with Ctrl-C. The command binds only to the Mac's loopback address and needs local network-listening permission if launched from a sandbox.

Type an idea on the Projects page and press **Plan it with Muse Spark** to open
the project page. Its progress row follows planning, approval, camera setup,
the bench run and the result. Review the steps and choose **Approve plan and
run on the bench**. **Change something** requests a revision in the same
project. If the camera needs help, the region editor appears on the project
page and the run resumes after validation. Manual controls, logs and project
details remain available below.

On the Projects homepage, **Speak** in the idea box captures up to 30 seconds
from the browser microphone. **Stop** sends the clip to Muse Voice
Transcribe and adds the transcript to the idea box for editing. SparkBench
does not save the audio. Review the text and press **Plan it with Muse Spark**
to start planning.

**Suggest ideas** asks Muse Spark for three projects this bench can run, in one
request with no retry. Each idea must carry steps that pass the same validator as
a real plan, and an idea that promises something the bench lacks is dropped.
Clicking one only fills the idea box. Records are saved under `runs/ideas/`.

The progress panel names the current task and its worker (Muse Spark, SAM,
the camera or local code). Active jobs have animated indicators, while approval,
blocked and completed states remain still. OLED reading progress uses the job's
actual frame counts, and the session log is under Details. Motion respects the
browser's reduced-motion preference.

The Projects page opens with the one-line pitch, the four-step loop and three proof cards drawn from real recorded runs: a pass, the caught wiring fault and an incomplete run. Each card opens its evidence. Every place a Meta model contributes carries a blue Muse Spark mark. A run page opens on the frame that tells its story: the first mismatch for a fault, the first unknown reading for an incomplete run. See [the build-guide walkthrough](build-guide.md). Guidance and photo capture are explicit actions; browsing saved projects makes no model calls. Compiled proposals also offer source/binary downloads and a source viewer.

Open the **Evidence** tab, select a run, then choose a measured step or scrub through frames. The evaluated-only checkbox hides frames outside recorded comparison windows. “Full frame” opens the original image at a larger size. Expand Provenance for source files, report hash and recorded findings.

The initial catalog includes:

- LED + OLED check: 45 sampled observations, scoped behavior pass.
- Wiring swap test: 47 sampled LED observations, 36 wrong-channel findings. “Behavior mismatch” and “Fault correctly detected” describe different outcomes; this is not a correct-wiring pass.
- Unreadable OLED: 48 sampled observations with 45 unknown OLED readings. Unknown stays distinct from off, empty text and failure.

Source report, frozen specification, camera metadata and frame index are checked against local integrity manifests. Each image is checked before display, including its measurement hash when evaluated. Changed, missing or inconsistent evidence becomes unavailable. These are local integrity checks, not origin authentication or proof of continuous behavior.

## Project page

A project page shows one state at a time, with one status at the top.

- **Plan:** the idea and the steps, with the run button always in view. **Adjust plan** sends a one-line change to Muse Spark.
- **Running:** the camera frame, five phases (Ready, Installed, Recorded, Read by Muse Spark, Verdict), overall progress and one chip per plan step. During reading the picture follows the frame just read and shows what Muse Spark returned. This is display only, and the verifier still decides at the end.
- **Result:** the verdict first. Each step's chip opens its frame with what the plan expected, what the camera measured and what Muse Spark read, with LED states drawn as dots. A failed or incomplete run shows the explanation or the next action in the same place. Earlier tests of the same build appear below the steps. A pass following a mismatch or incomplete result is labeled **passed on retest**. The results show what each attempt measured; they do not establish what the operator changed.

A project's status comes from the latest test of its current firmware. **Details** holds the run log, manual controls and firmware source. **Your bench** in the top bar holds the parts, wiring diagram and wiring steps, and a mismatch shows the diagram next to the evidence.

## Camera position

The agent now includes [guided camera setup](camera-setup.md). Before a plan's
first test, an unsupported view triggers automatic landmark alignment, SAM
region checks and independent camera validation. The operator only edits the
regions when automatic setup cannot qualify the reference. A successful
check saves a reference for the plan and resumes the agent. The existing LED
thresholds stay fixed. Once testing starts, restore the saved view or use a new
plan for a new reference; repair never changes the original measurement setup.

A camera test is measured only on frames that match the calibrated camera position, so the phone has to stay still for the whole run. The agent checks this before anything is flashed, and again right before the test if it flashed. It records a few seconds and confirms three things: the view matches the calibrated one, both idle LEDs read off, and the frozen OLED reader can read the screen without being told what to expect.

If anything is wrong, the agent names the problem, shows the calibrated view beside the current one, and waits. **I fixed it, check again** repeats the check and the same run carries on from there. **Stop** ends the run. When the check is blocked, Muse Spark looks at the frame once and says which parts are cut off and how to move the phone. That advice is only for the person: it can never clear a check.

The check sends no serial commands. It makes one Meta request when clear, the OLED reading, and at most one when blocked.

If the phone moves during a test, the geometry guard rejects those frames. The result says the camera moved, reports incomplete, and does not blame the board. A rejected frame is never read or guessed.

To calibrate a new phone position, run one test there so a capture shows the LEDs lit, then use `tools/calibrate_view.py`. It copies the capture, sets the view from checked markers (`tools/geometry_overlay.mjs` helps place them), and fits LED thresholds from frames labelled by inspection. It makes no Meta request and touches no hardware. The next capture is the held-out test. `tools/refresh_reference.py` is the narrower option: it moves the view and keeps the thresholds, using frames with the LEDs off.

The firmware shows each step's text in the largest font that fits, so a lone digit is big enough for the camera. A saved build with an older runtime is marked stale and rebuilt rather than installed. If the screen layout changes again, pass `--label-crop` to `tools/calibrate_view.py` so the crop covers the new text area.

## Run on the bench

On a reviewed plan, **Run on the bench** runs the same explicit jobs a person would click, in order: camera setup for a new plan or a camera check otherwise, compile, install, identity check, camera test. It skips a step only when the saved records show it is done (a compiled build for this plan with the current runtime, an install record for that exact firmware, a confirmed identity). It never changes wiring, mappings or limits.

When a test has usable non-pass evidence, the agent can ask Muse Spark to explain it, show the diagnosis, next check and a frame, then wait. **I fixed it, test again** or **I checked it, test again** continues the same dashboard session. The agent checks the camera again and records a separate test of the same plan. A successful continuation reports **Passed on retest**. **Stop** ends the run at any wait. If every frame was rejected for geometry, the agent directs the operator to restore framing without asking for a diagnosis.

## Explain a failed or incomplete run

A failed or incomplete run page has a **Why did this happen?** card. **Explain with Muse Spark** sends one bounded request: the frozen expected steps, the counts, the per-sample findings and up to three frames (the first mismatch or unknown frames, plus one matching frame as contrast). Meta never receives the verifier's thresholds or pass logic, and its reply cannot change the verdict. The reply is strict JSON: a diagnosis, a confidence, the frames it cited (which must be among those supplied, or the reply is rejected), what the evidence suggests, one bounded next check, and what cannot be determined. Cited frames are buttons that jump the viewer to that frame. Requests, responses, latency, token usage and integrity hashes are saved under `runs/diagnosis/{run_id}/{job_id}/`. Opening a run shows its saved explanation without a model call; **Explain again** makes a new explicit request. Passing runs have no explanation card.

The catalog is explicit in `src/sparkbench/dashboard/catalog.py`; the incomplete analysis intentionally references its original `restored-positive-control/capture` images. No current calibration/default file is substituted for a recorded run's frozen specification.

The plan page is the [Meta intent planner](intent-planning.md). It opens from a project's **Open plan & bench →** button. Every plan belongs to a project: the planner receives the accepted brief's firmware intent, and changing that intent means revising the brief. Saved proposals and recorded evidence remain read-only to browse. **Prepare firmware plan** on a project makes a planning request; **Run camera test** makes separate Meta OLED-reading requests. The current servo angle and full-rig acceptance remain unmeasured/incomplete. Recorded Meta diagnoses cover incomplete runs; a complete physical wiring fault, diagnosis and retest in one dashboard session is still pending.

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
