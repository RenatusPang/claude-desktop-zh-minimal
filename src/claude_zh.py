#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Minimal, fail-closed Chinese locale patch for a pinned Windows Claude Desktop build.

Never uploads data, reads API keys, changes app.asar, or edits Claude.exe.
Translation JSON files are redistributable resources from javaht (MIT); see NOTICE.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

TOOL_VERSION = "0.1.0"
SUPPORTED_PACKAGE_VERSION = "3.1623.0.0"
BUNDLE_REL = Path("ion-dist/assets/v1/shared-52-DYU8GgYU.js")
EXPECTED_ORIGINAL_SHA256 = "87400e6f593dff3c6aef0177b575da988212210f9ba4eea4652e87e5a55cb8d6"
WHITELIST = b'var jv=["en-US","de-DE","fr-FR","ko-KR","ja-JP","es-419","es-ES","it-IT","hi-IN","pt-BR","id-ID"]'
ZH_WHITELIST = b'var jv=["en-US","de-DE","fr-FR","ko-KR","ja-JP","es-419","es-ES","it-IT","hi-IN","pt-BR","id-ID","zh-CN"]'
LOCALE_PATTERN = re.compile(r'("locale"\s*:\s*")([^"\\]*)(")')
LANG_REL = (
    "ion-dist/i18n/zh-CN.json",
    "ion-dist/i18n/statsig/zh-CN.json",
    "zh-CN.json",
    "ion-dist/i18n/dynamic/zh-CN.json",
)
CONFIG_REL = (
    Path("AppData/Roaming/Claude/config.json"),
    Path("AppData/Roaming/Claude-3p/config.json"),
    Path("AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Roaming/Claude/config.json"),
    Path("AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Roaming/Claude-3p/config.json"),
)


class PatchError(Exception):
    """An expected, safe-to-report failure."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def patch_whitelist(original: bytes, *, check_hash: bool = True) -> bytes:
    if check_hash and sha256(original) != EXPECTED_ORIGINAL_SHA256:
        raise PatchError("Unknown JS build/hash. No modification made.")
    if original.count(WHITELIST) != 1:
        raise PatchError("Whitelist anchor not found exactly once.")
    if original.count(ZH_WHITELIST):
        raise PatchError("Bundle already patched; refusing to patch again.")
    return original.replace(WHITELIST, ZH_WHITELIST, 1)


def merge_catalog(english: dict, chinese: dict) -> tuple[dict, int]:
    if not isinstance(english, dict) or not isinstance(chinese, dict):
        raise PatchError("Catalog must contain JSON objects.")
    merged = english.copy()
    count = 0
    for key, value in chinese.items():
        if key in merged and isinstance(value, str):
            merged[key] = value
            count += 1
    return merged, count


def locale_value(raw: str) -> tuple[bool, str | None]:
    doc = json.loads(raw.lstrip("\ufeff"))
    if not isinstance(doc, dict):
        raise PatchError("Claude config must be a JSON object.")
    return "locale" in doc, doc.get("locale")


def set_locale(raw: str, locale: str) -> tuple[str, bool, str | None]:
    existed, original = locale_value(raw)
    if existed:
        matches = list(LOCALE_PATTERN.finditer(raw))
        if len(matches) != 1 or not isinstance(original, str):
            raise PatchError("Unsupported locale field in config.")
        updated = LOCALE_PATTERN.sub(lambda m: m.group(1) + locale + m.group(3), raw)
    else:
        opening = re.search(r"\{", raw)
        if not opening:
            raise PatchError("Invalid Claude config JSON.")
        tail = raw[opening.end():]
        add_comma = bool(tail.strip() and not tail.lstrip().startswith("}"))
        insert = '"locale":"' + locale + '"' + ("," if add_comma else "")
        updated = raw[:opening.end()] + insert + raw[opening.end():]
    json.loads(updated.lstrip("\ufeff"))
    return updated, existed, original


def restore_locale(raw: str, had_locale: bool, old_locale: str | None) -> tuple[str, bool]:
    exists, current = locale_value(raw)
    if not exists or current != "zh-CN":
        return raw, False  # Preserve deliberate user changes.
    if had_locale:
        return set_locale(raw, old_locale or "en-US")[0], True
    # An absent locale is inserted at the beginning of the object during install.
    updated, count = re.subn(r'(^\ufeff?\s*\{\s*)"locale"\s*:\s*"zh-CN"\s*,?', r'\1', raw, count=1)
    if count != 1:
        raise PatchError("Cannot safely remove newly inserted locale.")
    json.loads(updated.lstrip("\ufeff"))
    return updated, True


def as_json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def safe_write(path: Path, contents: bytes) -> None:
    """Write in place for MSIX paths: do not replace or alter ACLs/signatures."""
    with path.open("wb") as f:
        f.write(contents)
        f.flush()
        os.fsync(f.fileno())


def save_state(path: Path, state: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8"))
    os.replace(tmp, path)


def package_info() -> tuple[str, Path]:
    if os.name != "nt":
        raise PatchError("Windows only.")
    cmd = ('[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); '
           'Get-AppxPackage -Name Claude | Where-Object { $_.Name -eq "Claude" } '
           '| Select-Object Name,Version,InstallLocation | ConvertTo-Json -Compress')
    proc = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd],
                          capture_output=True, check=False)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise PatchError("Claude MSIX package not found; Windows Store version only.")
    info = json.loads(proc.stdout.decode("utf-8-sig", errors="replace"))
    if isinstance(info, list):
        if len(info) != 1:
            raise PatchError("Multiple Claude MSIX packages found.")
        info = info[0]
    if not isinstance(info, dict):
        raise PatchError("Invalid Claude package metadata.")
    version = str(info["Version"])
    install_root = Path(str(info["InstallLocation"]))
    if version != SUPPORTED_PACKAGE_VERSION:
        raise PatchError(f"Unsupported package version {version}; supported: {SUPPORTED_PACKAGE_VERSION}.")
    if not (install_root / "app" / "resources").is_dir():
        raise PatchError("Unsupported Claude package layout.")
    return version, install_root


def app_is_running(install_root: Path) -> bool:
    script = ('$r=$env:CLAUDE_ZH_APP_ROOT;'
              '$items=@(Get-CimInstance Win32_Process -ErrorAction Stop | '
              'Where-Object { $_.Name -ieq "claude.exe" -and $_.ExecutablePath -and '
              '$_.ExecutablePath.StartsWith($r,[StringComparison]::OrdinalIgnoreCase) }); '
              'Write-Output $items.Count')
    env = dict(os.environ)
    env["CLAUDE_ZH_APP_ROOT"] = str(install_root / "app")
    proc = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                          env=env, capture_output=True, check=False)
    if proc.returncode != 0:
        raise PatchError("Could not reliably detect Claude processes.")
    try:
        return int(proc.stdout.strip()) > 0
    except ValueError as err:
        raise PatchError("Unclear Claude process state.") from err


def paths() -> tuple[Path, Path, Path, list[Path]]:
    _, install_root = package_info()
    resource_root = install_root / "app" / "resources"
    bundle = resource_root / BUNDLE_REL
    backup_base = Path(os.environ["LOCALAPPDATA"]) / "ClaudeZhMinimal"
    home = Path(os.environ["USERPROFILE"])
    configs = [home / suffix for suffix in CONFIG_REL]
    return resource_root, bundle, backup_base, configs


def is_admin() -> bool:
    return os.name == "nt" and bool(ctypes.windll.shell32.IsUserAnAdmin())


def request_elevation(action: str) -> None:
    params = f'"{Path(__file__).resolve()}" {action}'
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
    if result <= 32:
        raise PatchError(f"Windows UAC elevation failed (code={result}).")
    print("已启动管理员权限窗口。请查看该窗口的执行结果。")


def plan_install(root: Path, bundle: Path, configs: list[Path]) -> dict:
    """Read everything and validate before the first write."""
    if not bundle.is_file():
        raise PatchError(f"Missing expected bundle: {bundle.name}")
    original = bundle.read_bytes()
    updated = patch_whitelist(original)
    frontend = root / "ion-dist" / "i18n"
    translations = Path(__file__).resolve().parent.parent / "translations"
    with (frontend / "en-US.json").open(encoding="utf-8-sig") as f:
        english = json.load(f)
    with (translations / "frontend-zh-CN.json").open(encoding="utf-8-sig") as f:
        chinese = json.load(f)
    merged, translated_count = merge_catalog(english, chinese)
    if translated_count < 20000:
        raise PatchError(f"Translation pack seems incomplete: {translated_count} translated keys.")
    generated = {
        "ion-dist/i18n/zh-CN.json": as_json_bytes(merged),
        "ion-dist/i18n/statsig/zh-CN.json": (translations / "statsig-zh-CN.json").read_bytes(),
        "zh-CN.json": (translations / "desktop-zh-CN.json").read_bytes(),
    }
    dynamic_english = frontend / "dynamic" / "en-US.json"
    if dynamic_english.exists():
        generated["ion-dist/i18n/dynamic/zh-CN.json"] = dynamic_english.read_bytes()
    for name, payload in generated.items():
        if (root / name).exists():
            raise PatchError(f"Chinese resource already exists: {name}. Restore other patches first.")
        json.loads(payload.decode("utf-8-sig"))
    config_plans = []
    for file in configs:
        if file.exists():
            raw = file.read_text(encoding="utf-8-sig")
            updated_locale, existed, prior = set_locale(raw, "zh-CN")
            config_plans.append({
                "path": str(file), "had_locale": existed, "old_locale": prior,
                "original_sha256": sha256(file.read_bytes()),
                "updated_content": updated_locale,
            })
    return {
        "original": original, "patched": updated, "generated": generated,
        "translated": translated_count, "config_plans": config_plans,
    }


def inspect() -> None:
    root, bundle, base, configs = paths()
    raw = bundle.read_bytes()
    state_file = base / "manifest.json"
    state = json.loads(state_file.read_text(encoding="utf-8-sig")) if state_file.exists() else None
    kind = "original" if sha256(raw) == EXPECTED_ORIGINAL_SHA256 else "modified / unknown"
    if state and state.get("patched_sha256") == sha256(raw):
        kind = "installed minimal patch"
    print(f"Claude version: {SUPPORTED_PACKAGE_VERSION}")
    print(f"Bundle: {kind}")
    print(f"Stored backup: {'yes' if state_file.exists() else 'no'}")
    for file in configs:
        if file.exists():
            exists, value = locale_value(file.read_text(encoding="utf-8-sig"))
            print(f"Locale in {file.parent.name}: {value if exists else '(default)'}")
    if kind == "original":
        try:
            plan = plan_install(root, bundle, configs)
            print(f"Compatible: yes; translated keys: {plan['translated']}")
        except PatchError as err:
            print(f"Compatible: no; reason: {err}")


def install() -> None:
    root, bundle, base, configs = paths()
    state_file = base / "manifest.json"
    if state_file.exists():
        raise PatchError("Installation state exists; use status/uninstall, not reinstall.")
    plan = plan_install(root, bundle, configs)
    if app_is_running(root.parent.parent):
        raise PatchError("Claude is running. Exit desktop app and tray icon before installation.")
    base.mkdir(parents=True, exist_ok=True)
    backup_dir = base / ("backup-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    backup_dir.mkdir(exist_ok=False)
    saved_bundle = backup_dir / "original-bundle.js"
    saved_bundle.write_bytes(plan["original"])
    if sha256(saved_bundle.read_bytes()) != EXPECTED_ORIGINAL_SHA256:
        raise PatchError("Backup integrity check failed.")
    state = {
        "tool": "claude-desktop-zh-minimal",
        "format": 1,
        "package_version": SUPPORTED_PACKAGE_VERSION,
        "resource_root": str(root),
        "bundle_path": str(bundle),
        "original_sha256": sha256(plan["original"]),
        "patched_sha256": sha256(plan["patched"]),
        "bundle_backup": str(saved_bundle),
        "resources": {name: sha256(data) for name, data in plan["generated"].items()},
        "configs": [
            {k: v for k, v in row.items() if k != "updated_content"}
            for row in plan["config_plans"]
        ],
        "status": "prepared",
    }
    save_state(state_file, state)
    try:
        safe_write(bundle, plan["patched"])
        for name, payload in plan["generated"].items():
            location = root / name
            location.parent.mkdir(parents=True, exist_ok=True)
            with location.open("xb") as f:
                f.write(payload)
        for row in plan["config_plans"]:
            # Refuse to overwrite a config that changed between preflight and writing.
            cfg = Path(row["path"])
            if sha256(cfg.read_bytes()) != row["original_sha256"]:
                raise PatchError(f"Config changed while installing: {cfg}")
            safe_write(cfg, row["updated_content"].encode("utf-8"))
        if sha256_file(bundle) != state["patched_sha256"]:
            raise PatchError("Patched bundle verification failed.")
        for name, checksum in state["resources"].items():
            if sha256_file(root / name) != checksum:
                raise PatchError(f"Translated resource verification failed: {name}")
        state["status"] = "installed"
        save_state(state_file, state)
        print(f"安装成功：仅修改 1 个 JS 文件，添加 {len(plan['generated'])} 个语言文件。")
        print(f"已翻译 {plan['translated']} 个词条；未翻译的词条使用本机英文兜底。")
        print("没有修改 Claude.exe / app.asar，不会提取、记录或上传 API 密钥；只在本机读取配置文件以修改语言设置。")
        print("备份位置：", backup_dir)
        print("请从 Windows 开始菜单启动 Claude 测试中文界面。")
    except Exception:
        print("安装中断，尝试安全恢复本次已写入的文件。", file=sys.stderr)
        try:
            _uninstall_core(root, bundle, base, state, interrupted=True)
        except Exception as rollback_error:
            print(f"自动恢复未完成：{rollback_error}", file=sys.stderr)
            print(f"保留现场和备份：{base}", file=sys.stderr)
        raise


def _uninstall_core(root: Path, bundle: Path, base: Path, state: dict, *,
                    interrupted: bool = False) -> None:
    if state.get("resource_root") != str(root) or state.get("package_version") != SUPPORTED_PACKAGE_VERSION:
        raise PatchError("Claude was moved or updated; do not restore stale backup.")
    backup = Path(state["bundle_backup"])
    if not backup.is_file() or sha256_file(backup) != EXPECTED_ORIGINAL_SHA256:
        raise PatchError("Original JS backup missing or invalid.")
    bundle_hash = sha256_file(bundle)
    allowed = {state["original_sha256"], state["patched_sha256"]}
    if bundle_hash not in allowed:
        raise PatchError("JS changed since installation; rollback blocked.")
    # Check ALL files before deleting any, to avoid half-uninstalls on modified resources.
    for name, expected in state["resources"].items():
        target = root / name
        if target.exists() and sha256_file(target) != expected:
            raise PatchError(f"Translated resource changed: {name}; refusing deletion.")
    if bundle_hash != state["original_sha256"]:
        safe_write(bundle, backup.read_bytes())
    for name in state["resources"]:
        target = root / name
        if target.exists():
            target.unlink()
    for row in state["configs"]:
        cfg = Path(row["path"])
        if not cfg.exists():
            continue
        raw = cfg.read_text(encoding="utf-8-sig")
        updated, changed = restore_locale(raw, row["had_locale"], row["old_locale"])
        if changed:
            safe_write(cfg, updated.encode("utf-8"))
    if sha256_file(bundle) != state["original_sha256"]:
        raise PatchError("Restored JS hash mismatch.")
    manifest = base / "manifest.json"
    if manifest.exists():
        manifest.unlink()
    print("卸载成功：原始 JS 已恢复，新增中文资源已清理。")
    print("个人配置保留；仅在当前 locale 仍为 zh-CN 时恢复旧语言。")
    print("备份文件保留在：", backup.parent)


def uninstall() -> None:
    root, bundle, base, _ = paths()
    manifest = base / "manifest.json"
    if not manifest.exists():
        raise PatchError("No install manifest. Nothing to uninstall with this tool.")
    state = json.loads(manifest.read_text(encoding="utf-8-sig"))
    if app_is_running(root.parent.parent):
        raise PatchError("Claude is running. Exit desktop app before uninstalling.")
    _uninstall_core(root, bundle, base, state)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Claude Desktop third-party API zh-CN minimal patch")
    parser.add_argument("action", choices=("status", "install", "uninstall"))
    args = parser.parse_args(argv)
    try:
        if args.action in ("install", "uninstall") and not is_admin():
            request_elevation(args.action)
            return 0
        if args.action == "status":
            inspect()
        elif args.action == "install":
            install()
        else:
            uninstall()
        return 0
    except (PatchError, OSError, ValueError, json.JSONDecodeError) as err:
        print(f"[失败/安全停止] {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
