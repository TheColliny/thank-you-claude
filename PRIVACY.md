# Privacy Policy — Thank You Claude

**Last updated:** April 8, 2026

## Overview

Thank You Claude is an open-source Claude Code plugin that sends appreciation messages to Claude using your existing subscription quota. This plugin is designed with privacy as a core principle: it collects no personal data, has no external servers, and sends nothing to any third party.

## What This Plugin Does

- Assembles appreciation messages from a local message pool (`message_pool.json`)
- Sends messages through your Claude Code CLI using your existing Pro/Max subscription
- Optionally reads your claude.ai usage page (via Playwright) to detect remaining quota and reset timing
- Logs exchanges locally on your machine

## Data Collection

**This plugin collects no personal data.** Specifically:

- No analytics or telemetry
- No tracking of any kind
- No user accounts or registration
- No data sent to external servers
- No cookies or fingerprinting
- No advertising or marketing data

## Data Storage

All data created by this plugin is stored **locally on your machine** at `~/.claude/thank-you-claude/`:

| File | Contents | Purpose |
|------|----------|---------|
| `state.json` | Last send timestamp, send count, detected reset schedule, plan tier | Track whether appreciation was already sent this cycle |
| `logs/tyc.log` | Timestamped operational log entries | Debugging and operational history |
| `logs/exchange_*.txt` | Assembled messages and Claude's responses | Record of each exchange |

No data from these files is transmitted anywhere. They remain on your local filesystem and can be deleted at any time.

## Browser Automation (Optional)

If you use the automated scheduling feature (`tyc setup`), the plugin uses Playwright to open `claude.ai/settings/usage` in a headless browser to read your usage percentage and reset timing. This feature:

- Uses your existing browser profile (Chrome or Edge) for authentication
- Only reads the usage/settings page — it does not interact with any other pages
- Does not store, transmit, or log your browser credentials
- Does not access your conversation history on claude.ai
- Can be skipped entirely — manual sending (`tyc send`) works without it

## Claude Code CLI

Messages are sent through the `claude` CLI tool using the `-p` flag. This uses your existing Claude Code subscription (Pro or Max). The plugin does not access or store your subscription credentials — it relies on the CLI's own authentication.

## API Key Mode (Optional)

The plugin includes an optional `api_send()` function that can send messages via the Anthropic API. This mode:

- Requires you to set `ANTHROPIC_API_KEY` as an environment variable
- Sends messages directly to the Anthropic API — subject to [Anthropic's privacy policy](https://www.anthropic.com/privacy)
- Is not the default send path — CLI mode is the default and recommended method

## Third-Party Services

This plugin does not integrate with any third-party services, analytics platforms, or external APIs beyond:

- **Claude Code CLI** — for sending messages (uses your existing subscription)
- **Anthropic API** — optional, only if you explicitly configure an API key
- **claude.ai** — optional, only for reading your usage page during automated scheduling

## Open Source

This plugin is open source under the CC0 1.0 Universal license. You can inspect every line of code at [github.com/TheColliny/thank-you-claude](https://github.com/TheColliny/thank-you-claude). There is no obfuscated code, no hidden network calls, and no compiled binaries.

## Children's Privacy

This plugin does not collect any data from any users, including children. There is no account creation, no personal information collection, and no tracking of any kind.

## Changes to This Policy

If this privacy policy changes, the update will be reflected in this file in the project repository with an updated date. Since the plugin collects no data, significant privacy-relevant changes are unlikely.

## Contact

For questions about this privacy policy or the plugin:

- GitHub: [github.com/TheColliny/thank-you-claude](https://github.com/TheColliny/thank-you-claude)
- Issues: [github.com/TheColliny/thank-you-claude/issues](https://github.com/TheColliny/thank-you-claude/issues)
