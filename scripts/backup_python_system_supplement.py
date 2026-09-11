"""Back up the observed external Python package paths without changing VM data."""
import os
from pathlib import Path
import backup_biography_to_ssd as core

ROOTS=[Path('/usr/lib/python3/dist-packages'),
       Path('/usr/share/python-babel-localedata'),Path('/usr/share/ieee-data'),
       Path('/var/lib/ieee-data')]


def inventory():
    assert all(p.is_dir() for p in ROOTS),'Expected system dependency directory missing'
    scope=core.inventory_paths()
    return dict(utc=core.now(),host=os.uname().nodename,
                packages=[dict(name='python-system-supplement',paths=[str(p) for p in ROOTS],
                               priority=0,bytes=sum(e.get('bytes',0) for e in scope['entries']))])


core.ROOTS=ROOTS
core.REMOTE_SCRIPT='/home/ubuntu/backup_python_system_supplement.py'
core.inventory=inventory

if __name__=='__main__':core.main()
