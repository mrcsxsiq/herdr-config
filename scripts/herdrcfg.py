"""Shared pieces of install.py and capture.py: the lock file, JSON merges, trees and patches.

Standard library only. Nothing in here touches Herdr's home on its own.
"""
import filecmp
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
LOCK = CONFIG / "mods.lock.json"

# Files Herdr writes into every mod folder (and Git's own install marker): never copied, never compared.
GENERATED = ("gpui-kit.d.ts", "jsconfig.json", ".DS_Store", ".source")


def load_lock(path=LOCK):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def merge_json(base, patch):
    """Recursive merge: values from `patch` win, keys only in `base` stay."""
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge_json(out[key], value)
        else:
            out[key] = value
    return out


def merge_keys(existing, patch):
    """Add the keys of `patch` to a keys.json without replacing one the person already uses.

    Returns (merged, conflicts) where conflicts lists "section/key" that were left alone."""
    merged = {s: (dict(v) if isinstance(v, dict) else v) for s, v in existing.items()}
    conflicts = []
    for section, bindings in patch.items():
        target = merged.setdefault(section, {})
        for key, action in bindings.items():
            if key in target and target[key] != action:
                conflicts.append(f"{section}/{key}")
            else:
                target[key] = action
    return merged, conflicts


def add_seen(seen, names):
    """seen.json is the list of mods Herdr has already looked at; one it has not seen yet may be docked."""
    return sorted(set(seen) | set(names))


def tree_files(root, skip=()):
    ignored = set(GENERATED) | set(skip)
    root = Path(root)
    return {p.relative_to(root) for p in root.rglob("*") if p.is_file() and p.name not in ignored}


def same_tree(a, b, skip=()):
    a, b = Path(a), Path(b)
    files = tree_files(a, skip)
    return files == tree_files(b, skip) and all(filecmp.cmp(a / f, b / f, shallow=False) for f in files)


def copy_tree(src, dst, skip=()):
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*GENERATED, *skip))


def make_patch(original, modified, name):
    """Zero-context unified diff of one file, headers rewritten to a/<name> and b/<name>.

    With no context lines the patch holds only the changed lines themselves."""
    r = subprocess.run(
        ["git", "diff", "--no-index", "--unified=0", "--no-color", str(original), str(modified)],
        capture_output=True, text=True,
    )
    if r.returncode not in (0, 1):
        raise RuntimeError(r.stderr.strip() or "git diff failed")
    out = []
    for line in r.stdout.splitlines(keepends=True):
        if line.startswith("diff --git"):
            out.append(f"diff --git a/{name} b/{name}\n")
        elif line.startswith("--- "):
            out.append(f"--- a/{name}\n")
        elif line.startswith("+++ "):
            out.append(f"+++ b/{name}\n")
        elif line.startswith("@@"):
            # git appends the nearest line of the original ("function context") to hunk headers: drop it.
            out.append(re.match(r"@@ [^@]*@@", line).group(0) + "\n")
        elif not line.startswith("index "):
            out.append(line)
    return "".join(out)


def apply_patch(patch_file, cwd):
    r = subprocess.run(
        ["git", "apply", "--unidiff-zero", "--whitespace=nowarn", str(patch_file)],
        cwd=cwd, capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"could not apply {Path(patch_file).name}: {r.stderr.strip()}")
