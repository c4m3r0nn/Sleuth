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
git clone git@github.com:c4m3r0nn/LLM_Research_CLI.git sleuth
cd sleuth
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env  # fill in at least one provider key
sleuth ask "what happened in AI this week?"
```

On a Raspberry Pi 5, install the same way (no system packages required).

## Commands at a glance

| Command | What it does |
| --- | --- |
| `sleuth ask "..."` | One-off research with the default model. |
| `sleuth ask --model claude-opus-4-7 "..."` | Pick a specific model. |
| `sleuth models` | List available models per provider. |
| `sleuth jobs new` | Wizard for a recurring research job. |
| `sleuth jobs list` | Show saved jobs and schedules. |
| `sleuth jobs run <id>` | Run a saved job once, right now. |
| `sleuth jobs schedule <id> --daily 09:00` | Hand the job to system cron. |
| `sleuth jobs unschedule <id>` | Take it back off cron. |
| `sleuth jobs rm <id>` | Delete the job. |
| `sleuth history` | See past runs. |
| `sleuth show <run_id>` | Dump a past run's full output. |
| `sleuth drive auth` | Authorise Google Drive sync (one-time). |
| `sleuth ping` | Send a test Telegram nudge. |
| `sleuth init` | Walk through first-run setup. |

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

## License

MIT.
