# Day 1: component bring-up

**Historical checklist.** Current October 30 state: the LED/OLED diagnostic is
superseded by the generated runtime, and all four scoped LED/OLED stages pass.
Servo actuation remains deferred. Use [live-validation.md](live-validation.md)
and HANDOVER.txt for current commands; the original checklist below is retained
as history, including its earlier combined-firmware instructions.

Prepared October 29, 2026. Today's target is repeatable, manually observed
hardware control. Camera discovery, visual verification, and generated firmware
remain later milestones. At preparation time no camera or servo bracket was
available. The October 30 handover selects the iPhone 15, which the user reports
works natively as a camera on their MacBook Pro. Start with `HANDOVER.txt` for the
current resume steps; no SparkBench frames have been captured yet.

October 30 progress: controller and carrier boot checks passed. The user confirmed
red GPIO25 and green GPIO26 blink patterns, OLED text and a full border, and SG90
motion in both directions with return. OLED is at 0x3C (7-bit), SDA21/SCL22,
working with the SH1106 128x64 profile; exact controller identity is unconfirmed.
The servo uses GPIO27 and an external nominal ~5 V supply with shared ground.
Actual shaft angles, supply voltage, and cable polarity were not measured.
The combined diagnostic below is uploaded with hash verification; six idle
heartbeats and OLED ACK passed. The first combined serial sequence passed with
2123 ms between reported steps. The user confirmed the combined replay's LED
sequence, servo movement and OLED labels all matched. This is manual observation;
video evidence and automatic camera verification remain pending.

## Before connecting peripherals

1. Photograph the arriving controller, carrier, and both sides of the OLED.
2. Confirm the controller family, header labels, carrier fit and USB connector.
   The previously tested board is an S3; a new WROOM board needs a different
   build. The active classic board is now in `hardware/board.json`; the original
   S3 record is in `hardware/boards/original-esp32s3.json`.
   Planning and manual evidence fields are in `hardware/rig.pending.json`;
   that file is not consumed by firmware.
3. Identify the OLED controller, interface, and 3.3 V compatibility. Do not
   infer the driver or pin order from display size alone.
4. Check the servo adapter's 5 V rating, barrel polarity and connector fit.
5. Establish laptop USB communication with the controller alone. No rig GPIO
   assignment is approved until the board is identified.

## Offline software checks

Run these from the project root. They do not open a camera or serial port:

```sh
PYTHONPATH=src .venv/bin/python -m sparkbench doctor
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

The original S3 serial-only firmware can be compiled without uploading:

```sh
PLATFORMIO_CORE_DIR="$PWD/.platformio" .venv/bin/pio run --project-dir firmware/bringup --environment s3-native-usb
```

A separate serial-only profile is prepared for the classic ESP32 board identified
through its CP2102 bridge on October 29 (ESP32-D0WD-V3, 4 MB flash):

```sh
PLATFORMIO_CORE_DIR="$PWD/.platformio" .venv/bin/pio run --project-dir firmware/bringup --environment classic-uart
```

Neither profile drives peripheral GPIOs. Compilation is not confirmation that
the profile matches the arriving board. Upload only after board identification.

## Bring up one component at a time

Disconnect power before changing wiring. Keep photographs and a written pin map
as the setup evolves.

1. **Controller:** upload the matching heartbeat image and confirm repeatable
   serial messages before adding peripherals.
2. **LEDs:** use one red and one green 5 mm LED. Each gets its own 330 ohm series
   resistor: selected GPIO -> resistor -> anode; cathode -> ESP32 GND. These
   indicators are active HIGH, unlike the previously proposed common-anode RGB
   modules. Test red, green, both, and neither. Keep the other pair as spares.
3. **OLED:** use the confirmed pin labels and compatible 3.3 V supply. Scan the
   I2C address and select the actual driver. Display large `SPARKBENCH` / `READY`
   text. This needs new test firmware; the heartbeat image does not do it.
4. **Servo:** further actuation is deferred until the proper bracket is available,
   per the user's preference; do not improvise a mount. When resumed, use the
   separate 5 V supply with common ESP32 ground and keep the external positive
   rail separate from the USB-powered ESP32. Record commanded positions separately
   from measured angles; no calibrated angle measurement is available yet.

## First combined smoke sequence

`firmware/rig_test` implements this hand-written sequence. It boots with outputs
off and requires an explicit `RUN` command. Each step lasts two seconds; after
step four, LEDs turn off, servo PWM is detached, and the OLED shows `COMPLETE`.
`STOP` aborts; `ID` and `STATUS` report state. The user manually confirmed the
combined replay; serial and observation scopes are recorded separately.

| Step | Red | Green | Servo pulse command | OLED |
| --- | --- | --- | --- | --- |
| 1 | ON | OFF | 1500 us | CENTER |
| 2 | OFF | ON | 1300 us | SIDE A |
| 3 | ON | ON | 1700 us | SIDE B |
| 4 | OFF | OFF | 1500 us | CENTER |

These pulses were individually tested using the standalone servo diagnostic.
Pulse commands do not establish measured shaft angles.

Next implement an ID/LED/SERVO/OLED/STOP command interface with bounded probe
timeouts. The heartbeat firmware has none of these commands yet. Do not label
the runtime protected or generated-code-safe until its relevant behavior has
been implemented and tested.

Save serial acknowledgements and manual observations separately. Serial logs
prove communication, not that LEDs, text or motion physically matched. The
existing verifier's synthetic fixtures do not establish physical success.

## User preparation

- Keep the data cable, board and carrier together; keep peripherals disconnected
  for the first USB check.
- Clear a tabletop and sort resistors, LEDs and jumper wires by type.
- Have a small flat screwdriver for power terminals, temporary tape and a piece
  of lightweight card ready.
- Confirm access to the competition's model portal. API access remains untested;
  it is not required for manual component bring-up. Enter credentials locally
  through the selected client's supported configuration when API integration is
  ready; do not include them in photographs or run logs.
