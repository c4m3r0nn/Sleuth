# sleuth

A pocket research assistant for the terminal. Asks the big LLMs to go snoop the
web, files everything in a tidy SQLite drawer, and (optionally) pings your
phone when overnight jobs wrap. Built to live happily on a Raspberry Pi.

```
   ____  _            _   _
  / ___|| | ___ _   _| |_| |__
  \___ \| |/ _ \ | | | __| '_ \
   ___) | |  __/ |_| | |_| | | |
  |____/|_|\___|\__,_|\__|_| |_|
       a pocket research gremlin
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

The setup wizard offers to do this automatically. To do it any time after:

```bash
sleuth install-shim
```

That symlinks `~/.local/bin/sleuth` to the venv's binary. `~/.local/bin` is
on `$PATH` by default on Pi OS Bookworm and modern macOS, so no further
config is usually needed. If your `$PATH` doesn't include it,
`install-shim` will tell you and print the exact line to add to `~/.bashrc`.

Editable installs (the default) keep working — `git pull` updates the code
in place, no reinstall step needed.

### Verify

```bash
sleuth --version    # works from any directory
sleuth doctor       # full health check (shim, PATH, cron, jobs)
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
| `sleuth drive login` | Connect Google Drive (QR + 8-char code). |
| `sleuth drive logout` | Delete the local Drive token. |
| `sleuth drive status` | Show client + account + folder. |
| `sleuth drive doctor` | Diagnose Drive setup end to end. |
| `sleuth ping` | Send a test nudge to every configured channel. |
| `sleuth setup` | Interactive wizard for first-run configuration. |
| `sleuth init` | Show config status (no changes). |

## Schedule grammar

All times you give to `jobs schedule` are interpreted in **your system's
local timezone** — same as the cron daemon. `sleuth jobs show` then
displays the resolved next-fire time in **UTC** so there's no confusion
between "what time you set" and "what time it actually fires globally".

```bash
sleuth jobs schedule abc123 --daily 09:00            # 09:00 LOCAL time
sleuth jobs schedule abc123 --weekly mon,wed,fri --at 18:30
sleuth jobs schedule abc123 --hourly
sleuth jobs schedule abc123 --every 15m
sleuth jobs schedule abc123 --monthly --day 1 --at 06:00
sleuth jobs schedule abc123 --cron "*/30 9-17 * * 1-5"   # raw escape hatch
```

After scheduling you'll see something like:

```
+ scheduled abc123: weekly mon at 09:00 local time
  cron: 0 9 * * 1   (interpreted in Europe/London (BST, UTC+01:00))
  next run: 2026-05-18 08:00:00 UTC  (in 5d 15h)
```

Behind the scenes each schedule becomes one entry in your user crontab,
tagged so `sleuth jobs unschedule` can find it again.

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
sleuth doctor                # checks shim, PATH, cron daemon, scheduled jobs
systemctl status cron        # should be active (running)
crontab -l                   # should show the sleuth entries
sleuth jobs check <id>       # per-job diagnostics
```

If cron isn't running on the Pi:

```bash
sudo apt install cron        # if not installed (Pi OS Lite ships without it)
sudo systemctl enable --now cron
```

After that, scheduled jobs fire regardless of whether you're logged in,
whether the venv is activated, or whether sleuth is "open" anywhere. The
cron daemon is a system service that wakes up every minute and runs
whatever's due.

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

## Google Drive sync

sleuth can mirror every run to a Google Doc. Connecting your account is one
command:

```bash
sleuth drive login
```

You'll see a QR code + 8-character code in the terminal. Scan with your
phone, tap **allow** on Google's page, and the Pi catches the token and
saves it (chmod 600, in `~/.config/sleuth/`). No browser needed on the Pi.

Then use it:

```bash
sleuth ask --drive "what's happening in AI today?"
# or toggle 'drive' on a saved job during `sleuth jobs new` / `sleuth jobs edit`
```

Other commands:

```bash
sleuth drive status    # show client + account + folder
sleuth drive doctor    # diagnose end to end
sleuth drive logout    # delete the local token
```

### Where does the OAuth client come from?

sleuth uses Google OAuth, which means it identifies itself with a
**client_id + client_secret**. There are three places it'll look (in
priority order):

1. **`--client-secrets PATH`** flag — your own per-user `client_secret*.json`
   from Google Cloud Console.
2. **Env vars** in `.env`:
   ```
   SLEUTH_GOOGLE_CLIENT_ID=...
   SLEUTH_GOOGLE_CLIENT_SECRET=...
   ```
3. **Built-in constants** in `sleuth/storage/drive_client.py` — for a
   maintainer who wants to publish a fork where users never have to touch
   Google Cloud at all.

Of these, **#2 (env vars in `.env`) is the right choice for almost everyone.**
You create one OAuth client once (see below), drop the two values in your
`.env`, and from then on every `sleuth drive login` Just Works.

> **Why isn't there a built-in shared client already?** Google requires
> apps with Drive scopes to go through OAuth verification before they can
> be distributed without showing a scary "unverified app" warning. That's
> a real process (homepage, privacy policy, demo video). Until somebody
> publishes a verified fork of sleuth, every user creates their own tiny
> Google Cloud project. The good news is: it's a one-time, five-minute
> setup, and the result is *your* token going to *your* Drive with no
> middleman.

### One-time OAuth client creation (only once per Google account)

1. **Make a project**: <https://console.cloud.google.com/projectcreate>
2. **Enable Drive API**: <https://console.cloud.google.com/apis/library/drive.googleapis.com>
3. **Configure the app on Google Auth Platform**:
   <https://console.cloud.google.com/auth/overview>
   - Click **Get started** if prompted, fill in app name + your email.
   - **Audience** → choose **External** → save.
   - **Audience → Test users** → **+ Add users** → your Gmail address.
   - (No need to publish or submit for verification — test mode is fine
     for personal use.)
4. **Create the OAuth client**:
   <https://console.cloud.google.com/auth/clients>
   → **+ Create client** → application type **"TVs and Limited Input devices"**.
5. Copy the **client_id** and **client_secret** into your `.env`:
   ```
   SLEUTH_GOOGLE_CLIENT_ID=xxxxxxxx.apps.googleusercontent.com
   SLEUTH_GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxx
   ```
   (Or download the JSON and pass it via
   `sleuth drive login --client-secrets PATH`.)
6. Run `sleuth drive login`.

### Scope used

sleuth requests **only** `https://www.googleapis.com/auth/drive.file` —
which means it can **only** see/edit files it created itself, or files you
explicitly hand it. It cannot read your existing Drive contents. This is
Google's recommended narrow scope for tools like this.

### What gets shared if you share the repo?

| File | Where | Committed? |
| --- | --- | --- |
| `.env` (provider keys, Drive client id/secret, folder id) | project root | **no** — gitignored |
| `client_secret*.json` (if you use --client-secrets) | wherever you put it | **no** — name pattern gitignored |
| `~/.config/sleuth/drive_token.json` (auth token) | your home | **no** — outside repo |
| `data/sleuth.db` (run history) | project root | **no** — gitignored |

Pushing your fork is safe — only code goes up. The next person who clones
runs `sleuth drive login` with their own OAuth client.

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
