"""Synthetic serial/lifecycle checks, never physical verification."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

from sparkbench.installation import verify_identity
from sparkbench.runtime_io import identity
from sparkbench.dashboard.lifecycle import firmware_status

class IdentityTests(unittest.TestCase):
    def scenario(self, correct=True):
        class Connection:
            is_open=False;pending=b'';commands=[]
            def open(self):self.is_open=True
            def close(self):self.is_open=False
            @property
            def in_waiting(self):return len(self.pending)
            def read(self,size):data=self.pending[:size];self.pending=self.pending[size:];return data
            def write(self,data):self.commands.append(data);self.pending=(identity('a'*64 if correct else 'b'*64)+'\n').encode()
            def flush(self):pass
        connection=Connection();clock=[0]
        def tick():clock[0]+=.1;return clock[0]
        with tempfile.TemporaryDirectory() as d,patch('serial.tools.list_ports.comports',return_value=[Mock(device='/dev/synthetic',vid=0x10C4,pid=0xEA60)]),patch('serial.Serial',return_value=connection),patch('sparkbench.installation.time.monotonic',side_effect=tick):
            result=verify_identity('/dev/synthetic','a'*64,Path(d)/'identity')
            self.assertTrue((Path(d)/'identity/uart.jsonl').exists());self.assertFalse(connection.is_open)
        self.assertEqual(connection.commands,[b'ID\n']);self.assertFalse(connection.dtr);self.assertFalse(connection.rts);return result
    def test_exact_idle_identity_is_uart_only_and_sends_only_id(self):
        result=self.scenario();self.assertEqual(result['status'],'pass');self.assertIn('not physical',result['scope']);self.assertEqual(result['serial_commands_sent'],['ID'])
    def test_wrong_plan_identity_is_never_confirmed(self):self.assertEqual(self.scenario(False)['status'],'incomplete')
    def test_absent_cp2102_never_opens_serial(self):
        with tempfile.TemporaryDirectory() as d,patch('serial.tools.list_ports.comports',return_value=[]),patch('serial.Serial') as serial:
            result=verify_identity('/dev/synthetic','a'*64,Path(d)/'identity');self.assertEqual(result['status'],'incomplete');serial.assert_not_called()

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.project={'accepted':{'sha256':'c'*64},'firmware_links':[{'proposal_id':'b'*32,'accepted_sha256':'c'*64}]}
        self.planner=Mock();self.planner.get.return_value={'id':'b'*32,'status':'ready','review_status':'reviewed','plan_sha256':'a'*64}
        self.jobs=[{'id':'2'*32,'action':'install','status':'installed','stage':'installed','proposal_id':'b'*32,'plan_sha256':'a'*64,'firmware_sha256':'f'*64},
                   {'id':'1'*32,'action':'compile','status':'compiled','stage':'compiled','proposal_id':'b'*32,'plan_sha256':'a'*64,'firmware_sha256':'f'*64}]
        self.active={'proposal_id':'b'*32,'plan_sha256':'a'*64,'firmware_sha256':'f'*64,'runtime_identity':{'status':'pass'}}
        self.execution=Mock();self.execution.list.side_effect=lambda:copy.deepcopy(self.jobs);self.execution._board.side_effect=lambda:({'active_firmware':copy.deepcopy(self.active)},None)
    def status(self):return firmware_status(self.project,self.planner,self.execution)
    def test_confirmed_installation_does_not_become_camera_verification(self):
        result=self.status();self.assertEqual(result['state'],'installed');self.assertTrue(result['matches_recorded_installation']);self.assertIsNone(result['camera_result'])
    def test_another_board_version_does_not_match_this_project(self):
        self.active['firmware_sha256']='e'*64;self.assertEqual(self.status()['state'],'install');self.assertFalse(self.status()['matches_recorded_installation'])
    def test_missing_uart_confirmation_requires_identity_check(self):
        self.active.pop('runtime_identity');self.assertEqual(self.status()['state'],'check_identity')
    def test_new_accepted_brief_does_not_inherit_old_installation(self):
        self.project['accepted']['sha256']='d'*64;result=self.status();self.assertEqual(result['state'],'prepare_proposal');self.assertIsNone(result['build']);self.assertFalse(result['matches_recorded_installation'])
    def test_unconfirmed_recovery_blocks_recorded_version_confidence(self):
        self.jobs.insert(0,{**self.jobs[0],'id':'3'*32,'status':'incomplete'})
        self.execution.diagnostics.return_value={'installation':{'status':'incomplete','write_attempted':True,'recovery':'incomplete: synthetic restore error'}}
        self.assertEqual(self.status()['state'],'firmware_unconfirmed');self.assertFalse(self.status()['matches_recorded_installation'])
    def test_identity_error_after_verified_flash_is_not_unconfirmed_recovery(self):
        self.jobs.insert(0,{**self.jobs[0],'id':'3'*32,'status':'incomplete'})
        self.execution.diagnostics.return_value={'installation':{'status':'installed_hash_verified','write_attempted':True,'recovery':None}}
        self.assertEqual(self.status()['state'],'installed')

if __name__=='__main__':unittest.main()
