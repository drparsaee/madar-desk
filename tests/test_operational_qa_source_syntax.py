"""Keep archived operational QA scripts parseable without escape warnings.

This is a source-level regression gate only. It does not run a browser, touch
customer profiles, or claim that the historical QA scenarios still pass.
"""

from pathlib import Path
import unittest
import warnings


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class OperationalQASyntaxTests(unittest.TestCase):
    def test_operational_qa_sources_compile_without_syntax_warnings(self):
        scripts = sorted(SCRIPTS.glob("operational_*_qa.py"))
        self.assertTrue(scripts, "No operational QA script was found")
        for source in scripts:
            with self.subTest(filename=source.name):
                with warnings.catch_warnings():
                    warnings.simplefilter("error", SyntaxWarning)
                    compile(source.read_text(encoding="utf-8-sig"),
                            str(source), "exec")


if __name__ == "__main__":
    unittest.main()
