import io
import json
from pathlib import Path
import tempfile
import tarfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from scripts import backup_biography_to_ssd as backup


class BackupTests(unittest.TestCase):
    def test_round_trip_and_corruption_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'source'
            root.mkdir()
            (root / 'nested').mkdir()
            payload = bytes(range(256)) * 8192
            (root / 'nested' / 'model.bin').write_bytes(payload)
            (root / 'empty').write_bytes(b'')
            out = io.BytesIO()
            with patch.object(backup, 'ROOTS', [root]), patch.object(backup.sys, 'stdout', SimpleNamespace(buffer=out)), patch.object(backup.os, 'uname', return_value=SimpleNamespace(nodename='fixture'), create=True):
                backup.stream([str(root)])
            archive = Path(tmp) / 'archive.tar.gz'
            archive.write_bytes(out.getvalue())
            result = backup.verify(archive)
            self.assertEqual(result['files'], 2)
            self.assertEqual(result['uncompressed_bytes'], len(payload))
            archive.write_bytes(out.getvalue()[:len(out.getvalue()) // 2])
            with self.assertRaises((EOFError, OSError, ValueError, tarfile.TarError)):
                backup.verify(archive)


if __name__ == '__main__':
    unittest.main()
