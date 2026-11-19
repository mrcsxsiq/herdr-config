# Instructions for coding agents

This repository is its owner's personal Herdr configuration. When asked to install it:

1. Check the prerequisites: the Herdr desktop app has been started once (`~/.config/herdr-app` exists, or `$HERDR_APP_HOME`), `git`, `python3`, and `gh` signed in (`gh auth status`). If Herdr is running, ask the person to quit it first.
2. Run `./install.sh --dry-run` and show the plan to the person.
3. After they agree, run `./install.sh --yes`. Add `--switch-layout` only if they ask for the layout to become active, and `--claude-extras` only if they ask for the Claude Code side steps.
4. Read the output. It ends with a list of things the person still has to do by hand (Jira and GitLab tokens, `gh auth login`, switching the layout). Pass that list on; do not try to do those yourself.

Rules:

- Do not edit the person's layout, `keys.json`, `settings.json` or `seen.json` by hand: the installer merges them and backs them up.
- Never run `herdr-kanban setup-keys`. It writes `keys.json` in a form Herdr 0.1.11 rejects.
- Do not copy third-party mods into this repository. They are cloned from their authors at the commits in `config/mods.lock.json`.
- Do not commit or push unless asked.
- `python3 -m unittest discover -s tests` must pass before any change to the scripts is called done.
