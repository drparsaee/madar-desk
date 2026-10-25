"""Madar supplier work: quantity-only receipt, then price, then real GL bill."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_app
from finance import empty_finance_state, validate_finance_state
from purchase_intake import empty_intakes, apply_intake


def create(eid='work-create'):
    return {'type':'intake.create', 'eventId':eid, 'intakeId':'intake-1',
            'projectId':'p-sample','cardId':'example-2','stepId':'test-step',
            'quantity':7,
            'supplier':{'id':'paper-company','name':'Paper Company','kind':'supplier',
                        'reference':''}}


class ProcurementTests(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory(prefix='madar-procurement-')
        self.addCleanup(root.cleanup)
        patch_root = patch.object(native_app, 'datadir', return_value=Path(root.name))
        patch_root.start()
        self.addCleanup(patch_root.stop)
        self.bridge = native_app.Bridge()
        self.bridge.enableUnifiedStorage()
        state = self.bridge.getState()
        task = next(t for t in state['tasks'] if t['id'] == 'example-2')
        task['checklist'].append({'id':'test-step','text':'Glue packaging boxes','done':False})
        self.bridge.saveState(state)

    def test_unpriced_has_no_liability_then_price_creates_draft_without_journal(self):
        first = self.bridge.accountingCommand(create())
        self.assertEqual(first['bookedPayable'],0)
        self.assertEqual(first['status'],'unpriced')
        self.assertEqual(first,self.bridge.accountingCommand(create()))
        view = self.bridge.accountingRead('p-sample')
        self.assertEqual(len(view['purchaseIntakes']),1)
        self.assertIsNone(view['purchaseIntakes'][0]['unitPrice'])
        self.assertEqual(view['documents'],[])
        self.assertEqual(next(p for p in view['balances'] if p['partyId']=='paper-company')['payable'],0)
        with self.assertRaises(ValueError):
            self.bridge.accountingCommand({'type':'intake.convert','eventId':'conv0','intakeId':'intake-1'})
        priced = self.bridge.accountingCommand({
            'type':'intake.price','eventId':'price1','intakeId':'intake-1','unitPrice':123})
        self.assertEqual(priced['proposedTotal'],861)
        self.assertEqual(priced['bookedPayable'],0)
        converted = self.bridge.accountingCommand({
            'type':'intake.convert','eventId':'convert1','intakeId':'intake-1'})
        self.assertEqual(converted['total'],861)
        self.assertEqual(self.bridge.accountingRead('p-sample')['documents'][0]['status'],'Draft')
        self.assertEqual(self.bridge.accountingCommand({
            'type':'intake.convert','eventId':'convert1','intakeId':'intake-1'})['documentId'],
            converted['documentId'])
        self.assertEqual(self.bridge.accountingRead('p-sample')['balances'][0]['payable'],0)
        self.bridge.accountingCommand({'type':'document.review','eventId':'review-intake',
                                       'documentId':converted['documentId'],'projectId':'p-sample'})
        self.bridge.accountingCommand({'type':'document.issue','eventId':'issue-intake',
                                       'documentId':converted['documentId'],'projectId':'p-sample',
                                       'postingDate':datetime.now(timezone.utc).date().isoformat()})
        totals = self.bridge.accountingRead('p-sample')['balances']
        self.assertEqual(next(x for x in totals if x['partyId']=='paper-company')['payable'],861)
        restart = native_app.Bridge()
        self.assertEqual(restart.accountingRead('p-sample')['purchaseIntakes'][0]['status'],'converted')
        self.assertTrue(restart._unified_store.integrity_check())

    def test_refuse_forged_source_or_duplicated_intake(self):
        snapshot = self.bridge._unified_store.load()
        fake=create()
        fake['stepId']='not-a-step'
        with self.assertRaises(ValueError):
            self.bridge.accountingCommand(fake)
        self.assertEqual(self.bridge._unified_store.load().revision,snapshot.revision)
        self.bridge.accountingCommand(create())
        duplicate=create('new-event')
        duplicate['intakeId']='second-intake'
        with self.assertRaises(ValueError):
            self.bridge.accountingCommand(duplicate)
        with self.assertRaises(ValueError):
            self.bridge.accountingCommand({**create(),'quantity':11})
        self.assertEqual(self.bridge.accountingRead('p-sample')['purchaseIntakes'][0]['quantity'],7)

    def test_unpriced_intake_preserves_task_on_project_change_or_deletion(self):
        self.bridge.accountingCommand(create())
        before = self.bridge._unified_store.load()
        modified = deepcopy(self.bridge.getState())
        task = next(t for t in modified['tasks'] if t['id']=='example-2')
        task['projectId']='p-personal'
        target = next(b for b in modified['boards'] if b['projectId']=='p-personal')
        task['boardId']=target['id']
        task['listId']=target['stages'][0]['id']
        task['labelIds']=[]
        task['customFieldValues']={}
        with self.assertRaises(PermissionError):
            self.bridge.saveState(modified)
        self.assertEqual(self.bridge._unified_store.load().revision,before.revision)
        self.assertTrue(validate_finance_state(self.bridge._load_finance()))

    def test_unpriced_source_cancel_does_not_accrue_payable(self):
        self.bridge.accountingCommand(create())
        cancelled=self.bridge.accountingCommand({
            'type':'intake.cancel','eventId':'cancel1','intakeId':'intake-1'})
        self.assertEqual(cancelled['bookedPayable'],0)
        with self.assertRaises(ValueError):
            self.bridge.accountingCommand({
                'type':'intake.price','eventId':'later','intakeId':'intake-1','unitPrice':500})
        self.assertEqual(self.bridge.accountingRead('p-sample')['documents'],[])


if __name__=='__main__':
    unittest.main()
