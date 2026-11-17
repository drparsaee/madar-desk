"""Host-private account lineage contracts; no real accounts, I/O or network."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mtr_account_lineage import (
    AccountLineageError, new_account_lineage, principal_actor_id,
)


class AccountLineageTests(unittest.TestCase):
    def setUp(self):
        # The module is pure. Even test-side temp/profiles are disposable.
        root = tempfile.TemporaryDirectory(prefix="mtr-account-lineage-")
        self.addCleanup(root.cleanup)
        self.root = Path(root.name)
        vars = ("APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "HOME",
                "USERPROFILE")
        patcher = patch.dict(os.environ, {key: str(self.root) for key in vars})
        patcher.start()
        self.addCleanup(patcher.stop)

    def account(self, lineage=None, *, username="same-username"):
        return {
            "username": username, "role": "editor", "passwordHash": "private-hash",
            "projects": ["project-a"], "accountLineage": (
                new_account_lineage() if lineage is None else lineage
            ),
        }

    def test_new_lineage_is_canonical_128_random_bits(self):
        issued = [new_account_lineage() for _ in range(64)]
        self.assertEqual(len(set(issued)), 64)
        for value in issued:
            self.assertRegex(value, r"\A[0-9a-f]{32}\Z")
            self.assertNotEqual(value, "0" * 32)

    def test_new_lineage_uses_os_csprng_exactly_16_bytes(self):
        with patch("mtr_account_lineage.secrets.token_bytes",
                   return_value=bytes(range(16))) as generator:
            created = new_account_lineage()
        generator.assert_called_once_with(16)
        self.assertEqual(created, bytes(range(16)).hex())

    def test_secure_rng_malformed_output_fails_closed(self):
        for fake in (b"", b"1" * 15, b"2" * 17,
                     b"\x00" * 16, "a" * 16, bytearray(16), False):
            with self.subTest(fake=type(fake).__name__ + ":" + str(len(fake))
                              if hasattr(fake, "__len__") else type(fake).__name__):
                with patch("mtr_account_lineage.secrets.token_bytes",
                           return_value=fake):
                    with self.assertRaises(AccountLineageError):
                        new_account_lineage()

    def test_same_username_different_lineage_is_different_actor(self):
        first = self.account("0123456789abcdef0123456789abcdef")
        second = self.account("fedcba9876543210fedcba9876543210")
        self.assertEqual(first["username"], second["username"])
        self.assertNotEqual(principal_actor_id(first), principal_actor_id(second))

    def test_password_reset_preserves_actor_when_host_keeps_lineage(self):
        old = self.account()
        updated = {**old, "passwordHash": "new-password-salt-and-hash"}
        self.assertEqual(principal_actor_id(old), principal_actor_id(updated))

    def test_role_grants_and_session_changes_do_not_change_actor(self):
        original = self.account()
        modified = {
            **original, "role": "admin", "projects": None,
            "session": "another-session",
            "financeEdit": False,
        }
        self.assertEqual(principal_actor_id(original), principal_actor_id(modified))

    def test_username_rename_cannot_rekey_lineage_actor(self):
        before = self.account()
        after = {**before, "username": "renamed-user"}
        self.assertEqual(principal_actor_id(before), principal_actor_id(after))

    def test_legacy_missing_lineage_rejected_not_username_fallback(self):
        for case in (
            {}, {"username": "known"},
            {"username": "known", "actorId": "known"},
            {"username": "known", "lineageId": "a" * 32},
            {"username": "known", "accountLineage": None},
        ):
            with self.subTest(keys=tuple(case)):
                with self.assertRaises(AccountLineageError):
                    principal_actor_id(case)

    def test_missing_legacy_lineage_never_auto_mints_on_recovery(self):
        with patch("mtr_account_lineage.secrets.token_bytes",
                   side_effect=AssertionError("unexpected lineage regeneration")) as rng:
            with self.assertRaises(AccountLineageError):
                principal_actor_id({"username": "legacy-account"})
        rng.assert_not_called()

    def test_malformed_and_noncanonical_lineage_rejected(self):
        cases = (
            "", "0" * 32, "a" * 31, "a" * 33,
            "A" * 32, "g" * 32, "f" * 16 + "-" + "f" * 16,
            " " + "a" * 32, "a" * 32 + "\n", "a" * 32 + "\x00",
            123, True, False, b"a" * 32, ["a" * 32],
        )
        for value in cases:
            with self.subTest(value=repr(value)[:60]):
                with self.assertRaises(AccountLineageError):
                    principal_actor_id(self.account(value))

    def test_forged_actor_claims_are_not_accepted_as_overrides(self):
        valid = self.account("a" * 32)
        for claim in ("actorId", "actor_id", "principalActorId",
                      "principal_actor_id"):
            with self.subTest(claim=claim):
                with self.assertRaises(AccountLineageError):
                    principal_actor_id({**valid, claim: "old-user-identity"})

    def test_only_plain_host_record_dict_accepted(self):
        valid = self.account()

        class UntrustedDict(dict):
            pass

        for value in (None, "name", [], (valid,), UntrustedDict(valid)):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(AccountLineageError):
                    principal_actor_id(value)

    def test_opaque_output_format_is_bounded_and_not_raw_lineage(self):
        account = self.account("0123456789abcdef0123456789abcdef")
        actor = principal_actor_id(account)
        self.assertRegex(actor, r"\Amtr-actor-v1-[0-9a-f]{64}\Z")
        self.assertLessEqual(len(actor), 180)
        self.assertNotIn(account["accountLineage"], actor)
        self.assertNotIn(account["username"], actor)
        self.assertNotIn(account["passwordHash"], actor)
        self.assertNotEqual(actor, account["accountLineage"])

    def test_output_is_stable_domain_separated_digest(self):
        lineage = "0123456789abcdef0123456789abcdef"
        account = self.account(lineage)
        expected_digest = hashlib.sha256(
            b"madar.mtr.account-lineage.actor.v1\x00"
            + bytes.fromhex(lineage)
        ).hexdigest()
        self.assertEqual(principal_actor_id(account),
                         "mtr-actor-v1-" + expected_digest)
        self.assertNotEqual(expected_digest,
                            hashlib.sha256(bytes.fromhex(lineage)).hexdigest())

    def test_errors_do_not_echo_private_fields(self):
        sensitive_username = "confidential-username"
        sensitive_password = "secret-password-hash"
        account = {
            "username": sensitive_username,
            "passwordHash": sensitive_password,
            "accountLineage": "BAD-PRIVATE-LINEAGE",
        }
        with self.assertRaises(AccountLineageError) as captured:
            principal_actor_id(account)
        description = str(captured.exception)
        for value in (sensitive_username, sensitive_password, "BAD-PRIVATE-LINEAGE"):
            self.assertNotIn(value, description)


if __name__ == "__main__":
    unittest.main()
