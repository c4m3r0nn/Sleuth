# sleuth

A pocket research assistant for the terminal. Asks the big LLMs to go snoop the
web, files everything in a tidy SQLite drawer, and (optionally) pings your
phone when overnight jobs wrap. Built to live happily on a Raspberry Pi.

```
   .--.    .  .  ___ . . _____ . .
  /    \   |  | /__\ | |   |   |_|
  \    /   \__/ \__  \_/   |   | |
   '--'    sleuth - the research gremlin
```

## What it does

- Throws a question at any of GPT-5.5, Claude Opus 4.7, Gemini 3.1 Pro (etc.)
  with web search switched on by default.
- Saves every run to a local SQLite drawer (`data/sleuth.db`) with citations,
  token counts, and the raw answer.
- Schedules recurring research jobs with a friendly grammar (`--daily 09:00`,
  `--weekly mon,wed --at 18:00`, `--every 15m`) or raw cron if you must.
- Optionally mirrors each finished run to Google Drive as a Doc.
- Optionally taps you on the shoulder via Telegram when a job finishes.

## Quickstart

```bash
git clone https://github.com/c4m3r0nn/LLM_Research_CLI.git sleuth
cd sleuth
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
sleuth setup            # guided walk-through; writes .env
sleuth                  # opens the interactive shell
```

Or skip the shell and use one-shot commands:

```bash
sleuth ask "what happened in AI this week?"
```

On a Raspberry Pi 5, install the same way (no system packages required).

## Install globally (so `sleuth` works from any directory)

### Option A: pipx (recommended)

`pipx` installs each tool in its own isolated venv and puts a shim on your
`$PATH` so you can run `sleuth` from anywhere.

```bash
# macOS
brew install pipx
pipx ensurepath

# Raspberry Pi (Debian/Ubuntu)
sudo apt install pipx
pipx ensurepath

# then, from the project dir:
pipx install -e .
```

Reopen your shell. `sleuth` should now work from any directory. To upgrade
later: `git pull && pipx reinstall sleuth-cli`.

### Option B: drop a symlink on PATH (works on a fresh Pi, no extra tools)

```bash
mkdir -p ~/.local/bin
ln -sf "$PWD/.venv/bin/sleuth" ~/.local/bin/sleuth
# make sure ~/.local/bin is on PATH (usually is on Pi OS / modern macOS)
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc   # or ~/.zshrc
exec $SHELL -l
```

The symlink keeps editable installs working: `git pull` is enough to update
the code, no reinstall step needed.

### Verify

```bash
which sleuth     # should print the path on PATH
sleuth --version
```

## Interactive shell

Type `sleuth` with no arguments and you drop into a session with history,
live autocomplete, and command walkthroughs.

**Walkthrough mode (recommended).** Type the bare command name, hit enter,
and sleuth prompts you for each input - no quotes needed.

```
sleuth> ask
  what should sleuth dig up? what happened in AI today
  tweak provider/model? [y/N]
sleuth> jobs new
  job name (e.g. 'morning-news') morning-ai-news
  research prompt summarise the top 5 AI stories from the last 24 hours
  which provider?
     <- [1] openai
        [2] anthropic
        [3] google
    > 1
  ...
sleuth> jobs schedule
  which job?
        [1] morning-ai-news (a1b2c3d4)
    > 1
  schedule kind?
     <- [1] daily
        [2] weekly
        [3] hourly
        ...
    > 1
  time (HH:MM, 24h) 09:00
```

**Inline mode.** You can also still pass arguments yourself:

```
sleuth> ask whats happening today        # no quotes needed for one-line prompts
sleuth> jobs schedule abc123 --daily 09:00
sleuth> exit
```

**Autocomplete.** Suggestions pop up as you type. `Tab` cycles them; arrow-down
+ `Enter` accepts the highlighted one (and stays on the line so you can keep
typing). `Enter` on its own submits.

Ctrl-D or `exit`/`quit`/`q` leaves. Up/down browses history (saved at
`./.sleuth_history`).

## Commands at a glance

| Command | What it does |
| --- | --- |
| `sleuth` | Open the interactive shell. |
| `sleuth shell` | Same, explicit form. |
| `sleuth ask "..."` | One-off research with the default model. |
| `sleuth ask --model claude-opus-4-7 "..."` | Pick a specific model. |
| `sleuth models` | List available models per provider. |
| `sleuth jobs new` | Define a recurring research job. |
| `sleuth jobs list` | Show saved jobs and schedules. |
| `sleuth jobs show <id>` | Inspect a single job. |
| `sleuth jobs edit <id> --prompt "..." --model ...` | Patch any field on a job. |
| `sleuth jobs run <id>` | Run a saved job once, right now. |
| `sleuth jobs schedule <id> --daily 09:00` | Hand the job to system cron. |
| `sleuth jobs unschedule <id>` | Take it back off cron. |
| `sleuth jobs crontab` | Show the cron entries sleuth installed. |
| `sleuth jobs logs <id>` | Tail the log file for a scheduled job. |
| `sleuth jobs check <id>` | Diagnose a scheduled job (cron entry, log status, OS-specific gotchas). |
| `sleuth jobs rm <id>` | Delete the job. |
| `sleuth history` | See past runs. |
| `sleuth show <run_id>` | Dump a past run's full output. |
| `sleuth drive auth` | Authorise Google Drive sync (one-time). |
| `sleuth ping` | Send a test nudge to every configured channel. |
| `sleuth setup` | Interactive wizard for first-run configuration. |
| `sleuth init` | Show config status (no changes). |

## Schedule grammar

```bash
sleuth jobs schedule abc123 --daily 09:00
sleuth jobs schedule abc123 --weekly mon,wed,fri --at 18:30
sleuth jobs schedule abc123 --hourly
sleuth jobs schedule abc123 --every 15m
sleuth jobs schedule abc123 --monthly --day 1 --at 06:00
sleuth jobs schedule abc123 --cron "*/30 9-17 * * 1-5"   # raw escape hatch
```

Behind the scenes each schedule becomes one entry in your user crontab, tagged
so `sleuth jobs unschedule` can find it again.

## Provider notes (May 2026)

- **OpenAI**: Responses API + built-in `web_search` tool. Default model is
  `gpt-5.5`.
- **Anthropic**: Messages API + server-side `web_search_20250305`. Org admin
  must enable web search in Console first.
- **Google**: New `google-genai` SDK with `google_search` grounding. Most 3.x
  text models still carry a `-preview` suffix; `gemini-3.1-flash-lite` is
  the only fully stable tier.

## Scheduled jobs and cron troubleshooting

When you run `sleuth jobs schedule <id> --daily 09:00` (or whatever),
sleuth writes one line to your user crontab. At the scheduled time, cron
runs the equivalent of `python -m sleuth _exec <id>` and writes everything
to `logs/<id>.log`.

If a scheduled job seems not to fire, in this order:

1. `sleuth jobs check <id>` - shows the cron entry, log status, and the
   macOS gotcha if applicable.
2. `sleuth jobs logs <id>` - tails the log file. If it doesn't exist
   yet, cron has never actually run the entry.
3. `crontab -l | grep sleuth` - confirms the entry is installed.
4. `sleuth jobs run <id>` - runs the job once, immediately, without cron.
   If this works but the scheduled one doesn't, the problem is cron, not
   sleuth.

### The macOS gotcha

On macOS, the `cron` daemon needs **Full Disk Access** to run anything in
your home directory. Without it, cron silently does nothing - no errors,
no log lines, just nothing.

Open System Settings -> Privacy & Security -> Full Disk Access -> `+` ->
press cmd+shift+G and type `/usr/sbin/cron`. Tick the box, restart your
mac (yes really), then try again.

On Raspberry Pi this isn't a thing - cron just works.

### Verify on a Pi

```bash
systemctl status cron     # should be active (running)
crontab -l                # should show the sleuth entries
sleuth jobs check <id>
```

### Catching up after the Pi was off

Vanilla cron does not run a missed entry when a powered-off machine comes
back. sleuth handles this with a `@reboot` crontab line that runs
`sleuth catchup` — which checks every scheduled job and runs any whose
most-recent fire didn't actually happen.

`sleuth jobs schedule` installs that `@reboot` line automatically. If you
scheduled jobs on an older version, install it manually once:

```bash
sleuth catchup --install
crontab -l | grep sleuth-catchup    # confirms the @reboot line is present
```

You can also run catch-up by hand any time:

```bash
sleuth catchup            # run missed jobs now
sleuth catchup --dry-run  # just list what would run
```

Catch-up runs each missed job **once**, not once per missed slot — fresh
research beats five stale snapshots.

## Notifications

sleuth can ping you on **Telegram**, **Discord**, or both when scheduled jobs
finish. The setup wizard walks you through either; you can also just put the
right values in `.env`:

```dotenv
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/.../...
```

`sleuth ping` sends a test message through everything that's configured.

## Development

```bash
pip install -e '.[dev]'
pytest
```

The project follows red-green TDD: tests in `tests/` cover the schedule
grammar, SQLite store, notifiers, the verb rotator, the setup-wizard env
writer, and the REPL parser. Run `pytest` after any change.

## License

MIT.
