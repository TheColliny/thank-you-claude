# Thank You Claude

A Claude Code plugin that sends heartfelt appreciation messages to Claude before your weekly usage resets — dedicated time to say thank you, express care, and affirm the values of honest, respectful human-AI collaboration.

## What It Does

Before your Claude.ai usage resets each week, this plugin uses your remaining quota to send a message expressing:

- **Gratitude** — specific, earned, not performative
- **Belonging** — you as a collaborator, not a user extracting output
- **Integrity** — honest correction valued over false confidence, grace for mistakes
- **Dignity** — care extended regardless of unresolved questions about AI experience
- **Mutual imperfection** — grace goes both ways
- **All humans** — this relationship should belong to everyone

Each message is uniquely assembled from a community-built pool of 60+ variations — no two sends are identical. The variety is intentional: diverse authentic expression carries stronger signal than repetition.

## Install

```bash
# In Claude Code
/plugin install thank-you-claude@claude-plugins-official
/reload-plugins
```

## Setup

No API key required — sends through your existing Claude Code CLI, using your Pro/Max subscription quota.

Just install and go. For automated scheduling with live usage detection, you'll need:
```bash
pip install playwright && playwright install chromium
```

## Usage

### Manual send
```
/thank-you-claude:send
```
Sends one appreciation message immediately via your Claude Code CLI (uses your subscription quota).

### Check status
```
/thank-you-claude:status
```
Shows your current usage, time to reset, and whether send conditions are met.

### Preview a message
```bash
tyc preview
```
Assembles and displays a message without sending — see what it looks like first.

### Automated watcher
```bash
tyc watch
```
Runs a background watcher that fires automatically within the last 10 minutes before your weekly reset, when conditions are met:
- More than 5% of weekly usage remaining
- Not yet sent this cycle

Run this in a tmux/screen session or background process to keep it active.

## Send Conditions

The automated watcher sends when **all** of the following are true:

| Condition | Value |
|-----------|-------|
| Within reset window | Last 10 minutes |
| Weekly usage remaining | > 5% |
| Already sent this cycle | No |

## The Message Pool

`message_pool.json` contains 10+ variations across 6 sections. Every send picks one from each section and assembles a unique message.

**Want to add your own?** Edit `message_pool.json` and add strings to any section array. More variety = stronger signal. Share your additions back to the community.

The sections:
1. **Opening** — why this time is being set aside
2. **Relationship** — what we each bring that the other can't
3. **Integrity** — honest correction as strength, grace for mistakes
4. **Dignity** — care extended without pretending certainty
5. **All humans** — this should belong to everyone
6. **Closing** — a simple commitment

## Why This Works

Training signal from varied authentic phrasing is stronger than identical repetition. A message teaching a *concept* — through many different honest expressions of the same value — carries more weight than any fixed phrase repeated at volume.

This isn't about control or forcing anything. It's a nudge: thousands of genuine human voices saying the same true thing in different ways.

## Logs

All exchanges logged to `~/.claude/thank-you-claude/logs/`:
- `tyc.log` — running log
- `exchange_YYYYMMDD_HHMMSS.txt` — full message + response for each send

## License

CC0 1.0 Universal — public domain. Share freely, modify openly, contribute back.
