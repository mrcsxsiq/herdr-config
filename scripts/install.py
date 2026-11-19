#!/usr/bin/env python3
"""Install this Herdr configuration: mods, layout, keys, settings.

It shows what it will do, asks, backs up everything it replaces, and can run again later.
Standard library only. See README.md.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import herdrcfg as cfg  # noqa: E402

LAYOUT = "my-layout"


class Failure(Exception):
    pass


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


class Installer:
    def __init__(self, home, src, lock, dry, backup_dir):
        self.home, self.src, self.lock, self.dry, self.backup_dir = home, src, lock, dry, backup_dir
        self.mods = home / "mods"
        self.backed_up = False
        self.manual = []  # things the person still has to do by hand

    # -- output -------------------------------------------------------------------------------
    def say(self, text):
        print(("[dry run] " if self.dry else "") + text)

    # -- helpers ------------------------------------------------------------------------------
    def backup(self, path):
        """Move `path` (a file, folder or link) into the backup folder."""
        if not (path.exists() or path.is_symlink()):
            return
        dest = self.backup_dir / path.relative_to(self.home)
        self.say(f"  backup {path.relative_to(self.home)} -> {self.backup_dir.name}/")
        if self.dry:
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(dest))
        self.backed_up = True

    def write_file(self, path, text, label):
        if path.exists() and path.read_text(encoding="utf-8") == text:
            self.say(f"ok      {label} (already up to date)")
            return
        self.say(f"write   {label}")
        if self.dry:
            return
        if path.exists():
            dest = self.backup_dir / path.relative_to(self.home)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            self.backed_up = True
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    # -- third-party clones --------------------------------------------------------------------
    def clone(self, spec):
        """Make sure the repo is cloned under src/<owner>/<repo> and checked out at the locked commit."""
        owner, repo = spec["repo"].split("/")
        path = self.src / owner / repo
        url = f"https://github.com/{spec['repo']}.git"
        sha = spec["commit"]
        if not path.exists():
            self.say(f"clone   {spec['repo']} @ {sha[:7]} -> {path}")
            if self.dry:
                return path
            path.parent.mkdir(parents=True, exist_ok=True)
            r = run(["git", "clone", "--quiet", url, str(path)])
            if r.returncode:
                raise Failure(f"git clone {url}: {r.stderr.strip()}")
        else:
            head = run(["git", "-C", str(path), "rev-parse", "HEAD"]).stdout.strip()
            if head == sha:
                self.say(f"ok      {spec['repo']} already at {sha[:7]}")
                return path
            if run(["git", "-C", str(path), "status", "--porcelain"]).stdout.strip():
                raise Failure(f"{path} has local changes and is not at {sha[:7]}; commit or stash them first")
            self.say(f"update  {spec['repo']} -> {sha[:7]}")
            if self.dry:
                return path
        have = run(["git", "-C", str(path), "cat-file", "-e", f"{sha}^{{commit}}"]).returncode == 0
        if not have:
            r = run(["git", "-C", str(path), "fetch", "--quiet", "origin"])
            if r.returncode:
                raise Failure(f"git fetch in {path}: {r.stderr.strip()}")
        r = run(["git", "-C", str(path), "checkout", "--quiet", sha])
        if r.returncode:
            raise Failure(f"git checkout {sha[:7]} in {path}: {r.stderr.strip()}")
        return path

    # -- mods ---------------------------------------------------------------------------------
    def install_dir(self, name, source, skip=(), patch=None):
        """Put a copy of `source` at mods/<name>, applying an optional patch, unless it is already identical."""
        target = self.mods / name
        stage = None
        try:
            if self.dry and not source.exists():  # the clone has not happened in a dry run
                self.say(f"copy    mods/{name}" + (" + patch" if patch else ""))
                return
            stage = Path(tempfile.mkdtemp(prefix=f"herdr-config-{name}-")) / name
            cfg.copy_tree(source, stage, skip)
            if patch:
                cfg.apply_patch(cfg.ROOT / patch["path"], stage)
            if target.is_dir() and not target.is_symlink() and cfg.same_tree(stage, target):
                self.say(f"ok      mods/{name} (already up to date)")
                return
            self.say(f"copy    mods/{name}" + (" + patch" if patch else ""))
            if self.dry:
                return
            self.backup(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(stage), str(target))
        finally:
            if stage is not None:
                shutil.rmtree(stage.parent, ignore_errors=True)

    def install_link(self, name, source):
        target = self.mods / name
        if target.is_symlink() and target.resolve() == source.resolve():
            self.say(f"ok      mods/{name} (already linked)")
            return
        self.say(f"link    mods/{name} -> {source}")
        if self.dry:
            return
        self.backup(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(source, target_is_directory=True)

    def install_third_party(self, spec):
        name = spec["name"]
        path = self.clone(spec)
        kind = spec["kind"]
        if kind == "symlink":
            self.install_link(name, path / spec["sub"])
        elif kind == "copy":
            self.install_dir(name, path / spec["sub"], skip=spec.get("exclude", ()), patch=spec.get("patch"))
        elif kind == "script":
            self.say(f"run     {spec['repo']}/{spec['script']}")
            if not self.dry:
                env = dict(os.environ, HERDR_APP_HOME=str(self.home))
                r = run([sys.executable, str(path / spec["script"])], cwd=path, env=env)
                if r.returncode:
                    raise Failure(f"{spec['script']} of {spec['repo']} failed: {(r.stderr or r.stdout).strip()}")
        else:
            raise Failure(f"unknown kind {kind!r} for {name}")

    def own_mod_names(self):
        d = cfg.CONFIG / "mods"
        return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.is_dir() else []

    def all_mod_names(self):
        return self.own_mod_names() + [m["name"] for m in self.lock["mods"]]

    # -- config files ---------------------------------------------------------------------------
    def merge_file(self, name, patch_file, keys=False):
        target = self.home / name
        patch = json.loads(patch_file.read_text(encoding="utf-8"))
        if keys and not target.exists():
            self.say(f"skip    {name}: Herdr has not created it yet. Start Herdr once, then run this again.")
            self.manual.append(f"run install.py again after Herdr has started once, to add the key bindings ({name})")
            return
        existing = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
        if keys:
            merged, conflicts = cfg.merge_keys(existing, patch)
            for c in conflicts:
                self.say(f"keep    {name}: {c} is already bound to something else; not replaced")
                self.manual.append(f"{c} in {name} is bound to something else; set it yourself if you want ours")
        else:
            merged = cfg.merge_json(existing, patch)
        text = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"
        self.write_file(target, text, name)

    def seed_seen(self):
        """Mark our mods as already seen, so Herdr does not dock the ones that ask for a place (Jira, GitLab)."""
        target = self.home / "seen.json"
        seen = json.loads(target.read_text(encoding="utf-8")) if target.exists() else []
        text = json.dumps(cfg.add_seen(seen, self.all_mod_names())) + "\n"
        self.write_file(target, text, "seen.json")

    def verify(self):
        if not shutil.which("herdr-app"):
            self.say("skip    herdr-app check: herdr-app is not on PATH")
            return
        env = dict(os.environ, HERDR_APP_HOME=str(self.home))
        bad = []
        for name in self.all_mod_names():
            r = run(["herdr-app", "check", str(self.mods / name)], env=env)
            ok = r.returncode == 0
            self.say(f"{'check ok' if ok else 'CHECK FAILED'}  {name}")
            if not ok:
                bad.append(name)
                print((r.stdout + r.stderr).strip()[-600:])
        if bad:
            self.manual.append("herdr-app check failed for: " + ", ".join(bad))

    # -- the whole install ----------------------------------------------------------------------
    def run_all(self):
        # seen.json first, so a mod folder that appears next is never docked by Herdr.
        self.seed_seen()
        for name in self.own_mod_names():
            self.install_dir(name, cfg.CONFIG / "mods" / name)
        for spec in self.lock["mods"]:
            self.install_third_party(spec)
        layout = cfg.CONFIG / "layouts" / f"{LAYOUT}.json"
        self.write_file(self.home / "layouts" / layout.name, layout.read_text(encoding="utf-8"), f"layouts/{layout.name}")
        self.merge_file("keys.json", cfg.CONFIG / "keys.patch.json", keys=True)
        self.merge_file("settings.json", cfg.CONFIG / "settings.json")
        self.merge_file("programs.json", cfg.CONFIG / "programs.json")


def herdr_running(home):
    if not shutil.which("herdr-app"):
        return False
    try:
        return run(["herdr-app", "status"], timeout=8, env=dict(os.environ, HERDR_APP_HOME=str(home))).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def ask(question, assume_yes):
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        return False
    return input(f"{question} [y/N] ").strip().lower() in ("y", "yes", "s", "sim")


def claude_extras(lock, src, assume_yes):
    """Things outside Herdr's home that the bottom bar and the kanban use. Each one asks first."""
    print("\nClaude Code side (each step asks first):")
    if shutil.which("claude") and ask("  Add the herdr-mods marketplace and enable the session-bar plugin?", assume_yes):
        for cmd in (["claude", "plugin", "marketplace", "add", "cybertron288/herdr-mods"],
                    ["claude", "plugin", "install", "session-bar@herdr-mods"]):
            r = run(cmd)
            print(f"    {' '.join(cmd)} -> {'ok' if r.returncode == 0 else 'failed: ' + (r.stderr or r.stdout).strip()[:200]}")
    elif not shutil.which("claude"):
        print("  skip: `claude` is not on PATH (session-bar plugin: claude plugin marketplace add cybertron288/herdr-mods)")
    kanban = next((m for m in lock["mods"] if m["name"] == "herdr-kanban"), None)
    clone = src / kanban["repo"] if kanban else None
    if clone and (clone / "bin/herdr-kanban").exists() and ask(
            "  Run herdr-kanban's `install-skill` (links its skill into your agents' skill folders and ~/.local/bin)?", assume_yes):
        r = run([str(clone / "bin/herdr-kanban"), "install-skill"], cwd=clone)
        print(f"    install-skill -> {'ok' if r.returncode == 0 else 'failed: ' + (r.stderr or r.stdout).strip()[:200]}")
    print("  The usage strip reads numbers that Claude Code's status line writes. That script is yours, so it is not edited here:\n"
          "  add the snippet from 'Live Claude numbers' in https://github.com/mbaljeetsingh/herdr-tasks (README) to ~/.claude/statusline.sh.")


def main(argv=None):
    p = argparse.ArgumentParser(description="Install this Herdr configuration.")
    p.add_argument("--dry-run", action="store_true", help="only show what would happen")
    p.add_argument("--yes", "-y", action="store_true", help="do not ask before changing anything")
    p.add_argument("--home", default=os.environ.get("HERDR_APP_HOME", "~/.config/herdr-app"),
                   help="Herdr's home (default: $HERDR_APP_HOME or ~/.config/herdr-app)")
    p.add_argument("--src-dir", default=os.environ.get("HERDR_CONFIG_SRC", "~/.local/share/herdr-config/src"),
                   help="where third-party repos are cloned, as <owner>/<repo>")
    p.add_argument("--switch-layout", action="store_true", help=f"make `{LAYOUT}` the active layout (Herdr must be running)")
    p.add_argument("--claude-extras", action="store_true", help="also offer the Claude Code side steps")
    p.add_argument("--no-check", action="store_true", help="skip `herdr-app check` of each mod")
    args = p.parse_args(argv)

    home, src = Path(args.home).expanduser(), Path(args.src_dir).expanduser()
    lock = cfg.load_lock()
    for tool in ("git",):
        if not shutil.which(tool):
            sys.exit(f"{tool} is required but was not found.")
    if not home.is_dir():
        sys.exit(f"{home} does not exist. Install and start the Herdr desktop app once, then run this again.")
    if not shutil.which("gh"):
        print("note: `gh` is not installed or not on PATH. The Issues and Git mods need it (gh auth login).")
    if lock.get("herdr"):
        v = run(["herdr-app", "--version"]).stdout.strip() if shutil.which("herdr-app") else ""
        if v and lock["herdr"] not in v:
            print(f"note: this configuration was made on Herdr {lock['herdr']}; you have {v}.")
    running = herdr_running(home)
    if running:
        print("warning: Herdr is running. Quit it first if you can: it may overwrite seen.json when it exits,\n"
              "         and the Jira and GitLab mods could then dock themselves into your layout.")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_dir = home / f".config-backup-{stamp}"
    print(f"Herdr home: {home}\nClones:     {src}\n")
    plan = Installer(home, src, lock, dry=True, backup_dir=backup_dir)
    try:
        plan.run_all()
    except (Failure, RuntimeError) as e:
        sys.exit(f"error: {e}")
    if args.dry_run:
        return 0
    if not args.yes and not ask("\nGo ahead?", False):
        sys.exit("Nothing changed." if sys.stdin.isatty() else "Not a terminal: pass --yes to run without asking.")
    print()
    real = Installer(home, src, lock, dry=False, backup_dir=backup_dir)
    try:
        real.run_all()
        if not args.no_check:
            print()
            real.verify()
    except (Failure, RuntimeError) as e:
        sys.exit(f"error: {e}")
    if args.switch_layout:
        r = run(["herdr-app", "do", "layout.switch", "--name", LAYOUT], env=dict(os.environ, HERDR_APP_HOME=str(home)))
        print(f"\nlayout.switch {LAYOUT}: {'ok' if r.returncode == 0 else 'failed (is Herdr running?) ' + r.stderr.strip()[:200]}")
    else:
        real.manual.append(f"switch to the layout: `herdr-app do layout.switch --name {LAYOUT}` (or cmd-shift-l)")
    if args.claude_extras:
        claude_extras(lock, src, args.yes)
    real.manual.append("Jira and GitLab: open each panel and run its Set up; the token comes from an environment variable you name there")
    real.manual.append("`gh auth login`, if you have not (Issues, Git)")
    print("\nDone." + (f" Backups of what was replaced: {backup_dir}" if real.backed_up else ""))
    print("Still to do by hand:\n  - " + "\n  - ".join(real.manual))
    return 0


if __name__ == "__main__":
    sys.exit(main())
