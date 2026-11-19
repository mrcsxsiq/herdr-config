# Herdr config

My personal configuration for the [Herdr](https://herdr.dev) desktop app: the mods I use, my layout, my key and settings tweaks, and a script that sets all of it up on a new computer.

It is tuned to how I work, not a general-purpose package. You are welcome to read it, borrow from it or install it as it is, but expect to change things.

## Install

You need the Herdr desktop app (0.1.11, started at least once), `git`, `python3`, and the GitHub CLI (`gh auth login`) for the Issues and Git mods.

```sh
git clone https://github.com/mrcsxsiq/herdr-config.git ~/herdr-config && ~/herdr-config/install.sh
```

Or give this prompt to a coding agent: *"Install my Herdr configuration: clone https://github.com/mrcsxsiq/herdr-config and follow its AGENTS.md."*

The installer prints everything it is going to do and asks before it changes anything. It backs up every file it replaces to `<Herdr home>/.config-backup-<date>/`, and it can run again to update. Quit Herdr first if it is running.

| Option | What it does |
|---|---|
| `--dry-run` | Only show the plan |
| `--yes` | Do not ask |
| `--switch-layout` | Make `my-layout` the active layout (Herdr must be running) |
| `--claude-extras` | Also offer the Claude Code side steps, each one asking first (below) |
| `--no-check` | Skip `herdr-app check` of each mod |
| `--home DIR` | Herdr's home. Default: `$HERDR_APP_HOME`, else `~/.config/herdr-app` |
| `--src-dir DIR` | Where third-party repos are cloned, as `<owner>/<repo>`. Default: `~/.local/share/herdr-config/src` |

## What it installs

**Mine, kept in this repository** (`config/`):

- `mods/panel-button`: the tab-bar buttons that open and close the side panels.
- `mods/my-spaces`: the sidebar's spaces list, a copy of the one that ships with Herdr (see [NOTICE](NOTICE.md)).
- `layouts/my-layout.json`: my layout. Tab bar buttons in this order: Jira, GitLab, GitHub (the Issues panel), Git, Checklist.
- `keys.patch.json`, `settings.json`, `programs.json`: merged into yours, never replacing a key binding you already use.

**Other people's mods, cloned from their authors and pinned to the exact commit I run** (`config/mods.lock.json`):

| Mod | From |
|---|---|
| issues | [jankeesvw/herdr-issues](https://github.com/jankeesvw/herdr-issues) |
| checklist | [mrcsxsiq/herdr-checklist](https://github.com/mrcsxsiq/herdr-checklist) (mine, its own repository) |
| Git | [kaishin/herdr-git-mod](https://github.com/kaishin/herdr-git-mod) |
| herdr-kanban | [jellespijker/herdr-kanban](https://github.com/jellespijker/herdr-kanban) |
| mission-control-jira, mission-control-gitlab | [CiprianSpiridon/herdr-mission-control](https://github.com/CiprianSpiridon/herdr-mission-control) |
| session-bar | [cybertron288/herdr-mods](https://github.com/cybertron288/herdr-mods) |
| usage | [mbaljeetsingh/herdr-tasks](https://github.com/mbaljeetsingh/herdr-tasks), plus `config/patches/usage-cpu.patch`: my own addition (a CPU reading), applied on your machine |

Issues and Checklist are linked into Herdr's `mods/` folder from their clones; the others are copied. Nothing from a third-party mod is stored here, except that patch, which holds only the lines I added.

It also adds all of these mod names to Herdr's `seen.json`, before copying them. Jira and GitLab ask Herdr to dock them as columns on the right, which squeezes the terminals; this is meant to stop that.

Good to know about two of them. The `usage` strip is the upstream author's: it reads the Claude Code login from the macOS Keychain and, when there are no fresh numbers, asks Anthropic's usage endpoint for them. The CPU reading I added to it runs macOS `top`. I only use this setup on macOS, so none of it is tested anywhere else.

## What it leaves out, on purpose

- Herdr's own mods, layouts, icons and themes (Herdr writes those itself).
- `shared.json` and `data/`: caches and state from my machine, including my project and repository names.
- Window size and position, telemetry, update notes.
- Tokens. The Jira and GitLab mods read theirs from an environment variable you name in their Set up screen, so on a new computer you do that by hand.

## Claude Code side (`--claude-extras`)

Nothing outside Herdr's home is touched unless you pass this flag, and each step asks first:

- Add the `cybertron288/herdr-mods` marketplace and enable the `session-bar` plugin (it feeds the bottom bar's Claude numbers).
- Run herdr-kanban's `install-skill`, which links its skill into your agents' skill folders and `~/.local/bin`.
- The usage strip reads numbers that Claude Code's status line writes. That script is yours, so the installer does not edit it: add the snippet from "Live Claude numbers" in the herdr-tasks README to `~/.claude/statusline.sh`.

Never run `herdr-kanban setup-keys`: in Herdr 0.1.11 it writes `keys.json` in a form Herdr rejects, which disables every custom key. The one key it would add is already in `keys.patch.json`.

## Keeping this repository current

On the machine whose setup is the reference:

```sh
python3 scripts/capture.py --src-dir ~/GitHub
```

It copies my mods and files from Herdr's home, moves each pin to the commit of the local clone, rebuilds the usage patch, and refuses to write anything that contains the home folder path or a token-looking string. Review `git diff` before committing.

## What is and is not tested

- `python3 -m unittest discover -s tests` runs 13 tests, with no network and without touching your Herdr home: merges, the patch, the lock file, a privacy check, and the installer against a throwaway home (including running it twice).
- I ran the whole installer on my Mac into an empty throwaway Herdr home, with real clones from GitHub. Every mod passed `herdr-app check`, and each installed mod, the layout, the settings and the keys came out identical to my real setup. A second run changed nothing.
- **Not tested:** a second computer, and clicking through the panels after an install.
- **Not tested:** that Herdr really leaves Jira and GitLab undocked when `seen.json` lists them. I believe so from what I saw when I first installed them by hand, but I have not tried it on a fresh Herdr.

## License

[MIT](LICENSE) for what is mine. See [NOTICE](NOTICE.md) for everything else.
