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
| The agent supports a human fix and re-test | The dashboard can wait for an operator and re-test the same approved plan. A single hero-project fault, explanation, repair and passing re-test is still pending on hardware. |

Verification covers sampled settled windows in the calibrated view. The submitted bench is the
classic ESP32, two LEDs and an OLED. Muse Spark returns structured data, and a trusted renderer
writes the firmware. The operator handles any physical changes. See the [recorded evidence](evidence/README.md)
and [demo script](demo.md).

## Submission checklist

The official deadline is Wednesday 4 November at 9:00 PM ET, Thursday 5 November at 8:00 AM
in Dhaka. [Event schedule](https://dev.meta.ai/events/global-hackathon).

- [ ] Select **Indie Developer** and **Push the Frontier**. List all human contributors.
- [ ] Check the signed-in submission form for required fields and link visibility.
- [ ] Record and upload the demo, then verify the link as a signed-out viewer.
- [ ] Make the repository public when ready and verify that the evidence link opens.
- [ ] Paste the [form answers](submission.md), add the video link to the form and README, and review the permission field.
- [ ] Include the dated [engineering log](history.md) to identify the work built during the event.
- [ ] Complete any separate participant credit claim or optional prize entry that applies.

For the demo, spend most of the time on the plan, its camera evidence, and one practical
diagnosis. The [timed script](demo.md) has a recorded cut and a conditional sequence for the
joint bench session.
