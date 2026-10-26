"""Synthetic-only tests for R19 read-only full-year Parsian archive explorer."""
from hashlib import sha256
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from parsian_source_year_browser import (
    EXPECTED_SHA, SourceArchiveError,list_year_archives,source_table_page)
from standalone_accounting_desktop import AccountingDesktopAPI
from standalone_accounting_identity import LocalCompanyIdentity


class ParsianYearBrowserTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='madar-parsian-raw-year-test-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        folder=self.root/'parsian-source-years'
        folder.mkdir()
        manifest={"source":"ISOLATED_RESTORED_BAK_VERIFIED_20261026",
                  "snapshotMatchesBackup":True,"sourceBackupSha256":EXPECTED_SHA['1404'],
                  "sourceCurrency":"UNKNOWN_RAW_LEGACY_UNITS",
                  "vendorTableCount":1,"vendorRowCount":1,
                  "archiveSha256":"a"*64,"tableCounts":{"Tbl_Private_Notes":1}}
        (folder/'1404-manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        row=json.dumps({'table':'Tbl_Private_Notes','fields':{
            'title':{'t':'text','value':'موارد آزمایشی'},
            'password':{'t':'text','value':'DO_NOT_EXPOSE'},
            'Blob':{'t':'binary','b64':'YWJj'},
            'Amount':{'t':'decimal','text':'125.75'}}},ensure_ascii=False).encode('utf-8')
        with closing(sqlite3.connect(folder/'1404.sqlite3')) as cn:
            cn.execute('CREATE TABLE archive_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            cn.execute('CREATE TABLE archived_rows(source_table TEXT NOT NULL,ordinal INTEGER NOT NULL,typed_raw_json BLOB NOT NULL,row_sha256 TEXT NOT NULL, PRIMARY KEY(source_table,ordinal))')
            cn.executemany('INSERT INTO archive_meta VALUES (?,?)',(
                ('source_class',manifest['source']),
                ('bak_snapshot_equivalence_verified','true'),
                ('financial_posting_authorized','false'),
                ('source_archive_sha256',manifest['archiveSha256'])))
            cn.execute('INSERT INTO archived_rows VALUES (?,?,?,?)',(
                'Tbl_Private_Notes',0,row,sha256(row).hexdigest()))
            cn.commit()

    def test_list_year_table_and_page_are_exact_and_redacted(self):
        years=list_year_archives(self.root)
        self.assertEqual([(r['year'],r['rowCount']) for r in years],[('1404',1)])
        page=source_table_page(self.root,'1404','Tbl_Private_Notes')
        self.assertEqual(page['rows'][0]['fields']['Amount'],'125.75')
        self.assertNotIn('DO_NOT_EXPOSE',str(page))
        self.assertIn('محافظت',page['rows'][0]['fields']['password'])
        self.assertIn('باینری',page['rows'][0]['fields']['Blob'])
        self.assertEqual(source_table_page(self.root,'1404','Tbl_Private_Notes',40)['rows'],[])

    def test_year_and_table_name_injection_are_denied(self):
        for year,table in (('../secret','Tbl_Private_Notes'),('1404','../secret'),
                           ('1404','tbl_unknown')):
            with self.assertRaises(SourceArchiveError):
                source_table_page(self.root,year,table)
        with self.assertRaises(SourceArchiveError):
            source_table_page(self.root,'1404','Tbl_Private_Notes',-1)

    def test_corruption_detection_and_snapshot_provenance(self):
        manifest_file=self.root/'parsian-source-years'/'1404-manifest.json'
        data=json.loads(manifest_file.read_text('utf-8'))
        data['sourceBackupSha256']='0'*64
        manifest_file.write_text(json.dumps(data),encoding='utf-8')
        with self.assertRaises(SourceArchiveError):list_year_archives(self.root)

    def test_backend_admin_only_enforcement(self):
        store=LocalCompanyIdentity(self.root)
        store.add_user('owner','1234','admin',job_title='مدیر')
        owner_session=store.login('owner','1234')
        store.add_user('viewer1','5678','viewer',administrator=owner_session)
        viewer_session=store.login('viewer1','5678')
        owner=AccountingDesktopAPI(self.root,identity_store=store,
            identity_token=owner_session,authenticated_user=store.require_session(owner_session))
        viewer=AccountingDesktopAPI(self.root,identity_store=store,
            identity_token=viewer_session,authenticated_user=store.require_session(viewer_session))
        self.assertEqual(owner.standaloneAccountingParsianArchiveIndex()[0]['year'],'1404')
        with self.assertRaises(PermissionError):viewer.standaloneAccountingParsianArchiveIndex()
        with self.assertRaises(PermissionError):
            viewer.standaloneAccountingParsianArchiveRows('1404','Tbl_Private_Notes',0)


if __name__=='__main__':unittest.main()
