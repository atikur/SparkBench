# Start SparkBench from a fresh checkout

From the checkout root, start the local dashboard with Python 3.11.

```sh
PYTHONPATH=src python3.11 -m sparkbench dashboard
```

Open `http://127.0.0.1:8765`. The page and its local assets load with the Python standard library. A source-only checkout starts with no saved projects or plans. Its three catalog entries are marked **Evidence unavailable** until their original local records are present. The submission's selected evidence can be reviewed separately. The bench status is unavailable until the saved board record can be matched to its application binary.

You can validate the example plan and render its firmware source without credentials or build tools. Choose a new output directory each time.

```sh
PYTHONPATH=src python3.11 -m sparkbench build \
  --plan examples/led_oled_plan.json --render-only \
  --output runs/source-only-render
```

On macOS, `bash tools/bootstrap_macos.sh` uses an installed Python 3.11 with OpenSSL to create `.venv`, install the project with its pinned PlatformIO and esptool dependencies, run the host tests, and print local readiness. Installing dependencies requires network access. The dashboard and HTTP tests require permission to listen on loopback. Use `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests` to repeat the tests after setup. Tests that use private recorded captures are skipped when those captures are absent.

For planning and live OLED transcription, configure `META_API_KEY` and `META_MODEL=muse-spark-1.3-contributor` in a local `.env` file or process environment. The dashboard reads those values when it starts a request. Browse saved evidence without a Meta key. Building a binary also requires the pinned ESP32 Arduino platform and U8g2 library in [the runtime's PlatformIO configuration](../firmware/runtime/platformio.ini), which PlatformIO can fetch when they are absent from its cache.

## Restore a commissioned bench

The demonstrated hardware is the classic 4 MB ESP32 with CP2102 USB serial, the documented GPIO25/GPIO26 LED and I²C OLED wiring, and an iPhone Continuity Camera on a fixed mount. Use the [wiring and build guide](build-guide.md) for the connections. Live operation requires macOS with Apple Command Line Tools for the native camera and image helpers. Keep the servo supply off.

When moving the same commissioned bench to a new checkout, restore these local files from its verified records at their recorded relative paths:

| Local asset | Why the live path needs it |
| --- | --- |
| `hardware/board.json` and its `active_firmware.application_binary` | The board record names the saved bytes of the currently installed application. The dashboard checks the local binary against `active_firmware.firmware_sha256` before relying on the record. |
| `runs/firmware/led-oled-installed-2026-10-30/{bootloader.bin,partitions.bin,boot_app0.bin}` | This is the installer’s trusted boot layout reference. The new build's bootloader and partition table must match the reference. Before writing, esptool checks all three existing boot regions and the previous application against the saved bytes. |
| The reviewed plan and its compiled artifact, or a reviewed plan to compile on the new host | Installation verifies the artifact's plan, trusted runtime files and binary hashes. A subsequent camera test requires the exact installed firmware identity. |
| `hardware/oled-reader.policy.json`, the policy's `calibration` file and its referenced camera image | The policy freezes the reader, prompt and calibration hash. The analyzer checks the reference image, camera ID, macOS version and native reader source against calibration. |

The source checkout omits the local `runs/` assets above. A saved board record is valid for its specific hardware and firmware state. A blank or different board needs separately verified commissioning and a recovery image before the dashboard's app-only installer can take over. The installer verifies the existing layout, writes the application at `0x10000`, verifies the result, and attempts to restore the previous application if a write or verification fails.

To check camera access and select the current devices, run these commands from the project root:

```sh
PYTHONPATH=src .venv/bin/python -m sparkbench camera authorize
PYTHONPATH=src .venv/bin/python -m sparkbench camera list
.venv/bin/python -m serial.tools.list_ports --verbose
```

Choose the exact iPhone and CP2102 from the current listings. With both LEDs and the OLED visible, keep the phone and bench fixed. The dashboard's camera check compares the current idle view with the frozen calibration before a bench run. A camera-only capture can help inspect framing. It establishes camera access and visibility.

## Prepare a changed camera view

Use `.venv/bin/python tools/calibrate_view.py --help` for the supervised calibration procedure. It requires a completed capture from an authorized bounded LED/OLED run on the commissioned bench. An existing installation with a matching artifact can supply that capture even when its old view no longer matches. The lower-level `sparkbench.runtime_io.acquire` API captures the protected runtime's LED/OLED sequence before analysis. It requires the explicit port, camera ID, compiled artifact and new output directory. It verifies the running identity and camera readiness before it starts the sequence.

Mark the LED centers and the four OLED corners in a saved frame, and label multiple on/off samples for each LED from the actual images. Check the geometry and scores with the calibration tool's `--probe` option. It writes a candidate policy with `--labels`. Add `--promote` to the labelled invocation to select it locally, using a new output directory if you already wrote a candidate. For a position-only change on the same bench, `.venv/bin/python tools/refresh_reference.py --help` documents how to carry forward previous LED thresholds using checked all-off frames. Freeze the selected policy before acquiring a separate test capture.

In the dashboard, choose a reviewed plan and follow [the bench workflow](dashboard.md). A run can report a pass, mismatch or incomplete result. The result applies to its recorded sample windows and approved LED/OLED behavior.
