from copy import deepcopy
import unittest

from finance_reference_guard import ensure_finance_references_preserved


def fixture():
    old = {'projects': [{'id': 'p'}, {'id': 'q'}],
           'tasks': [{'id': 'a', 'projectId': 'p', 'title': 'A'},
                     {'id': 'b', 'projectId': 'p', 'title': 'B'}]}
    finance = {'contracts': [], 'invoices': [], 'ledger': [], 'cardCosts': {},
               'accountingSources': {
                   'doc-1': {'projectId': 'p', 'cardIds': ['a'],
                             'sourceIds': ['task:a'], 'fingerprint': 'x',
                             'kind': 'sales'}}}
    return old, finance


class ReferenceGuardTests(unittest.TestCase):
    def test_preserves_edit_and_soft_trash_of_document_linked_card(self):
        old, money = fixture()
        new = deepcopy(old)
        new['tasks'][0].update(title='Revised', deleted=True)
        self.assertTrue(ensure_finance_references_preserved(old, new, money))
        self.assertEqual(old['tasks'][0]['title'], 'A')

    def test_refuses_reparent_or_delete_linked_card(self):
        old, money = fixture()
        new = deepcopy(old)
        new['tasks'][0]['projectId'] = 'q'
        with self.assertRaises(PermissionError):
            ensure_finance_references_preserved(old, new, money)
        new = deepcopy(old)
        new['tasks'] = new['tasks'][1:]
        with self.assertRaises(PermissionError):
            ensure_finance_references_preserved(old, new, money)

    def test_refuses_project_delete_when_ledger_or_invoice_exists(self):
        old, money = fixture()
        money['invoices'] = [{'cardId':'a','projectId':'p'}]
        new = deepcopy(old)
        new['projects'] = [{'id':'q'}]
        with self.assertRaises(PermissionError):
            ensure_finance_references_preserved(old, new, money)

    def test_refuses_moving_card_with_cost_override_even_without_invoice(self):
        old, money = fixture()
        money['accountingSources'] = {}
        money['cardCosts'] = {'b': {'actualDirect': 15}}
        new = deepcopy(old)
        new['tasks'][1]['projectId'] = 'q'
        with self.assertRaises(PermissionError):
            ensure_finance_references_preserved(old, new, money)

    def test_unlinked_reparent_allowed(self):
        old, money = fixture()
        new = deepcopy(old)
        new['tasks'][1]['projectId'] = 'q'
        self.assertTrue(ensure_finance_references_preserved(old, new, money))

    def test_historical_orphan_does_not_break_every_save(self):
        old, money = fixture()
        money['accountingSources']['doc-2'] = {'projectId': 'p',
          'cardIds': ['already-absent'], 'sourceIds': [],
          'fingerprint': 'x', 'kind': 'sales'}
        self.assertTrue(ensure_finance_references_preserved(old, deepcopy(old), money))

if __name__ == '__main__':
    unittest.main()
