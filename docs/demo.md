# SparkBench demo video

Watch it at https://youtu.be/y6KSh-sNYX0. The video runs 2 minutes 56 seconds and is edited from screen recordings made on 4 November 2026. The
real run takes about 10 minutes, so the waits are sped up. Each sped-up or slowed part says so on screen,
and labels mark the live recordings, the camera replays and the saved screens.

| Time | Screen | Source |
| --- | --- | --- |
| 0:00 to 0:04 | Close-up of the camera view: READY is on the display, and the red LED lights. | Wire-swap session |
| 0:04 to 0:07 | Title card: "Build passed. Did the board actually do it?" | Title card |
| 0:07 to 0:12 | The home page. | Home page recording |
| 0:12 to 0:18 | The iPhone's view of the bench with the saved SAM 3.1 regions drawn on it. | Recorded camera frame |
| 0:18 to 0:24 | **Speak**, then Muse Voice writes the spoken idea into the box. | Voice recording, recording part at 5.6x |
| 0:24 to 0:31 | Picking the desk status light example fills the idea box, and Muse Spark starts planning it. | Home page recording |
| 0:31 to 0:38 | The desk-light plan for this test, with its step table. The narration and label say it is a saved plan. | Saved screen of a plan with the same steps as the test that follows |
| 0:38 to 0:46 | Close-up of the breadboard with the two swapped wire ends circled. | Frame from the fault test |
| 0:46 to 1:01 | SAM 3.1 outlines the display and both LEDs. | Wire-swap session, 2.4x |
| 1:01 to 1:11 | READY lights red and BUSY lights green, as full-frame camera replays. | Wire-swap session, slowed |
| 1:11 to 1:33 | Muse Spark reads the OLED, the test reports a mismatch, and the fixed pin probe runs. | Wire-swap session, 8.1x and 6.8x |
| 1:33 to 1:55 | The mapping repair card, zooming in on the pin table, then the operator's approval. | Wire-swap session, the zoom on a still frame |
| 1:55 to 2:03 | Local code builds and flashes the repaired mapping. | Wire-swap session, 10x |
| 2:03 to 2:13 | The same wires: READY lights green and BUSY lights red, as full-frame camera replays. | Wire-swap session, slowed |
| 2:13 to 2:31 | A fresh reading, then the pass with 27 of 27 samples, zooming in on the result. | Wire-swap session, the reading at 10.6x, the zoom on a still frame |
| 2:31 to 2:41 | A separate test: the red LED reading was unknown, so the result is **Incomplete**. Muse Spark explains the frames and proposes the next check. | Second plan, same night |
| 2:41 to 2:48 | The test history keeps the mismatch, the incompletes and the pass. | Still from the second plan's recording |
| 2:48 to 2:56 | What was built during the hackathon, and the repository link. | End card |

The fault, probe, approval and retest are one session on 4 November. The home page and voice recordings were
made later the same day. The second plan is
separate as well. The [evidence bundle](evidence/README.md) holds the records and numbers for the
[fault and repair](evidence/repair-run.json).

## Run the wire swap yourself

1. With USB unplugged and the servo supply off, swap the green and yellow wire ends at the breadboard.
   Move only those two wires, because a moved LED breaks the saved camera position.
2. Plug USB back in, close heavy apps and keep the phone still.
3. Plan the desk-light idea and approve it. Expect **Behavior mismatch**, then the probe, then the
   **LED mapping repair** card.
4. Approve the repair. A fresh test runs against the same plan with the wires still swapped.
5. Unplug USB and put the two wire ends back. The next plan that runs reinstalls its own firmware.

Each plan gets one repair attempt, so another try needs a new project.

## Seeing SAM 3.1

SAM runs during camera setup, which is the first thing a new plan does. A plan with a good saved
reference skips it unless the view has changed. To show it, approve a new plan. The run card then names SAM,
draws its boxes on the frame they came from, and holds them for five seconds after the reference
is saved. The result page says when SAM took part in that test's camera setup.

The supporting engineering records cover additional [live validation](live-validation.md), the
[full-rig acceptance plan](full-rig.md) and [servo tracking](servo-tracking.md).
