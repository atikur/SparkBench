# SparkBench demo script

The recorded cut takes about 2 minutes 35 seconds. Use desktop width, show the plan and camera
frames large enough to read, and place a persistent date and run label on each recorded example.
The [evidence index](evidence/README.md) provides the visual assets and provenance.

| Time | Screen | Narration |
| --- | --- | --- |
| 0:00–0:15 | Title over the home page. “SparkBench · Built during the Meta Global AI Developer Hackathon · 27 Oct – 4 Nov 2026” | “A build and a serial response tell us the board is running. SparkBench checks what the board actually does.” |
| 0:15–0:40 | Describe the desk light, then show the saved READY/BUSY/DONE plan. Highlight the LEDs, OLED labels and durations. | “I ask for READY with the green LED, BUSY with the red LED, and DONE with both off. Muse Spark drafts the plan, which I review before running it.” |
| 0:40–1:00 | Show **Approve plan and run on the bench** and the agent timeline. Label any cut or sped-up footage. | “One approval starts the workflow. Local code checks the camera, builds and installs when needed, and checks the application identity before the test.” |
| 1:00–1:30 | **Recorded 4 Nov · READY/BUSY/DONE · 290be0…** Show the pass counts and one frame per step. [READY](evidence/hero-ready.jpg) · [BUSY](evidence/hero-busy.jpg) · [DONE](evidence/hero-done.jpg) | “This run passed all 26 sampled observations. The LEDs are measured from pixels. Muse Spark reads each eligible OLED crop without the expected label. Local code compares the observations with the approved plan.” |
| 1:30–1:55 | **Separate recording · 3 Nov · intentional LED swap.** Show the recorded LED observations beside the [display crop](evidence/wiring-fault.png). | “We also deliberately swapped the LED connections in a separate test. The verifier recorded 36 wrong-channel findings across 47 samples.” |
| 1:55–2:20 | Show the [incomplete OLED result](evidence/incomplete.json) and its [display crop](evidence/incomplete.png). Cut to **Separate recording · camera geometry** and show the [saved explanation](evidence/diagnosis-accepted.json). Highlight its cited frame IDs and next check. | “When the OLED readings are missing, the run stays incomplete. In another incomplete run, Muse Spark used the saved frames and findings to suggest a camera check. The explanation leaves the verdict intact.” |
| 2:20–2:35 | Close on the plan, evidence index and repository link. | “The dashboard can wait for the operator and test the same plan again. You can inspect the saved pass, fault and incomplete results with their source records.” |

For an entirely offline recording, use the saved project and evidence screens. On a source-only
checkout, show the saved frames and excerpts from the evidence index. Record the approval button
and timeline as a walkthrough of the implemented workflow. Label historical UI screenshots and
avoid presenting footage from different runs as one continuous session.

## Optional joint bench recording

Use this cut once the phone view matches its calibration and the operator is available to make
and restore the wiring change.

1. On the correctly wired bench, run the approved READY/BUSY/DONE plan and save the pass.
2. With the bench stopped and powered down for rewiring, have the operator swap only the two LED
   connections. Restore power and re-run the same plan. Save the mismatch and check that the
   compared frames actually measured the fault.
3. Open the explanation and show what it cites and what it proposes checking. Use the response
   that the run actually saved.
4. Have the operator restore the original wiring with the bench powered down. Restore power,
   confirm the operator step and re-test the same plan. Save and show both attempt records and
   the new measured outcome.
5. Include the repair sequence in the demo once the mismatch, explanation, operator action and
   passing re-test are recorded. Use the recorded cut above if any link in that sequence is missing.

The supporting engineering records cover additional [live validation](live-validation.md), the
[full-rig acceptance plan](full-rig.md) and [servo tracking](servo-tracking.md).
