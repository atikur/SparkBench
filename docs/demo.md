# SparkBench demo script

One take from a new project, about 2 minutes 50 seconds after editing. The real run takes about 10 minutes, so speed up the waits and label each sped-up part on screen. Use desktop width, and make the plan and camera frames large enough to read.

**Before the take:** with USB unplugged and the servo supply off, swap the green and yellow wire ends at the breadboard. Move only those two wires, because a moved LED breaks the saved camera position. Plug USB back in, close heavy apps, and keep the phone still. Say on screen that the wires are swapped.

| Time | Screen | Narration |
| --- | --- | --- |
| 0:00–0:06 | Title card: **"Build passed. Did the board actually do it?"** Subtitle: "SparkBench · built from scratch, 27 Oct – 4 Nov 2026, Meta Global AI Developer Hackathon". | "An AI wrote the firmware. It compiled, and the serial port said done. Nobody checked the board." |
| 0:06–0:18 | Home page: the stamped frame on the right, the idea box on the left. | "SparkBench makes it prove it. A phone watches the real board, and three Meta models help the agent plan, see and read. Only the measurements decide." |
| 0:18–0:38 | Press **Speak** and say the desk-light sentence. Muse Voice fills the box. Press **Plan it with Muse Spark** and show the step table. | "I ask for READY in green, BUSY in red, then DONE with both off. Muse Spark writes the plan, and nothing runs until I approve it." |
| 0:38–0:48 | Close-up of the two swapped wires, then press **Approve plan and run on the bench**. | "Before this take I swapped two wires, and I haven't told the model." |
| 0:48–1:08 | The stage: SAM's boxes appear on the frame with the orange SAM tag. Sped up, labelled. | "First the agent looks at the bench. SAM 3.1 outlines the display and both LEDs, and a separate capture has to confirm them." |
| 1:08–1:18 | Build, install and identity rows. Sped up, labelled. | "Trusted local code builds and installs the firmware, then the board confirms what it's running." |
| 1:18–1:45 | The test. Hold on READY with the **red** LED lit, then the frame count while Muse Spark reads the OLED. End on **Behavior mismatch** with the numbers shown. | "The plan says green. The board lit red. The camera measures the LEDs from pixels, and Muse Spark reads the display without seeing the plan." |
| 1:45–2:15 | The probe flashes the LEDs. Scroll to **LED mapping repair**: the two-row diff and Muse Spark's explanation. Press **Approve mapping repair and retest**. | "The agent runs one fixed probe. Muse Spark works out from the measurements that the pins are swapped. Local code checks the answer, and nothing is flashed until I approve." |
| 2:15–2:35 | Sped-up build and test, then the pass, with READY now lighting **green** on the same wires. Show the numbers. | "A fresh test against the same plan passes. The behavior didn't change, only the pin mapping, and the failure stays on record." |
| 2:35–2:48 | Cut to the labelled recording of the 4 November incomplete test: the red LED lit, the reading unknown, and **Incomplete**. | "And when it can't measure something, it says so. Unknown stays unknown, and never counts as a pass." |
| 2:48–2:55 | Evidence page and repository link. | "Every run, request and frame is saved with its hash, so you can check all of it." |

**If the live take goes wrong:** each plan gets one repair attempt, so a retake needs a new project. Keep the wires swapped and start again from the home page. As a last resort, cut together tonight's [recorded repair](evidence/repair-run.json) and label it as a recording. Use the real numbers on screen rather than the ones from another take, and don't present footage from different runs as one continuous session.

**After filming:** unplug USB and put the two wire ends back. The next plan that runs reinstalls its own firmware.

## Getting SAM 3.1 on camera

SAM runs during camera setup, which is the first thing a new plan does. A plan with a good saved
reference skips it unless the view has changed. To show it, approve a new plan. The run card then names SAM,
draws its boxes on the frame they came from, and holds them for five seconds after the reference
is saved. The result page says when SAM took part in that test's camera setup.

The supporting engineering records cover additional [live validation](live-validation.md), the
[full-rig acceptance plan](full-rig.md) and [servo tracking](servo-tracking.md).
