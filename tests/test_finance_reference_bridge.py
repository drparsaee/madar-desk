"""Prevent task-finance link loss under real disposable unified storage."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_app


def sale():
    return {'type':'draft.sales.fromTask','eventId':'link-sale-1',
            'projectId':'p-sample','cardId':'example-2',
            'party':{'id':'test-person','name':'Test','reference':'','kind':'customer'},
            'lines':[{'id':'service','description':'Sample','quantity':1,'unitPrice':1500}],
            'discount':0,'tax':0,'advance':0}


class FinanceReferenceBridgeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='madar-finance-ref-host-')
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        bound=patch.object(native_app,'datadir',return_value=self.root)
        bound.start(); self.addCleanup(bound.stop)
        self.bridge=native_app.Bridge()
        self.bridge.enableUnifiedStorage()
        self.document=self.bridge.accountingCommand(sale())['documentId']

    def test_accounting_linked_task_cannot_be_physically_removed(self):
        snapshot=self.bridge._unified_store.load()
        state=deepcopy(self.bridge.getState())
        state['tasks']=[t for t in state['tasks'] if t['id']!='example-2']
        with self.assertRaises(PermissionError):
            self.bridge.saveState(state)
        after=self.bridge._unified_store.load()
        self.assertEqual(after.revision,snapshot.revision)
        self.assertEqual(after.sha256,snapshot.sha256)
        self.assertEqual(self.bridge.accountingRead('p-sample')['documents'][0]['id'],self.document)

    def test_normal_edit_and_soft_trash_keep_document(self):
        state=deepcopy(self.bridge.getState())
        card=next(t for t in state['tasks'] if t['id']=='example-2')
        card['description']='Edited without losing invoice reference'
        card['deleted']=True
        self.assertTrue(self.bridge.saveState(state))
        self.assertEqual(len(self.bridge.accountingRead('p-sample')['documents']),1)
        self.assertTrue(next(t for t in self.bridge.getState()['tasks'] if t['id']=='example-2')['deleted'])


if __name__=='__main__': unittest.main()
