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

## Interactive shell

Type `sleuth` with no arguments and you drop into a session with history,
tab-completion, and the same commands you'd use from a regular shell:

```
sleuth> ask "what's a positive news story from today?"
sleuth> jobs list
sleuth> jobs schedule abc123 --daily 09:00
sleuth> exit
```

Ctrl-D or `exit`/`quit`/`q` leaves. Up/down browses history (saved at
`./.sleuth_history`). Tab completes commands and `jobs`/`drive` subcommands.

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
