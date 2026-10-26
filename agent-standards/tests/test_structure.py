"""Verify locally activated project-agent policy without dependencies."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "agent-standards"
PROFILE = tuple((POLICY / "projects").glob("*.md"))
REQUIRED = (
    "README.md",
    "core/coding-principles.md",
    "core/change-scope.md",
    "core/verification-rules.md",
)


class AgentPolicyChecks(unittest.TestCase):
    def test_shared_files_and_profile(self):
        self.assertEqual(1, len(PROFILE))
        for relative in REQUIRED:
            with self.subTest(relative=relative):
                self.assertTrue((POLICY / relative).is_file())

    def test_entry_points_active(self):
        self.assertIn("agent-standards/README.md", (ROOT / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertIn("agent-standards/README.md", (ROOT / "CLAUDE.md").read_text(encoding="utf-8"))
        rules = sorted((ROOT / ".cursor" / "rules").glob("*.mdc"))
        self.assertEqual(1, len(rules))
        self.assertIn("alwaysApply: true", rules[0].read_text(encoding="utf-8"))
        self.assertIn("agent-standards/README.md", rules[0].read_text(encoding="utf-8"))

    def test_relative_policy_links(self):
        files = [ROOT / "AGENTS.md", ROOT / "CLAUDE.md", POLICY / "README.md", *PROFILE]
        files += list((POLICY / "core").glob("*.md"))
        for path in files:
            for href in re.findall(r"\[[^]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                if href.startswith(("https://", "http://", "#", "mailto:")):
                    continue
                target = path.parent / href.split("#", 1)[0]
                with self.subTest(file=str(path.relative_to(ROOT)), link=href):
                    self.assertTrue(target.exists(), "broken link to " + href)

    def test_shared_origin_and_approval_boundary(self):
        overview = (POLICY / "README.md").read_text(encoding="utf-8")
        self.assertIn("783e9e6c07ca6f3d14d7e95ac245fc22af27d8ae", overview)
        self.assertIn("REFERENCE_ONLY", overview)
        self.assertTrue((ROOT / "PROJECT_CONTEXT.md").is_file())


if __name__ == "__main__":
    unittest.main()
