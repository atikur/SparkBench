"""No physical I/O: exercise the safeguards before running a diagnostic."""
import io
import unittest
from unittest.mock import Mock

from sparkbench.led_oled import IDENTITY, Journal, check_sequence, ready_identity


class LedOledSafeguards(unittest.TestCase):
    def test_only_exact_idle_identity_with_ack_can_authorize(self):
        self.assertTrue(ready_identity(IDENTITY))
        for line in ("SPARKBENCH RIG_TEST MODE:IDLE PWM:OFF OLED:ACK",
                     IDENTITY.replace("IDLE", "RUNNING"),
                     IDENTITY.replace("ACK", "MISSING"),
                     "prefix " + IDENTITY):
            self.assertFalse(ready_identity(line))

    def test_start_requires_both_identity_and_live_frames_and_is_once_only(self):
        connection = Mock()
        journal = Journal(connection, io.StringIO())
        for identity, frames in ((False, False), (True, False), (False, True)):
            journal.verified, journal.camera_ready = identity, frames
            with self.assertRaises(ValueError):
                journal.send("VISUAL")
        connection.write.assert_not_called()
        journal.verified = journal.camera_ready = True
        journal.send("VISUAL")
        connection.write.assert_called_once_with(b"VISUAL\n")
        with self.assertRaises(ValueError):
            journal.send("VISUAL")

    def test_combined_run_and_servo_commands_are_never_sent(self):
        connection = Mock()
        journal = Journal(connection, io.StringIO())
        journal.verified = journal.camera_ready = True
        for command in ("RUN", "CENTER", "TEST", "VISUAL\nRUN"):
            with self.assertRaises(ValueError):
                journal.send(command)
        connection.write.assert_not_called()

    def test_done_alone_and_missing_step_cannot_pass_serial_check(self):
        expected = [{"step": 1, "red": False, "green": False, "oled_text": "DARK"}]
        self.assertEqual(check_sequence(["VISUAL_DONE"], expected)["status"], "incomplete")
        lines = ["VISUAL_STEP:1 RED:0 GREEN:0 TEXT:DARK UPTIME_MS:1000",
                 "VISUAL_STOPPED STATUS:COMPLETE RED:0 GREEN:0 UPTIME_MS:4000",
                 "VISUAL_DONE"]
        self.assertEqual(check_sequence(lines, expected)["status"], "pass")
        self.assertEqual(check_sequence(lines + lines, expected)["status"], "incomplete")
        self.assertEqual(check_sequence(lines + ["SPARKBENCH LED_OLED_TEST BOOT"], expected)["status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
