"""Tests that need no network and never touch the real Herdr home."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import capture  # noqa: E402
import herdrcfg as cfg  # noqa: E402
import install  # noqa: E402


class Merges(unittest.TestCase):
    def test_merge_json_patch_wins_and_keeps_the_rest(self):
        merged = cfg.merge_json({"a": 1, "sounds": {"enabled": False, "volume": 3}}, {"a": 2, "sounds": {"enabled": True}})
        self.assertEqual(merged, {"a": 2, "sounds": {"enabled": True, "volume": 3}})

    def test_merge_keys_adds_but_never_replaces_a_key_in_use(self):
        existing = {"global": {"cmd-t": "tab.new", "ctrl-shift-m": "something.else"}, "terminal": {}}
        merged, conflicts = cfg.merge_keys(existing, {"global": {"ctrl-shift-m": "mod.open:herdr-kanban", "ctrl-shift-j": "x"}})
        self.assertEqual(conflicts, ["global/ctrl-shift-m"])
        self.assertEqual(merged["global"]["ctrl-shift-m"], "something.else")
        self.assertEqual(merged["global"]["ctrl-shift-j"], "x")
        self.assertEqual(existing["global"].get("ctrl-shift-j"), None, "the input is not mutated")

    def test_add_seen_is_idempotent_and_sorted(self):
        once = cfg.add_seen(["tabs"], ["Git", "usage", "tabs"])
        self.assertEqual(once, ["Git", "tabs", "usage"])
        self.assertEqual(cfg.add_seen(once, ["Git"]), once)


class Patches(unittest.TestCase):
    def test_patch_has_only_added_lines_and_reproduces_the_modified_file(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "orig.js").write_text("one\ntwo\nthree\nfour\n")
            (d / "mod.js").write_text("one\nADDED a\ntwo\nthree\nADDED b\nADDED c\nfour\n")
            patch = cfg.make_patch(d / "orig.js", d / "mod.js", "main.js")
            lines = patch.splitlines()
            self.assertFalse([l for l in lines if l.startswith("-") and not l.startswith("---")], "nothing removed")
            self.assertFalse([l for l in lines if l.startswith(" ")], "no context lines, so no code of the original")
            self.assertFalse([l for l in lines if l.startswith("@@") and not l.endswith("@@")], "no original text in hunk headers")
            (d / "work").mkdir()
            (d / "work" / "main.js").write_text((d / "orig.js").read_text())
            (d / "p.patch").write_text(patch)
            cfg.apply_patch(d / "p.patch", d / "work")
            self.assertEqual((d / "work" / "main.js").read_text(), (d / "mod.js").read_text())


class Repository(unittest.TestCase):
    def test_lock_is_well_formed(self):
        lock = cfg.load_lock()
        names = [m["name"] for m in lock["mods"]]
        self.assertEqual(len(names), len(set(names)))
        for m in lock["mods"]:
            self.assertRegex(m["commit"], r"^[0-9a-f]{40}$", m["name"])
            self.assertRegex(m["repo"], r"^[\w.-]+/[\w.-]+$", m["name"])
            self.assertIn(m["kind"], ("symlink", "copy", "script"))
            if m["kind"] in ("symlink", "copy"):
                self.assertTrue(m["sub"])
            if m.get("patch"):
                self.assertTrue((ROOT / m["patch"]["path"]).is_file())

    def test_own_mods_do_not_clash_with_third_party_ones(self):
        own = {p.name for p in (cfg.CONFIG / "mods").iterdir() if p.is_dir()}
        self.assertFalse(own & {m["name"] for m in cfg.load_lock()["mods"]})

    def test_nothing_private_in_config(self):
        home = str(Path.home())
        self.assertEqual(capture.scan(cfg.CONFIG, home), [])
        mine = [*ROOT.glob("*.md"), ROOT / "install.sh", *(ROOT / "scripts").glob("*.py"), *(ROOT / "tests").glob("*.py")]
        self.assertEqual([f.name for f in mine if home in f.read_text(encoding="utf-8")], [])

    def test_layout_only_uses_mods_we_install_or_herdr_ships(self):
        layout = json.loads((cfg.CONFIG / "layouts" / "my-layout.json").read_text())
        used = set(re.findall(r'"mod":\s*"([^"]+)"', json.dumps(layout)))
        ours = {p.name for p in (cfg.CONFIG / "mods").iterdir() if p.is_dir()} | {m["name"] for m in cfg.load_lock()["mods"]}
        shipped = {"tabs", "files", "changes", "spaces", "agents", "workspace-status", "workspace-chrome", "terminals-bar", "terminals-pane", "pane", "peek", "menu", "new-menu", "machine-add", "confirm", "help", "picker", "prompt", "toast", "worktree"}
        self.assertEqual(sorted(used - ours - shipped), [], "the layout uses a mod nothing installs")


class InstallerLocalParts(unittest.TestCase):
    """The parts of the installer that do not clone anything, against a throwaway home."""

    def make(self, home, dry=False):
        return install.Installer(home, home / "src", {"mods": []}, dry=dry, backup_dir=home / ".config-backup-test")

    def test_installs_own_files_then_a_second_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            (home / "settings.json").write_text('{"zoom": 1.5, "other": true}\n')
            first = self.make(home)
            first.run_all()
            for name in ("panel-button", "my-spaces"):
                self.assertTrue((home / "mods" / name / "main.js").is_file(), name)
            self.assertTrue((home / "layouts" / "my-layout.json").is_file())
            settings = json.loads((home / "settings.json").read_text())
            self.assertEqual(settings["other"], True, "what was there stays")
            self.assertEqual(settings["zoom"], json.loads((cfg.CONFIG / "settings.json").read_text())["zoom"])
            self.assertFalse((home / "keys.json").exists(), "keys.json is not created from a partial file")
            self.assertIn("panel-button", json.loads((home / "seen.json").read_text()))
            self.assertTrue(first.backed_up, "the old settings.json was backed up")
            second = self.make(home)
            second.run_all()
            self.assertFalse(second.backed_up, "nothing was replaced the second time")

    def test_keys_are_added_to_an_existing_file_and_never_replace_a_binding(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            (home / "keys.json").write_text(json.dumps({"global": {"cmd-t": "tab.new"}, "terminal": {}}))
            self.make(home).run_all()
            keys = json.loads((home / "keys.json").read_text())
            self.assertEqual(keys["global"]["cmd-t"], "tab.new")
            self.assertEqual(keys["global"]["ctrl-shift-m"], "mod.open:herdr-kanban")

    def test_dry_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            self.make(home, dry=True).run_all()
            self.assertEqual(list(home.iterdir()), [])

    def test_a_different_folder_of_the_same_name_is_backed_up_not_lost(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            (home / "mods" / "panel-button").mkdir(parents=True)
            (home / "mods" / "panel-button" / "main.js").write_text("// somebody else's\n")
            self.make(home).run_all()
            saved = home / ".config-backup-test" / "mods" / "panel-button" / "main.js"
            self.assertEqual(saved.read_text(), "// somebody else's\n")


class CommandLine(unittest.TestCase):
    def test_dry_run_from_the_command_line_exits_clean_and_creates_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            home, src = Path(d) / "home", Path(d) / "src"
            home.mkdir()
            r = subprocess.run([sys.executable, str(ROOT / "scripts" / "install.py"), "--dry-run", "--home", str(home), "--src-dir", str(src)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("clone   jankeesvw/herdr-issues", r.stdout)
            self.assertEqual(list(home.iterdir()), [])
            self.assertFalse(src.exists())


if __name__ == "__main__":
    unittest.main()
