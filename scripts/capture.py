#!/usr/bin/env python3
"""Refresh this repository from the Herdr setup on this machine.

Copies the mods and files that are yours, moves each pin in config/mods.lock.json to the commit of
your local clone, and rebuilds the patch for mods you edited. It never touches Herdr's home, and it
refuses to write anything that contains your home folder path or something that looks like a token.
"""
import argparse
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import herdrcfg as cfg  # noqa: E402
from install import run  # noqa: E402

SECRET = re.compile(r"(ghp_|gho_|github_pat_|glpat-|xox[bp]-|sk-ant-|AKIA[0-9A-Z]{12})")
OWN_FILES = {"layouts/my-layout.json": "layouts/my-layout.json", "settings.json": "settings.json", "programs.json": "programs.json"}


def scan(root, home_path):
    """Return the files under `root` that hold the person's home path or a token-looking string."""
    bad = []
    for f in Path(root).rglob("*"):
        if not f.is_file() or f.suffix in (".png", ".jpg", ".gif"):
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        if home_path in text or SECRET.search(text):
            bad.append(f)
    return bad


def main(argv=None):
    p = argparse.ArgumentParser(description="Refresh this repository from this machine's Herdr setup.")
    p.add_argument("--home", default=os.environ.get("HERDR_APP_HOME", "~/.config/herdr-app"))
    p.add_argument("--src-dir", default="~/GitHub", help="where your clones of the third-party repos are, as <owner>/<repo>")
    p.add_argument("--no-pins", action="store_true", help="do not move the commits in mods.lock.json")
    args = p.parse_args(argv)
    home, src = Path(args.home).expanduser(), Path(args.src_dir).expanduser()

    for name in sorted(q.name for q in (cfg.CONFIG / "mods").iterdir() if q.is_dir()):
        source = home / "mods" / name
        if not source.is_dir():
            sys.exit(f"missing {source}")
        shutil.rmtree(cfg.CONFIG / "mods" / name)
        cfg.copy_tree(source.resolve(), cfg.CONFIG / "mods" / name)
        print(f"copied   mods/{name}")
    for rel, dest in OWN_FILES.items():
        shutil.copy2(home / rel, cfg.CONFIG / dest)
        print(f"copied   {rel}")

    if not args.no_pins:
        lock = cfg.load_lock()
        for spec in lock["mods"]:
            clone = src / spec["repo"]
            if not clone.is_dir():
                sys.exit(f"no clone of {spec['repo']} at {clone}; pass --src-dir or --no-pins")
            head = run(["git", "-C", str(clone), "rev-parse", "HEAD"]).stdout.strip()
            if head != spec["commit"]:
                print(f"pin      {spec['name']}: {spec['commit'][:7]} -> {head[:7]}")
                spec["commit"] = head
            if spec.get("patch"):
                file = spec["patch"]["file"]
                text = cfg.make_patch(clone / spec["sub"] / file, home / "mods" / spec["name"] / file, file)
                (cfg.ROOT / spec["patch"]["path"]).write_text(text, encoding="utf-8")
                print(f"patch    {spec['name']}: {text.count(chr(10) + '@@') + text.startswith('@@')} hunks")
        cfg.write_json(cfg.LOCK, lock)

    bad = scan(cfg.CONFIG, str(Path.home()))
    if bad:
        sys.exit("refusing to leave these files as they are (home path or token-like text inside):\n  " + "\n  ".join(map(str, bad)))
    print("\nDone. Review `git diff` before committing.")


if __name__ == "__main__":
    main()
