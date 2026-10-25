from pathlib import Path
import tempfile
import unittest

from parsian_backup_probe import identify_backup


class ProbeTests(unittest.TestCase):
    def test_tape_signature_only_classifies_not_imports(self):
        with tempfile.TemporaryDirectory(prefix='parsian-fixture-') as temp:
            test=Path(temp)/'synthetic.bak'
            test.write_bytes(b'TAPE'+bytes(8192))
            result=identify_backup(test)
            self.assertEqual(result['format'],'sqlserver_media_backup')
            self.assertFalse(result['canImportIntoMadar'])
            self.assertEqual(result['bytes'],8196)
    def test_unknown_and_too_small_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix='parsian-fixture-') as temp:
            test=Path(temp)/'unknown.bak'
            test.write_bytes(bytes(2048))
            self.assertEqual(identify_backup(test)['format'],'unknown_backup')
            test.write_bytes(b'TAPE')
            with self.assertRaises(ValueError):
                identify_backup(test)
    def test_unsupported_extension_rejected(self):
        with tempfile.TemporaryDirectory(prefix='parsian-fixture-') as temp:
            test=Path(temp)/'fake.mdf'
            test.write_bytes(b'TAPE'+bytes(8192))
            with self.assertRaises(ValueError):
                identify_backup(test)


if __name__=='__main__': unittest.main()
