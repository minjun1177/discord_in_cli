# Discord in CLI

Use Discord from your terminal — read messages in real time, send messages, manage files, all from the command line.

This is the **Rust rewrite** of the original Python implementation. It keeps the same feature set, the same `settings.json` schema, and the same terminal output style, built with [serenity](https://github.com/serenity-rs/serenity) on tokio.

## Features

- 📨 Live message stream in the terminal — bot usernames in purple, mentions highlighted in orange
- ✍️ Send messages by typing; `@Name` is automatically converted to a real Discord mention
- 🔔 Alert highlight when you're mentioned or `@everyone` is used
- 🗑️ See edits (`Modified: before -> after`) and deletions in real time
- 💾 Save messages to a file (plain text or JSON-lines format)
- 🖼️ Render image attachments as Unicode half-block art in the terminal (`/img open`)
- 🃏 Render embeds and UI components (buttons, select menus) as panels (`/embed open`)
- 📎 Upload and download files from the terminal
- ↩️ Edit and reply to recent messages (`/edit`, `/reply`)

## Requirements

- Rust 1.75+ (edition 2021)
- A Discord bot token with **MESSAGE CONTENT INTENT** and **SERVER MEMBERS INTENT** enabled (see the Discord Developer Portal)
- A Discord server ID and channel ID (enable *Developer Mode* in Discord → right-click → "Copy Server ID" / "Copy Channel ID")

## Setup

```bash
cp settings.inc.json settings.json
# fill in SERVER_ID, CHANNEL_ID, TOKEN

cargo build --release
./target/release/discord_in_cli
```

## Commands

| Input | What it does |
|-------|--------------|
| `/select <channel_id>` | Select a channel to monitor and chat in (fetches recent history) |
| `/exit` | Deselect the channel and show the channel list again |
| `/status` | Show which server/channel the bot is connected to |
| `/embed open` / `/embed close` | Toggle embed (card message) rendering |
| `/img open` / `/img close` | Toggle image rendering in the terminal |
| `/stop` | Shut the bot down cleanly |
| `/setrpc <text> [online\|idle\|dnd\|offline]` | Change the bot's activity / presence |
| `/refresh` | Re-fetch the recent messages of the selected channel |
| `/messages` / `/messages all` | List your (or all) recent messages with `~N` indices |
| `/edit <new text>` | Edit your most recent message |
| `/edit ~N <new text>` | Edit the Nth most recent message |
| `/editmsg <id> <new text>` | Edit a message by its ID |
| `/reply <text>` / `/reply ~N <text>` | Reply to the most recent (or Nth) message |
| `/uploadfile <path>` | Upload a local file to the current channel |
| `/downloadfile ~N [index] [path]` | Download an attachment from the Nth recent message |
| `/downloadfile <msg_id> [index] [path]` | Download an attachment by message ID |
| `just type this` | Sends the text as a message (prefixed with `USERNAME:`) |

## Settings (`settings.json`)

| Key | Description | Default |
|-----|-------------|---------|
| `SERVER_ID` | Server (guild) to monitor | *required* |
| `CHANNEL_ID` | Default channel to monitor | *required* |
| `TOKEN` | Bot token (keep it secret!) | *required* |
| `ALLOW_MENTION_EVERYONE` | Allow sending `@everyone` | `false` |
| `SAVE_MESSAGES` | Save messages to a file | `true` |
| `SAVE_AS_JSON` | Save as JSON-lines instead of plain text | `false` |
| `SAVE_FILENAME` | Log file name | `messages.log` |
| `FETCH_HISTORY_LIMIT` | How many past messages to fetch on `/select` | `10` |
| `EMBED_VIEW_default` | Start with embed rendering on | `false` |
| `IMG_VIEW_default` | Start with image rendering on | `false` |
| `MSG_HISTORY_MAX` | Recent-message buffer size (for `/edit`, `/reply`) | `50` |
| `USERNAME` | Name prefix shown when sending messages | `Sparky` |
| `WATCH_ID` | User IDs whose mentions trigger the orange highlight | `[]` |

`settings.json` is in `.gitignore` — never commit your token.

## Project layout

```
src/
├── main.rs      ← entry point: loads settings, builds the client
├── config.rs    ← settings.json parsing
├── state.rs     ← shared runtime state (selected channel, message buffer, toggles)
├── handler.rs   ← gateway event handlers (ready / message / edit / delete)
├── console.rs   ← the interactive stdin command loop
├── fmt.rs       ← ANSI colors, markup resolution, message printing
├── embed.rs     ← embed & component panel rendering
├── image.rs     ← image → Unicode half-block rendering
└── log.rs       ← message logging (text / JSON)
```

## License

[nihagosepeungeodachuehasem-license](https://github.com/200mill/nihagosepeungeodachuehasem-license)
