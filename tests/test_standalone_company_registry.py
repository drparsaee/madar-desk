"""Always tests a disposable company hub, never real APPDATA."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from standalone_accounting_company_registry import (
    CompanyRegistryError, StandaloneCompanyRegistry, CompanySessionGuard,
)
from standalone_accounting_desktop import AccountingDesktopAPI


class CompanyRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.registry = StandaloneCompanyRegistry(self.root)

    def test_multiple_company_sqlite_are_isolated(self):
        a = self.registry.create_company("شرکت یک")
        b = self.registry.create_company("شرکت دو")
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual(len(self.registry.list_companies()), 2)
        book_a = self.registry.company_data_directory(a["id"])
        book_b = self.registry.company_data_directory(b["id"])
        self.assertNotEqual(book_a,book_b)
        api_a = AccountingDesktopAPI(book_a)
        api_b = AccountingDesktopAPI(book_b)
        before_a = api_a.standaloneAccountingRead()
        before_b = api_b.standaloneAccountingRead()
        self.assertEqual((before_a["revision"], before_b["revision"]), (0, 0))
        api_a.standaloneAccountingCommand({
            "expectedRevision": 0,
            "command": {
                "type": "party.register", "eventId": "company-a-party",
                "partyId": "company-a-customer", "name": "مشتری اختصاصی الف",
                "kind": "customer",
            }})
        self.assertEqual(api_a.standaloneAccountingRead()["revision"],1)
        self.assertEqual(api_b.standaloneAccountingRead()["revision"],0)
        self.assertNotIn("company-a-customer",
                         api_b.standaloneAccountingRead()["view"]["parties"])
        self.assertTrue((book_a/"standalone-accounting.sqlite3").exists())
        self.assertTrue((book_b/"standalone-accounting.sqlite3").exists())

    def test_duplicate_name_and_invalid_root_are_refused(self):
        self.registry.create_company("آموزش")
        with self.assertRaises(CompanyRegistryError):
            self.registry.create_company("آموزش")
        for name in ("", "\x00bad", "x"*121):
            with self.assertRaises(CompanyRegistryError):
                self.registry.create_company(name)
        with self.assertRaises(CompanyRegistryError):
            StandaloneCompanyRegistry(Path("relative"))
        with self.assertRaises(CompanyRegistryError):
            self.registry.company_data_directory("../escape")

    def test_bidi_spoof_and_persian_visual_duplicate_are_rejected(self):
        self.registry.create_company("شرکت كيان")
        with self.assertRaises(CompanyRegistryError):
            self.registry.create_company("شرکت کیان")
        for value in ("مدار\u202eexe", "حساب\u2067متن\u2069", "نام\u200bمخفی"):
            with self.subTest(value=value), self.assertRaises(CompanyRegistryError):
                self.registry.create_company(value)
        valid=self.registry.create_company('بسته\u200cبندی ایرانی')
        self.assertEqual(valid['name'],'بسته\u200cبندی ایرانی')

    def test_unknown_company_and_corrupt_registry_fail_closed(self):
        with self.assertRaises(CompanyRegistryError):
            self.registry.company_data_directory("0"*32)
        path=self.root/"companies.json"
        path.write_text("{", encoding="utf-8")
        with self.assertRaises(CompanyRegistryError):
            self.registry.list_companies()
        with self.assertRaises(CompanyRegistryError):
            self.registry.create_company("جدید")

    def test_symlink_folder_refused(self):
        other=self.root/"elsewhere"
        other.mkdir()
        link=self.root/"linked"
        try:
            link.symlink_to(other,target_is_directory=True)
        except (OSError,NotImplementedError):
            self.skipTest("Symlinks unavailable in this environment")
        with self.assertRaises(CompanyRegistryError):
            StandaloneCompanyRegistry(link)

    def test_company_guard_exclusive_and_reusable(self):
        first=self.registry.create_company("شرکت برای قفل")
        book=self.registry.company_data_directory(first["id"])
        with CompanySessionGuard(book):
            with self.assertRaises(CompanyRegistryError):
                CompanySessionGuard(book).acquire()
        with CompanySessionGuard(book):
            self.assertTrue((book/".standalone-company-active.lock").is_file())


if __name__=="__main__":
    unittest.main()
