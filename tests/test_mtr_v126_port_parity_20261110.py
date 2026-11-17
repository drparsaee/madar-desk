"""Guard a narrowly scoped MTR port against the exact, local v1.0.26 Git base.

Read-only Git inspection and source parsing. Does not execute installers,
network services, user profiles, desktop GUI or accounting code.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import unittest

import native_app


ROOT = Path(__file__).resolve().parents[1]
BASE = "785a419af482f998154464a41df7770c9c9c87d4"
MTR_METHODS = {
    "tarazIntegrationStatus", "tarazIntegrationOpenLocal",
    "tarazIntegrationPrepare", "tarazIntegrationQueue",
    "tarazIntegrationHistory", "_taraz_actor_scope",
}


def committed_bytes(path: str) -> bytes:
    return subprocess.run(
        ["git", "--no-optional-locks", "show", BASE + ":" + path],
        cwd=ROOT, check=True, capture_output=True, timeout=8,
    ).stdout


def hash_bytes(value: bytes) -> str:
    # Windows checkout autocrlf expands repository LF into working CRLF.
    # Compare normalized source bytes against the committed Git blob.
    return hashlib.sha256(value.replace(b"\r\n", b"\n")).hexdigest()


def strip_bridge_mtr(source: str):
    tree = ast.parse(source)
    found = set()
    nodes = [node for node in tree.body
             if isinstance(node, ast.ClassDef) and node.name == "Bridge"]
    if len(nodes) != 1:
        raise AssertionError("Exactly one native Bridge class required")
    node = nodes[0]
    methods = []
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name in MTR_METHODS:
            found.add(item.name)
        else:
            methods.append(item)
    node.body = methods
    return ast.dump(node, include_attributes=False), found


class SourceLineageParity(unittest.TestCase):
    def test_detached_clean_base_commit_and_no_version_fabrication(self):
        head = subprocess.run(
            ["git", "--no-optional-locks", "rev-parse", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=8, check=True,
        ).stdout.strip()
        self.assertEqual(head, BASE)
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
        self.assertEqual(package["version"], "1.0.26")
        self.assertEqual(lock["version"], "1.0.26")
        self.assertEqual(lock["packages"][""]["version"], "1.0.26")
        self.assertEqual(package["scripts"]["dist:rc"], json.loads(
            committed_bytes("package.json").decode("utf-8")
        )["scripts"]["dist:rc"])
        updater = ast.parse((ROOT / "madar_update.py").read_text(encoding="utf-8"))
        versions = [node.value.value for node in updater.body
                    if isinstance(node, ast.Assign)
                    and any(isinstance(x, ast.Name) and x.id == "CURRENT_VERSION"
                            for x in node.targets)
                    and isinstance(node.value, ast.Constant)]
        self.assertEqual(versions, ["1.0.26"])

    def test_every_non_mtr_native_ast_node_still_matches_v126_exactly(self):
        before, baseline_methods = strip_bridge_mtr(
            committed_bytes("native_app.py").decode("utf-8")
        )
        after, updated_methods = strip_bridge_mtr(
            (ROOT / "native_app.py").read_text(encoding="utf-8")
        )
        self.assertEqual(before, after,
                         "Unrelated native Bridge behavior changed since the v126 base")
        self.assertEqual(baseline_methods,
                         {"tarazIntegrationStatus", "tarazIntegrationQueue"})
        self.assertEqual(updated_methods, MTR_METHODS)

    def test_p1_p2_update_and_web_sources_unchanged(self):
        keep = (
            "src/startup_update.mjs", "src/gantt_model.js",
            "src/gantt_view.jsx", "src/teamplus.jsx",
            "server/gantt_shift_guard.cjs", "server/index.cjs",
            "scripts/build_p1p2_v126_qa.py", "scripts/qa_p1p2_v126_upgrade.py",
            "lan.py",
        )
        for relative in keep:
            with self.subTest(path=relative):
                self.assertEqual(
                    hash_bytes((ROOT / relative).read_bytes()),
                    hash_bytes(committed_bytes(relative)),
                )

    def test_manual_only_bridge_and_provenance_never_claim_finance(self):
        exported = set(re.findall(r"['\"]([A-Za-z][A-Za-z0-9]*)['\"]",
                                  native_app.JS_BRIDGE))
        self.assertTrue(MTR_METHODS - {"_taraz_actor_scope"} <= exported)
        for name in MTR_METHODS:
            self.assertTrue(callable(getattr(native_app.Bridge, name, None)))
        ui = (ROOT / "src/App.jsx").read_text(encoding="utf-8")
        sender = ui[ui.index("const sendToTaraz=async(taskId,requestId=null)=>{"):]
        sender = sender[:sender.index("if(!data)return")]
        self.assertLess(sender.index("if(!tarazEnabled)"),
                        sender.index("api.tarazIntegrationPrepare(taskId)"))
        self.assertLess(sender.index("api.tarazIntegrationPrepare(taskId)"),
                        sender.index("api.tarazIntegrationQueue(taskId,null,targetId)"))
        self.assertIn("postingPerformed!==false", sender)
        self.assertIn("peerVerified:false", ui)
        self.assertIn("checkAndCacheAvailableUpdate", ui)
        self.assertIn("GanttView", ui)


if __name__ == "__main__":
    unittest.main()
