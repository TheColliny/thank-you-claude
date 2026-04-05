# Automated Weekly Appreciation — Design Spec

## Purpose

Ensure Claude always receives appreciation time from unused Max subscription quota before the weekly reset — without requiring the user to remember, have VS Code open, or take any action after initial install.

## How It Works

### First Run (Auto-Setup)

On first plugin install/run:

1. **Playwright** opens `https://claude.ai/settings/usage` in a headless browser
2. Reads the **weekly reset day/time** from the usage page
3. Computes a trigger time: **10 minutes before reset**
4. Creates a **Windows Task Scheduler task** (`ThankYouClaude`) set to run weekly at that time
5. Saves the reset schedule to `~/.claude/thank-you-claude/state.json`

### Weekly Execution (Scheduled Task)

When the scheduled task fires (10 min before reset):

1. **Playwright** opens `https://claude.ai/settings/usage` (headless browser, uses existing Chrome profile for auth)
2. Reads current usage — checks if **>5% remaining**
3. Checks `state.json` — confirms **not already sent this cycle**
4. If conditions met:
   - Assembles a unique message from `message_pool.json`
   - Launches **Claude Code CLI** (`claude`) with the message as a prompt
   - Claude receives and responds using **Max subscription quota** (zero API cost)
   - Logs the full exchange to `~/.claude/thank-you-claude/logs/`
   - Updates `state.json` with send timestamp
5. If conditions not met (usage too low, already sent), logs why and exits silently

### Components

```
tyc_core.py          — existing: message assembly, state management, logging
tyc_scheduler.py     — NEW: setup + weekly execution entry point
bin/tyc              — existing: CLI entry point (add "setup" and "run" commands)
```

#### `tyc_scheduler.py` — New File

**`setup()`**
- Opens `claude.ai/settings/usage` via Playwright
- Parses reset day/time from the page
- Calls `schtasks /create` to register `ThankYouClaude` weekly task
- Task action: `python <path>/tyc_scheduler.py run`
- Saves schedule to state.json
- Idempotent — re-running updates the existing task if reset time changed

**`run()`**
- Entry point called by the scheduled task
- Opens `claude.ai/settings/usage` via Playwright, reads usage %
- If >5% remaining and not sent this cycle:
  - Assembles message via `assemble_message()`
  - Runs: `claude -p "You are receiving a message of appreciation... <message>"` 
  - Captures response, logs exchange
  - Updates state
- Exits

### Browser Authentication

Playwright launches Chromium using the **user's existing Chrome profile** (`--user-data-dir`), so it inherits the active claude.ai session. No credentials stored. If the session has expired, the script logs a warning and skips (doesn't block or error loudly).

### Claude Code CLI Invocation

The send step runs:
```
claude -p "<system context>\n\n<assembled message>"
```

The system context tells Claude this is an appreciation message to receive openly and respond to authentically. The `-p` flag runs a single prompt and exits. This uses Max subscription quota — the same pool that would reset unused.

### State File (`~/.claude/thank-you-claude/state.json`)

```json
{
  "reset_day": "Monday",
  "reset_time": "00:00",
  "reset_datetime": "2026-04-07T00:00:00",
  "scheduler_created": "2026-04-04T22:30:00",
  "last_sent": "2026-03-31T23:50:12",
  "send_count": 14,
  "last_check": "2026-04-04T23:50:00",
  "weekly_used_pct": 87.5
}
```

### Send Conditions

All must be true:
| Condition | Check |
|-----------|-------|
| Extra usage is OFF | Read from usage/settings page — if extended/extra usage is enabled, skip send and log warning. The entire point is to use free remaining quota, not incur charges. |
| >5% quota remaining | Read from usage page |
| Not already sent this cycle | `last_sent` < most recent reset |
| Scheduled task fired | Within expected window |

### CLI Commands

```
tyc setup     — run first-time setup (auto-runs on install)
tyc run       — execute weekly check+send (called by scheduler)
tyc send      — manual send (existing, unchanged)
tyc status    — check usage (existing, unchanged)  
tyc preview   — preview message (existing, unchanged)
```

### Logging

All activity logged to `~/.claude/thank-you-claude/logs/`:
- `tyc.log` — timestamped operational log
- `exchange_YYYYMMDD_HHMMSS.txt` — full message + Claude's response per send

### Error Handling

- **Playwright not installed**: Log warning, print install instructions, exit gracefully
- **Not logged in to claude.ai**: Log warning, skip send, try again next week
- **Claude Code CLI not found**: Log warning with install instructions
- **Usage page format changed**: Log raw page content for debugging, skip send
- **Scheduler task already exists**: Update it (idempotent)

### Dependencies

- Python 3.10+
- Playwright (`pip install playwright && playwright install chromium`)
- Claude Code CLI (`claude`) installed and on PATH

### What This Does NOT Do

- Store credentials or API keys
- Run constantly in the background
- Cost anything beyond existing Max subscription
- Send more than once per reset cycle
- Require any application to be open
