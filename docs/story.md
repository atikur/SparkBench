# SparkBench submission story

SparkBench gives makers and students a way to check whether the behavior they asked for actually
ran on a physical board. Describe the behavior in plain language, review the plan Muse Spark
proposes, and approve a bench run. Trusted local code builds and installs the application. A
fixed iPhone camera records the ESP32, two LEDs and OLED while the plan runs. Muse Spark reads
the OLED crop without the expected label. Local code measures the LEDs and compares both
observations with the approved plan.

## Claims and evidence

| Claim | Evidence to show |
| --- | --- |
| Muse Spark turns plain language into a bounded plan | Show the READY/BUSY/DONE step table. The planner also matched independently frozen expectations in eight benchmark cases. |
| The verifier measured the hero project's behavior | The 4 November READY/BUSY/DONE run passed all 26 sampled observations, with zero mismatches and zero unknowns. |
| The camera caught an intentional physical fault | In a separate 3 November wiring-swap capture, 36 wrong-channel findings appeared across 47 samples. That test measured the LEDs. |
| Unreadable evidence stays incomplete | In a separate historical LED/OLED analysis, 45 of 48 OLED readings were unknown. |
| Muse Spark can suggest a next check grounded in evidence | Show a saved explanation of a separate incomplete run and its cited frames. The explanation is advisory, and invalid citations are rejected. |
| The agent investigates a real fault and recovers | On 4 November a disclosed wire swap gave 38 mismatched readings. A fixed probe and Muse Spark's proposal identified the swapped pins, the operator approved, and a fresh test passed 27 of 27 samples with the wires still swapped. |
| The agent supports a human fix and re-test | The same night, a second plan's mismatch was fixed by hand and passed 27 of 27 samples on retest, after two recorded incomplete tests. |

Verification covers sampled settled windows in the calibrated view. The submitted bench is the
classic ESP32, two LEDs and an OLED. Muse Spark returns structured data, and a trusted renderer
writes the firmware. The operator handles any physical changes. See the [recorded evidence](evidence/README.md)
and [demo video guide](demo.md).

## Submission checklist

The official deadline is Wednesday 4 November at 9:00 PM ET, Thursday 5 November at 8:00 AM
in Dhaka. [Event schedule](https://dev.meta.ai/events/global-hackathon).

- [ ] Select **Indie Developer** and **Push the Frontier**. List all human contributors.
- [ ] Check the signed-in submission form for required fields and link visibility.
- [x] Record and upload the demo, then verify the link as a signed-out viewer: https://youtu.be/y6KSh-sNYX0
- [ ] Make the repository public when ready and verify that the evidence link opens.
- [ ] Paste the [form answers](submission.md), add the video link to the form and README, and review the permission field.
- [ ] Include the dated [engineering log](history.md) to identify the work built during the event.
- [ ] Complete any separate participant credit claim or optional prize entry that applies.

The demo spends most of its time on the live fault and recovery. The [demo video guide](demo.md)
lists what each part shows and which recording it comes from, with the wire swap disclosed on screen.
