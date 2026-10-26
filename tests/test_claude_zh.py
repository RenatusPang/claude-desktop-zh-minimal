# SPDX-License-Identifier: MIT
"""Tests use synthetic app bundles and temporary directories only."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import claude_zh as patcher


class UnitTests(unittest.TestCase):
    def test_whitelist_exact(self):
        original = b"prefix" + patcher.WHITELIST + b"suffix"
        changed = patcher.patch_whitelist(original, check_hash=False)
        self.assertEqual(changed.count(patcher.ZH_WHITELIST), 1)
        self.assertTrue(changed.startswith(b"prefix"))
        with self.assertRaises(patcher.PatchError):
            patcher.patch_whitelist(changed, check_hash=False)

    def test_refuse_unknown_or_ambiguous_bundle(self):
        with self.assertRaises(patcher.PatchError):
            patcher.patch_whitelist(b"some future build")
        with self.assertRaises(patcher.PatchError):
            patcher.patch_whitelist(patcher.WHITELIST * 2, check_hash=False)

    def test_merge_english_fallback(self):
        result, total = patcher.merge_catalog(
            {"A": "English", "B": "Fallback"},
            {"A": "中文", "C": "Old unused entry"})
        self.assertEqual(result, {"A": "中文", "B": "Fallback"})
        self.assertEqual(total, 1)

    def test_locale_preserves_other_keys(self):
        raw = '{"locale": "en-US", "gateway": {"model": "deepseek-chat"}}'
        modified, had, old = patcher.set_locale(raw, "zh-CN")
        self.assertIn("deepseek-chat", modified)
        self.assertEqual((had, old), (True, "en-US"))
        restored, changed = patcher.restore_locale(modified, had, old)
        self.assertTrue(changed)
        self.assertEqual(json.loads(restored), json.loads(raw))

    def test_locale_new_key_round_trip(self):
        raw = '{"gateway": {"safe": true}}'
        changed, had, old = patcher.set_locale(raw, "zh-CN")
        self.assertFalse(had)
        restored, done = patcher.restore_locale(changed, had, old)
        self.assertTrue(done)
        self.assertEqual(json.loads(restored), json.loads(raw))

    def test_locale_does_not_override_user_change(self):
        new_value, changed = patcher.restore_locale(
            '{"locale":"fr-FR","gateway":"keep"}', True, "en-US")
        self.assertFalse(changed)
        self.assertIn("fr-FR", new_value)


class IntegrationTests(unittest.TestCase):
    def test_mock_install_and_rollback_no_secrets_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            top = Path(tmp)
            root = top / "fake_app" / "app" / "resources"
            bundle = root / patcher.BUNDLE_REL
            bundle.parent.mkdir(parents=True)
            original = b"synthetic-code;" + patcher.WHITELIST + b";end;"
            bundle.write_bytes(original)

            english = root / "ion-dist/i18n/en-US.json"
            english.parent.mkdir(parents=True)
            # The source translation is public MIT-licensed data.
            translation_path = (Path(__file__).resolve().parent.parent
                                / "translations/frontend-zh-CN.json")
            translations = json.loads(translation_path.read_text(encoding="utf-8"))
            english.write_text(
                json.dumps({key: "English" for key in translations}),
                encoding="utf-8")
            dynamic = root / "ion-dist/i18n/dynamic/en-US.json"
            dynamic.parent.mkdir(parents=True)
            dynamic.write_text('{"dynamic":"English"}', encoding="utf-8")

            configs = [top / "Claude/config.json", top / "Claude-3p/config.json"]
            for c in configs:
                c.parent.mkdir(parents=True)
                c.write_text('{"locale":"en-US","gateway":"DUMMY_SECRET_SENTINEL"}',
                             encoding="utf-8")
            base = top / "user_local_data"
            location = (root, bundle, base, configs)
            with (patch.object(patcher, "paths", return_value=location),
                  patch.object(patcher, "app_is_running", return_value=False),
                  patch.object(patcher, "EXPECTED_ORIGINAL_SHA256",
                               patcher.sha256(original))):
                patcher.install()
                self.assertTrue((base / "manifest.json").exists())
                self.assertIn(patcher.ZH_WHITELIST, bundle.read_bytes())
                self.assertTrue((root / "ion-dist/i18n/zh-CN.json").exists())
                self.assertEqual(json.loads(configs[0].read_text())["locale"], "zh-CN")
                self.assertNotIn("DUMMY_SECRET_SENTINEL",
                                 (base / "manifest.json").read_text(encoding="utf-8"))
                # A later setting change must survive rollback.
                configs[1].write_text(
                    '{"locale":"fr-FR","gateway":"DUMMY_SECRET_SENTINEL"}',
                    encoding="utf-8")
                patcher.uninstall()
                self.assertEqual(bundle.read_bytes(), original)
                self.assertFalse((root / "ion-dist/i18n/zh-CN.json").exists())
                self.assertFalse((base / "manifest.json").exists())
                self.assertEqual(json.loads(configs[0].read_text())["locale"], "en-US")
                self.assertEqual(json.loads(configs[1].read_text())["locale"], "fr-FR")
                self.assertIn("DUMMY_SECRET_SENTINEL", configs[0].read_text())


if __name__ == "__main__":
    unittest.main()
