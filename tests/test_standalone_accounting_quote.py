"""Exact synthetic sale quotes; no database/network or customer records."""
import unittest

from accounting_core import MAX_TOMAN
from standalone_accounting_quote import quote_standalone_sale


class StandaloneQuote(unittest.TestCase):
    def test_rial_native_quote_keeps_single_rial(self):
        result = quote_standalone_sale(
            {"quantity": 3, "unitPrice": 1, "currency": "RIAL"},
            ledger_currency="RIAL")
        self.assertEqual(result["amount"], "3")
        self.assertEqual(result["amountRial"], "3")
        toman = quote_standalone_sale(
            {"quantity": 2, "unitPrice": 125, "currency": "TOMAN"},
            ledger_currency="RIAL")
        self.assertEqual(toman["amountRial"], "2500")
    def test_book_100_quantity_unit_toman(self):
        quote = quote_standalone_sale({"quantity": 100, "unitPrice": 20000,
                                       "currency": "TOMAN"})
        self.assertEqual(quote, {"quantity": 100, "currency": "TOMAN",
                                 "amount": "2000000", "amountToman": 2000000,
                                 "status": "quote-only"})

    def test_exact_rial_conversion_and_no_loss(self):
        rial = quote_standalone_sale({"quantity": 100, "unitPrice": 200000,
                                      "currency": "RIAL"})
        self.assertEqual(rial["amount"], "20000000")
        self.assertEqual(rial["amountToman"], 2000000)
        with self.assertRaisesRegex(ValueError, "exact TOMAN"):
            quote_standalone_sale({"quantity": 1, "unitPrice": 125,
                                   "currency": "RIAL"})

    def test_rejects_bool_floats_extra_fields_and_overflows(self):
        allowed = {"quantity": 1, "unitPrice": 100, "currency": "TOMAN"}
        for changes in ({"quantity": True}, {"quantity": 1.5},
                        {"unitPrice": "100"}, {"unitPrice": 0},
                        {"unitPrice": -1}, {"currency": "USD"},
                        {"quantity": 1000001}, {"actor": "admin"},
                        {"unitPrice": MAX_TOMAN + 1},
                        {"quantity": 2, "unitPrice": MAX_TOMAN}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                quote_standalone_sale({**allowed, **changes})

    def test_big_rial_total_exposed_as_exact_decimal_string(self):
        quote = quote_standalone_sale({"quantity": 1,
                                       "unitPrice": 10 * MAX_TOMAN,
                                       "currency": "RIAL"})
        self.assertEqual(quote["amount"], str(10 * MAX_TOMAN))


if __name__ == "__main__":
    unittest.main()
