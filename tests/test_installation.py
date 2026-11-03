"""Mocked bootloader operations; no serial device or firmware mutation."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sparkbench.installation import install
from sparkbench.vision import digest


class InstallationTests(unittest.TestCase):
    def scenario(self, codes, same_image=False):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); reference=root/"runs/firmware/led-oled-installed-2026-10-30"
            build=root/"artifact/project/.pio/build/classic-led-oled-runtime"
            reference.mkdir(parents=True); build.mkdir(parents=True)
            for name in ("bootloader.bin","partitions.bin","boot_app0.bin"):
                (reference/name).write_bytes(name.encode()); (build/name).write_bytes(name.encode())
            (build/"firmware.bin").write_bytes(b"synthetic-new-image")
            previous=root/"previous.bin"; previous.write_bytes(b"synthetic-old-image")
            if same_image: previous.write_bytes((build/"firmware.bin").read_bytes())
            artifact={"firmware":"project/.pio/build/classic-led-oled-runtime/firmware.bin",
                      "firmware_sha256":digest(build/"firmware.bin"),"plan_sha256":"a"*64}
            port=Mock(device="/dev/synthetic",vid=0x10C4,pid=0xEA60,hwid="synthetic")
            with patch("sparkbench.installation.ROOT",root), \
                    patch("sparkbench.installation.load_artifact",return_value=({},artifact)), \
                    patch("serial.tools.list_ports.comports",return_value=[port]), \
                    patch("sparkbench.installation.subprocess.run",side_effect=[Mock(returncode=c) for c in codes]) as run:
                result=install(root/"artifact",port.device,previous,digest(previous),root/"output")
                commands=[call.args[0] for call in run.call_args_list]
            return result,commands

    def test_verifies_prior_bytes_then_writes_only_application_then_verifies(self):
        result,commands=self.scenario([0,0,0])
        self.assertEqual(result["status"],"installed_hash_verified")
        self.assertEqual([c[9] for c in commands],["verify-flash","write-flash","verify-flash"])
        self.assertEqual(commands[1][10],"0x10000")
        self.assertFalse(result["boot_partition_nvs_written"])

    def test_prior_mismatch_never_writes_or_restores(self):
        result,commands=self.scenario([1])
        self.assertEqual(result["status"],"incomplete")
        self.assertEqual(len(commands),1)
        self.assertNotIn("recovery",result)

    def test_identical_application_is_verified_without_reflashing(self):
        result,commands=self.scenario([0],same_image=True)
        self.assertEqual(result['status'],'installed_hash_verified')
        self.assertFalse(result['uploaded']);self.assertTrue(result['reused_verified_application'])
        self.assertEqual(len(commands),1);self.assertEqual(commands[0][9],'verify-flash')

    def test_failed_write_restores_and_verifies_previous_application(self):
        result,commands=self.scenario([0,1,0,0])
        self.assertEqual(result["status"],"incomplete")
        self.assertEqual(result["recovery"],"previous_application_restored_hash_verified")
        self.assertEqual([c[9] for c in commands],["verify-flash","write-flash","write-flash","verify-flash"])


if __name__=="__main__": unittest.main()
