import copy
import unittest

from finance_visibility import redact_card, preserve_editor_finance


def original():
    return {"id":"t1","projectId":"p","title":"Task","cost":983,
            "costEnabled":True,"costCategory":"secret","costDate":"2026-10-11","saleUnitPrice":987_654,
            "checklist":[{"id":"i1","text":"a","done":False,"cost":55,
                          "costCategory":"private","costDate":"2026-10-11"},
                         {"id":"i2","text":"b","done":False,"cost":0}],
            "checklists":[{"id":"g","name":"Group","items":[{"id":"x","text":"x","done":False,"cost":60}]}]}


class FinanceVisibility(unittest.TestCase):
    def test_redact_does_not_mutate_authoritative(self):
        source=original()
        masked=redact_card(source)
        self.assertEqual(masked["cost"],0)
        self.assertEqual(masked["saleUnitPrice"],0)
        self.assertEqual(masked["costEnabled"],None)
        self.assertEqual(masked["checklist"][0]["cost"],0)
        self.assertEqual(masked["checklists"][0]["items"][0]["cost"],0)
        self.assertEqual(source["cost"],983)

    def test_editor_changes_nonfinancial_title_but_keeps_money_unchanged(self):
        source=original()
        incoming=redact_card(source)
        incoming["title"]="Revised"
        incoming["checklist"][0]["done"]=True
        preserve_editor_finance([source],[incoming])
        self.assertEqual(incoming["title"],"Revised")
        self.assertEqual(incoming["checklist"][0]["cost"],55)
        self.assertEqual(incoming["checklists"][0]["items"][0]["cost"],60)
        self.assertEqual(incoming["cost"],983)
        self.assertEqual(incoming["saleUnitPrice"],987_654)
        self.assertEqual(source["title"],"Task")

    def test_editor_attempt_to_edit_money_denied(self):
        source=original()
        incoming=redact_card(source)
        incoming["cost"]=999
        with self.assertRaises(PermissionError):
            preserve_editor_finance([source],[incoming])

    def test_sale_quantity_is_not_disclosed_or_editor_mutable(self):
        source=original()
        source["saleQuantity"]=250
        source["saleCurrency"]="TOMAN"
        source["salePartyId"]="customer-1"
        incoming=redact_card(source)
        self.assertEqual(incoming["saleQuantity"], 1)
        self.assertEqual(incoming["salePartyId"], "")
        incoming["saleQuantity"]=999
        with self.assertRaises(PermissionError):
            preserve_editor_finance([source],[incoming])
        incoming=redact_card(source)
        incoming["title"]="Change allowed"
        preserve_editor_finance([source],[incoming])
        self.assertEqual(incoming["saleQuantity"], 250)

    def test_editor_can_remove_unpaid_empty_expense_items(self):
        source=original()
        source["checklist"].append({"id":"zero", "text":"zero", "done":False,
                                    "cost":0, "expenseItems":[]})
        incoming=redact_card(source)
        incoming["checklist"]=[x for x in incoming["checklist"] if x["id"]!="zero"]
        preserve_editor_finance([source],[incoming])
        self.assertNotIn("zero", [x["id"] for x in incoming["checklist"]])
        incoming=redact_card(source)
        incoming["saleUnitPrice"]=50000
        with self.assertRaises(PermissionError):
            preserve_editor_finance([source],[incoming])

    def test_editor_cannot_delete_paid_legacy_line(self):
        source=original()
        incoming=redact_card(source)
        incoming["checklist"]=incoming["checklist"][1:]
        with self.assertRaises(PermissionError):
            preserve_editor_finance([source],[incoming])

    def test_editor_cannot_delete_paid_named_group(self):
        source=original()
        incoming=redact_card(source)
        incoming["checklists"]=[]
        with self.assertRaises(PermissionError):
            preserve_editor_finance([source],[incoming])

    def test_editor_can_append_unpaid_line(self):
        source=original()
        incoming=redact_card(source)
        incoming["checklist"].append({"id":"i3","done":False,"text":"new","cost":0})
        preserve_editor_finance([source],[incoming])
        self.assertEqual(incoming["checklist"][-1]["cost"],0)

    def test_editor_cannot_create_money_for_new_card(self):
        incoming=[{"id":"t2","projectId":"p","title":"new","cost":1,"checklist":[]}]
        with self.assertRaises(PermissionError):
            preserve_editor_finance([],incoming)

    def test_editor_can_create_zero_cost_new_card(self):
        incoming=[{"id":"t2","projectId":"p","title":"new","cost":0,"costEnabled":None,"checklist":[]}]
        preserve_editor_finance([],incoming)
        self.assertEqual(incoming[0]["cost"],0)

    def test_editor_cannot_physically_delete_paid_card(self):
        with self.assertRaises(PermissionError):
            preserve_editor_finance([original()], [])

    def test_editor_cannot_physically_drop_even_unpaid_card(self):
        source=original()
        source["cost"]=0
        source["costEnabled"]=None
        source["costCategory"]=source["costDate"]=""
        for item in source["checklist"]:
            item["cost"]=0
            item["costCategory"]=item["costDate"]=""
        source["checklists"][0]["items"][0]["cost"]=0
        with self.assertRaises(PermissionError):
            preserve_editor_finance([source], [])

    def test_legacy_missing_id_paid_item_done_change_safe(self):
        source=original()
        del source["checklist"][0]["id"]
        incoming=redact_card(source)
        incoming["checklist"][0]["done"]=True
        preserve_editor_finance([source],[incoming])
        self.assertTrue(incoming["checklist"][0]["done"])
        self.assertEqual(incoming["checklist"][0]["cost"],55)

    def test_legacy_missing_id_paid_item_cannot_move_or_replace(self):
        source=original()
        del source["checklist"][0]["id"]
        incoming=redact_card(source)
        incoming["checklist"].reverse()
        with self.assertRaises(PermissionError):
            preserve_editor_finance([source],[incoming])
        incoming=redact_card(source)
        incoming["checklist"][0]["text"]="other"
        with self.assertRaises(PermissionError):
            preserve_editor_finance([source],[incoming])


if __name__ == "__main__":
    unittest.main()
