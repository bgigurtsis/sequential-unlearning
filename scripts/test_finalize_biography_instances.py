"""Exercise destructive-action gates with mocked AWS; never contacts AWS."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import finalize_biography_instances as finalizer


class FinalizationTests(unittest.TestCase):
    def exercise(self,*,protected=True,wrong_volume=False,copy_error=False,missing_report=False,stale_report=False):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            cloud={'system_supplements':{}}
            for role in ['gpu1','gpu2']:
                for scope in ['cloud','system']:
                    folder=root/scope/role;folder.mkdir(parents=True)
                    (folder/'complete.json').write_text(json.dumps({'inventory_packages':1,'utc':finalizer.now()}))
                cloud[role]={'packages':[{}],'shared_packages':[],'independent_source_paths_matched':1}
                cloud['system_supplements'][role]={'independent_source_paths_matched':1}
            for mode,result in [('cloud',cloud),('repository',{'files':1,'errors':['mismatch'] if copy_error else [],'excluded_links':[]})]:
                if not (missing_report and mode=='repository'):
                    timestamp='2000-01-01T00:00:00+00:00' if stale_report and mode=='cloud' else finalizer.now()
                    (root/(mode+'-verification-final.json')).write_text(json.dumps({'mode':mode,'result':result,'utc':timestamp}))
            instances=[{'InstanceId':key,'State':{'Name':'running'},
                        'BlockDeviceMappings':[{'Ebs':{'VolumeId':'wrong' if wrong_volume else volume,
                                                       'DeleteOnTermination':not protected}}]}
                       for key,volume in finalizer.INSTANCES.items()]
            calls=[]
            def fake_aws(operation,args,folder):
                calls.append(operation)
                return {'Reservations':[{'Instances':instances}]} if operation=='describe-instances' else {}
            argv=['finalize','--action','terminate','--backup-root',str(root),'--receipt-directory',str(root/'receipts')]
            with patch('sys.argv',argv),patch.object(finalizer,'aws',side_effect=fake_aws):
                if protected and not any([wrong_volume,copy_error,missing_report,stale_report]):
                    finalizer.main()
                    self.assertEqual(calls,['describe-instances','terminate-instances'])
                else:
                    with self.assertRaises((ValueError,FileNotFoundError)):finalizer.main()
                    self.assertNotIn('terminate-instances',calls)

    def test_protected_roots_and_complete_backup_allow_approved_action(self):self.exercise()
    def test_unprotected_root_blocks_termination(self):self.exercise(protected=False)
    def test_wrong_volume_blocks_termination(self):self.exercise(wrong_volume=True)
    def test_mismatched_repository_blocks_termination(self):self.exercise(copy_error=True)
    def test_missing_report_blocks_termination(self):self.exercise(missing_report=True)
    def test_stale_cloud_report_blocks_termination(self):self.exercise(stale_report=True)


if __name__=='__main__':unittest.main()
