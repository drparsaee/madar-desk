import tempfile
import unittest
from pathlib import Path

from standalone_legacy_party_import import import_to_new_database
from standalone_accounting import StandaloneAccountingStore


class LegacyPartyImportTests(unittest.TestCase):
    def test_preview_then_import_to_new_db(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'export.csv'
            source.write_text('partyId,name,kind\nold-1,Test Customer,customer\nold-2,Test Vendor,vendor\n', encoding='utf-8')
            dest = root / 'standalone-accounting.sqlite3'
            self.assertEqual(import_to_new_database(source, dest)['count'], 2)
            self.assertFalse(dest.exists())
            self.assertEqual(import_to_new_database(source, dest, confirmed=True)['count'], 2)
            state = StandaloneAccountingStore(dest).read(actor='admin', accounts={'admin': {'username':'admin','role':'admin'}})
            self.assertEqual(state['view']['currency'], 'RIAL')
            self.assertIn('old-1', state['view']['parties'])
            with self.assertRaises(FileExistsError):
                import_to_new_database(source, dest, confirmed=True)

    def test_bad_csv_never_creates_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'bad.csv'
            source.write_text('partyId,name,kind\nold-1,One,vendor\nold-1,Two,vendor\n', encoding='utf-8')
            dest = root / 'standalone-accounting.sqlite3'
            with self.assertRaises(ValueError):
                import_to_new_database(source, dest, confirmed=True)
            self.assertFalse(dest.exists())
