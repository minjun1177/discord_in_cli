//! The interactive console: reads stdin lines and dispatches commands,
//! mirroring the original `app.py` `watch_console` loop.

use crate::fmt::{
    channel_guild_id, channel_name, color, convert_names_to_mentions, message_preview,
    print_discord_msg, resolve_markup, BOT_PURPLE,
};
use crate::state::{active_channel_id, State};
use serenity::builder::{
    CreateAllowedMentions, CreateAttachment, CreateMessage, EditMessage, GetMessages,
};
use serenity::cache::Cache;
use serenity::gateway::{ActivityData, ShardMessenger};
use serenity::http::{Http, HttpError, StatusCode};
use serenity::model::channel::{Channel, ChannelType, GuildChannel, Message};
use serenity::model::guild::{Guild, PartialGuild};
use serenity::model::id::{ChannelId, GuildId, MessageId, UserId};
use serenity::model::user::OnlineStatus;
use std::sync::atomic::Ordering;
use std::sync::Arc;
use tokio::sync::mpsc::UnboundedReceiver;
use tokio::sync::mpsc::UnboundedSender;

/// Spawn a thread that forwards stdin lines into the channel.
pub fn spawn_stdin_reader(tx: UnboundedSender<String>) {
    std::thread::spawn(move || {
        let stdin = std::io::stdin();
        let mut line = String::new();
        loop {
            line.clear();
            match stdin.read_line(&mut line) {
                Ok(0) => break, // EOF
                Ok(_) => {
                    let trimmed = line.trim_end().to_string();
                    if tx.send(trimmed).is_err() {
                        break;
                    }
                }
                Err(_) => break,
            }
        }
    });
}

/// Main console loop; returns when `/stop` is issued.
pub async fn run_console(
    http: Arc<Http>,
    cache: Arc<Cache>,
    shard: ShardMessenger,
    state: Arc<State>,
    client: reqwest::Client,
    mut rx: UnboundedReceiver<String>,
) {
    while let Some(line) = rx.recv().await {
        let line = line.trim().to_string();
        if line.is_empty() {
            continue;
        }
        if handle_command(&http, &cache, &shard, &state, &client, &line).await {
            break;
        }
    }
}

#[allow(clippy::too_many_arguments)]
async fn handle_command(
    http: &Http,
    cache: &Cache,
    shard: &ShardMessenger,
    state: &State,
    client: &reqwest::Client,
    line: &str,
) -> bool {
    if line == "/status" {
        cmd_status(http, cache, state).await;
    } else if line == "/stop" {
        println!("[SYSTEM] Stopping bot...");
        shard.shutdown_clean();
        return true;
    } else if line.contains("@everyone") && !state.settings.allow_mention_everyone {
        println!("[ERROR] '@everyone' is not allowed.");
    } else if line.starts_with("/select") {
        cmd_select(http, cache, state, client, line).await;
    } else if line.starts_with("/embed") {
        cmd_toggle(http, cache, state, client, "embed", line).await;
    } else if line.starts_with("/img") {
        cmd_toggle(http, cache, state, client, "img", line).await;
    } else if line == "/exit" {
        cmd_exit(http, cache, state, client).await;
    } else if line.starts_with("/setrpc") {
        cmd_setrpc(shard, line);
    } else if line == "/refresh" {
        cmd_refresh(http, cache, state, client).await;
    } else if line.starts_with("/messages") {
        cmd_messages(http, cache, state, line).await;
    } else if line.starts_with("/edit") {
        cmd_edit(http, cache, state, line).await;
    } else if line.starts_with("/reply") {
        cmd_reply(http, cache, state, line).await;
    } else if line.starts_with("/uploadfile") {
        cmd_uploadfile(http, cache, state, line).await;
    } else if line.starts_with("/downloadfile") {
        cmd_downloadfile(http, cache, state, client, line).await;
    } else if line.starts_with('/') {
        println!("[ERROR] Unknown command: {line}");
    } else {
        cmd_send(http, cache, state, line).await;
    }
    false
}

async fn cmd_status(http: &Http, cache: &Cache, state: &State) {
    let cid = active_channel_id(state);
    match ChannelId::new(cid.get()).to_channel(http).await {
        Ok(Channel::Guild(gc)) => {
            let guild_name = cache
                .guild(gc.guild_id)
                .map(|g| g.name.clone())
                .unwrap_or_default();
            println!(
                "[SYSTEM] Bot connected to '{}' (ID: {}) in server '{}' (ID: {}).",
                gc.name, gc.id, guild_name, gc.guild_id
            );
        }
        Ok(Channel::Private(pc)) => {
            println!("[SYSTEM] Bot connected to 'DM' (ID: {}).", pc.id);
        }
        Ok(_) => println!("[ERROR] Channel with ID {cid} not found."),
        Err(_) => println!("[ERROR] Channel with ID {cid} not found."),
    }
}

async fn cmd_select(
    http: &Http,
    cache: &Cache,
    state: &State,
    client: &reqwest::Client,
    line: &str,
) {
    let parts: Vec<&str> = line.split_whitespace().collect();
    if parts.len() != 2 || !parts[1].chars().all(|c| c.is_ascii_digit()) {
        println!("[ERROR] Invalid command. Use '/select <channel_id>'.");
        return;
    }
    let temp_id: u64 = parts[1].parse().unwrap();
    let cid = ChannelId::new(temp_id);
    match cid.to_channel(http).await {
        Ok(_) => {
            *state.selected_channel.lock().unwrap() = Some(cid);
            state.clear_channel_messages();
            let name = channel_name(cache, cid);
            println!("[SYSTEM] Selected channel ID: {temp_id} ('{name}')");
            println!(
                "[SYSTEM] Fetching last {} messages from '{name}'...",
                state.settings.fetch_history_limit
            );
            refresh_channel(http, cache, state, client, cid).await;
        }
        Err(_) => println!("[ERROR] Channel with ID {temp_id} not found."),
    }
}

async fn cmd_toggle(
    http: &Http,
    cache: &Cache,
    state: &State,
    client: &reqwest::Client,
    which: &str,
    line: &str,
) {
    let parts: Vec<&str> = line.split_whitespace().collect();
    if parts.len() != 2 || (parts[1] != "open" && parts[1] != "close") {
        println!("[ERROR] Usage: /{which} open or /{which} close");
        return;
    }
    let enabled = parts[1] == "open";
    match which {
        "embed" => state.embed_view.store(enabled, Ordering::Relaxed),
        "img" => state.img_view.store(enabled, Ordering::Relaxed),
        _ => unreachable!(),
    }
    let label = if which == "embed" { "Embed" } else { "Image" };
    let status = if enabled { "enabled" } else { "disabled" };
    println!("[SYSTEM] {label} rendering is now {status}.");
    let selected = *state.selected_channel.lock().unwrap();
    if let Some(cid) = selected {
        let name = channel_name(cache, cid);
        println!("[SYSTEM] Refreshing messages from '{name}'...");
        refresh_channel(http, cache, state, client, cid).await;
    }
}

async fn cmd_exit(http: &Http, cache: &Cache, state: &State, _client: &reqwest::Client) {
    println!("[SYSTEM] Exiting channel selection mode.");
    *state.selected_channel.lock().unwrap() = None;
    state.clear_channel_messages();
    match state.settings.server_id {
        Some(gid) => {
            if let Err(e) = get_all_channels(http, cache, GuildId::new(gid), state).await {
                println!("[ERROR] Failed to list channels: {e}");
            }
        }
        None => println!(
            "[ERROR] SERVER_ID is not set in settings.json. Please provide a valid server ID."
        ),
    }
}

fn cmd_setrpc(shard: &ShardMessenger, line: &str) {
    let raw = line.trim_start_matches("/setrpc").trim();
    if raw.is_empty() {
        println!("[ERROR] Usage: /setrpc <activity text> [online|idle|dnd|offline]");
        return;
    }
    const VALID: [&str; 4] = ["online", "idle", "dnd", "offline"];
    let (activity_text, status_str): (&str, String) = match raw.rsplit_once(' ') {
        Some((text, status)) => {
            let lower = status.to_lowercase();
            if VALID.contains(&lower.as_str()) {
                (text.trim(), lower)
            } else {
                (raw, "online".to_string())
            }
        }
        None => (raw, "online".to_string()),
    };
    let status = match status_str.as_str() {
        "idle" => OnlineStatus::Idle,
        "dnd" => OnlineStatus::DoNotDisturb,
        "offline" => OnlineStatus::Invisible,
        _ => OnlineStatus::Online,
    };
    shard.set_presence(Some(ActivityData::playing(activity_text)), status);
    println!("[SYSTEM] Rich Presence set to '{activity_text}' with status '{status_str}'.");
}

async fn cmd_refresh(http: &Http, cache: &Cache, state: &State, client: &reqwest::Client) {
    let selected = *state.selected_channel.lock().unwrap();
    match selected {
        Some(cid) => {
            let name = channel_name(cache, cid);
            println!("[SYSTEM] Refreshing messages from '{name}'...");
            refresh_channel(http, cache, state, client, cid).await;
        }
        None => println!("[ERROR] No channel selected to refresh."),
    }
}

async fn cmd_messages(http: &Http, cache: &Cache, state: &State, line: &str) {
    let mut parts = line.splitn(2, ' ');
    parts.next();
    let all = parts.next().map(|s| s.trim() == "all").unwrap_or(false);
    let bot_id = state.bot_user_id();
    let items: Vec<(usize, Arc<Message>)> = {
        let buf = state.channel_messages.lock().unwrap();
        buf.iter()
            .rev()
            .enumerate()
            .map(|(i, m)| (i + 1, m.clone()))
            .filter(|(_, m)| all || Some(m.author.id) == bot_id)
            .collect()
    };
    if items.is_empty() {
        println!("[SYSTEM] No sent messages in history.");
        return;
    }
    println!("[SYSTEM] Your sent messages (newest first):");
    for (i, msg) in items.iter().rev() {
        let author_colored = if msg.author.bot {
            color(BOT_PURPLE, &msg.author.name)
        } else {
            msg.author.name.clone()
        };
        let resolved = resolve_markup(&msg.content, cache, msg.guild_id);
        let resolved = convert_names_to_mentions(&resolved, msg.guild_id, cache, http).await;
        let preview = truncate(&resolved, 50);
        let time = msg.timestamp.format("%H:%M:%S").to_string();
        println!("  ~{i}  {author_colored} ({time}) {preview}");
    }
    println!("[SYSTEM] Use '/edit <new text>' or '/edit ~N <new text>' to edit.");
    println!("[SYSTEM] Use '/reply <text>' or '/reply ~N <text>' to reply to a message.");
}

fn truncate(s: &str, max: usize) -> String {
    let mut out: String = s.chars().take(max).collect();
    if s.chars().count() > max {
        out.push_str("...");
    }
    out
}

async fn cmd_edit(http: &Http, _cache: &Cache, state: &State, line: &str) {
    let mut parts = line.splitn(2, ' ');
    let cmd = parts.next().unwrap_or("");
    let rest = parts.next().unwrap_or("").trim().to_string();
    let cid = active_channel_id(state);

    if cmd == "/editmsg" {
        let mut p = rest.splitn(2, ' ');
        let id_part = p.next().unwrap_or("");
        let new_content = p.next().unwrap_or("").to_string();
        if id_part.is_empty()
            || !id_part.chars().all(|c| c.is_ascii_digit())
            || new_content.is_empty()
        {
            println!("[ERROR] Usage: /editmsg <message_id> <new_content>");
            return;
        }
        let message_id: u64 = id_part.parse().unwrap();
        match cid.message(http, MessageId::new(message_id)).await {
            Ok(target) => {
                match cid
                    .edit_message(
                        http,
                        target.id,
                        EditMessage::new().content(new_content.clone()),
                    )
                    .await
                {
                    Ok(_) => println!("[SYSTEM] Edited message ID {message_id} to: {new_content}"),
                    Err(serenity::Error::Http(HttpError::UnsuccessfulRequest(resp)))
                        if resp.status_code == StatusCode::NOT_FOUND =>
                    {
                        println!("[ERROR] Message with ID {message_id} not found in the selected channel.");
                    }
                    Err(serenity::Error::Http(HttpError::UnsuccessfulRequest(resp)))
                        if resp.status_code == StatusCode::FORBIDDEN =>
                    {
                        println!(
                            "[ERROR] Bot does not have permission to edit message ID {message_id}."
                        );
                    }
                    Err(e) => println!("[ERROR] Failed to edit message ID {message_id}: {e}"),
                }
            }
            Err(e) => println!("[ERROR] Failed to fetch message ID {message_id}: {e}"),
        }
        return;
    }

    // /edit <new text> | /edit ~N <new text>
    if rest.is_empty() {
        println!("[ERROR] Usage: /edit <new text>  or  /edit ~N <new text>");
        println!("        /edit hello world     → edit last message");
        println!("        /edit ~3 hello world  → edit 3rd most recent message");
        println!("        /messages             → list recent channel messages");
        return;
    }
    let mut index = 1usize;
    let mut new_content = rest.clone();
    if let Some(stripped) = rest.strip_prefix('~') {
        let mut idx_parts = stripped.splitn(2, ' ');
        let idx_str = idx_parts.next().unwrap_or("");
        let rest2 = idx_parts.next().unwrap_or("");
        if !idx_str.is_empty() && idx_str.chars().all(|c| c.is_ascii_digit()) && !rest2.is_empty() {
            index = idx_str.parse().unwrap();
            new_content = rest2.to_string();
        } else {
            println!("[ERROR] Usage: /edit ~N <new text>  (N = message number from /messages)");
            return;
        }
    }
    let len = state.channel_messages.lock().unwrap().len();
    if index < 1 || index > len {
        println!(
            "[ERROR] Index ~{index} is out of range. You have {len} message(s) in history. Use /messages to see them."
        );
        return;
    }
    let target = {
        let buf = state.channel_messages.lock().unwrap();
        (*buf[len - index]).clone()
    };
    if Some(target.author.id) != state.bot_user_id() {
        println!(
            "[ERROR] ~{index} is a message by '{}'. You can only edit the bot's own messages (marked ★ in /messages).",
            target.author.name
        );
        return;
    }
    let username = &state.settings.username;
    match cid
        .edit_message(
            http,
            target.id,
            EditMessage::new().content(format!("{username}: {new_content}")),
        )
        .await
    {
        Ok(_) => println!("[SYSTEM] Edited message ~{index} to: {new_content}"),
        Err(serenity::Error::Http(HttpError::UnsuccessfulRequest(resp)))
            if resp.status_code == StatusCode::NOT_FOUND =>
        {
            println!("[ERROR] Message ~{index} was deleted and can no longer be edited.");
            state.remove_from_channel_messages(target.id);
        }
        Err(serenity::Error::Http(HttpError::UnsuccessfulRequest(resp)))
            if resp.status_code == StatusCode::FORBIDDEN =>
        {
            println!("[ERROR] Bot does not have permission to edit that message.");
        }
        Err(e) => println!("[ERROR] Failed to edit message: {e}"),
    }
}

async fn cmd_reply(http: &Http, cache: &Cache, state: &State, line: &str) {
    let rest = line.trim_start_matches("/reply").trim().to_string();
    if rest.is_empty() {
        println!("[ERROR] Usage: /reply <text>  or  /reply ~N <text>");
        println!("        /reply hello          → reply to last message");
        println!("        /reply ~3 hello       → reply to 3rd most recent message");
        return;
    }
    let mut index = 1usize;
    let mut reply_content = rest.clone();
    if let Some(stripped) = rest.strip_prefix('~') {
        let mut idx_parts = stripped.splitn(2, ' ');
        let idx_str = idx_parts.next().unwrap_or("");
        let rest2 = idx_parts.next().unwrap_or("");
        if !idx_str.is_empty() && idx_str.chars().all(|c| c.is_ascii_digit()) && !rest2.is_empty() {
            index = idx_str.parse().unwrap();
            reply_content = rest2.to_string();
        } else {
            println!("[ERROR] Usage: /reply ~N <text>  (N = message number from /messages)");
            return;
        }
    }
    let len = state.channel_messages.lock().unwrap().len();
    if index < 1 || index > len {
        println!("[ERROR] Index ~{index} is out of range. You have {len} message(s) in history.");
        return;
    }
    let target = {
        let buf = state.channel_messages.lock().unwrap();
        (*buf[len - index]).clone()
    };

    let cid = active_channel_id(state);
    let processed = convert_names_to_mentions(&reply_content, target.guild_id, cache, http).await;
    let username = &state.settings.username;
    let send_result = cid
        .send_message(
            http,
            CreateMessage::new()
                .content(format!("{username}: {processed}"))
                .reference_message((cid, target.id))
                .allowed_mentions(CreateAllowedMentions::new().replied_user(false)),
        )
        .await;
    match send_result {
        Ok(sent) => {
            state.add_to_channel_messages(Arc::new(sent));
            let preview = message_preview(&target.content, cache, target.guild_id, 30);
            println!(
                "[SYSTEM] Replied to ~{index} ({}: {preview})",
                target.author.name
            );
        }
        Err(serenity::Error::Http(HttpError::UnsuccessfulRequest(resp)))
            if resp.status_code == StatusCode::NOT_FOUND =>
        {
            println!("[ERROR] Message ~{index} was deleted and can no longer be replied to.");
            state.remove_from_channel_messages(target.id);
        }
        Err(e) => println!("[ERROR] Failed to reply: {e}"),
    }
}

async fn cmd_uploadfile(http: &Http, cache: &Cache, state: &State, line: &str) {
    let mut parts = line.splitn(2, ' ');
    parts.next();
    let Some(file_path) = parts.next() else {
        println!("[ERROR] Usage: /uploadfile <file_path>");
        return;
    };
    let file_path = file_path.trim();
    if !std::path::Path::new(file_path).is_file() {
        println!("[ERROR] File '{file_path}' does not exist.");
        return;
    }
    match tokio::fs::read(file_path).await {
        Ok(bytes) => {
            let fname = std::path::Path::new(file_path)
                .file_name()
                .map(|s| s.to_string_lossy().into_owned())
                .unwrap_or_else(|| file_path.to_string());
            let username = &state.settings.username;
            let cid = active_channel_id(state);
            let attachment = CreateAttachment::bytes(bytes, fname);
            match cid
                .send_message(
                    http,
                    CreateMessage::new()
                        .content(format!("{username} uploaded a file:"))
                        .files([attachment]),
                )
                .await
            {
                Ok(sent) => {
                    state.add_to_channel_messages(Arc::new(sent));
                    let name = channel_name(cache, cid);
                    println!("[SYSTEM] Uploaded file '{file_path}' to channel '{name}'.");
                }
                Err(e) => println!("[ERROR] Failed to upload file: {e}"),
            }
        }
        Err(e) => println!("[ERROR] Failed to upload file: {e}"),
    }
}

async fn cmd_downloadfile(
    http: &Http,
    _cache: &Cache,
    state: &State,
    client: &reqwest::Client,
    line: &str,
) {
    let parts: Vec<&str> = line.splitn(4, ' ').collect();
    if parts.len() < 2 {
        println!("[ERROR] Usage: /downloadfile ~N [attachment_index] [save_path]");
        println!("        /downloadfile <message_id> [attachment_index] [save_path]");
        println!("        Examples:");
        println!("        /downloadfile ~1");
        println!("        /downloadfile ~2 1");
        println!("        /downloadfile ~3 2 downloads");
        println!("        /downloadfile 123456789012345678 1 C:/tmp/file.png");
        return;
    }
    let target = parts[1];
    let mut attachment_index = 1usize;
    let mut save_target: Option<String> = None;
    if parts.len() >= 3 {
        if parts[2].chars().all(|c| c.is_ascii_digit()) {
            attachment_index = parts[2].parse().unwrap();
            if parts.len() == 4 {
                save_target = Some(parts[3].to_string());
            }
        } else {
            save_target = Some(parts[2].to_string());
            if parts.len() == 4 {
                println!("[ERROR] Invalid arguments. If you provide both attachment_index and save_path, use: /downloadfile <target> <attachment_index> <save_path>");
                return;
            }
        }
    }
    if attachment_index < 1 {
        println!("[ERROR] attachment_index must be >= 1");
        return;
    }

    let cid = active_channel_id(state);
    let target_message: Option<Message> = if let Some(idx_str) = target.strip_prefix('~') {
        if !idx_str.is_empty() && idx_str.chars().all(|c| c.is_ascii_digit()) {
            let index: usize = idx_str.parse().unwrap();
            let len = state.channel_messages.lock().unwrap().len();
            if index < 1 || index > len {
                println!(
                    "[ERROR] Index ~{index} is out of range. You have {len} message(s) in history."
                );
                return;
            }
            let buf = state.channel_messages.lock().unwrap();
            Some((*buf[len - index]).clone())
        } else {
            None
        }
    } else if target.chars().all(|c| c.is_ascii_digit()) {
        match cid
            .message(http, MessageId::new(target.parse().unwrap()))
            .await
        {
            Ok(m) => Some(m),
            Err(serenity::Error::Http(HttpError::UnsuccessfulRequest(resp)))
                if resp.status_code == StatusCode::NOT_FOUND =>
            {
                println!("[ERROR] Message ID {target} was not found in the selected channel.");
                return;
            }
            Err(e) => {
                println!("[ERROR] Failed to fetch message ID {target}: {e}");
                return;
            }
        }
    } else {
        None
    };
    let Some(target_message) = target_message else {
        println!("[ERROR] Target must be ~N or <message_id>.");
        return;
    };

    if target_message.attachments.is_empty() {
        println!("[ERROR] The target message has no attachments.");
        return;
    }
    if attachment_index > target_message.attachments.len() {
        println!(
            "[ERROR] attachment_index {attachment_index} is out of range. This message has {} attachment(s).",
            target_message.attachments.len()
        );
        return;
    }
    let attachment = &target_message.attachments[attachment_index - 1];
    let file_name = if attachment.filename.is_empty() {
        format!("attachment_{}", attachment.id)
    } else {
        attachment.filename.clone()
    };

    // Compute the save path (mirroring the Python logic).
    let save_path: String = match &save_target {
        Some(st) => {
            let p = std::path::Path::new(st);
            if p.is_dir() || st.ends_with('/') || st.ends_with('\\') {
                let _ = std::fs::create_dir_all(p);
                p.join(&file_name).to_string_lossy().into_owned()
            } else {
                if let Some(parent) = p.parent() {
                    if !parent.as_os_str().is_empty() {
                        let _ = std::fs::create_dir_all(parent);
                    }
                }
                st.clone()
            }
        }
        None => {
            let _ = std::fs::create_dir_all("downloads");
            std::path::Path::new("downloads")
                .join(&file_name)
                .to_string_lossy()
                .into_owned()
        }
    };

    // Deduplicate an existing file with _1, _2, ... suffixes.
    let (base, ext) = match save_path.rfind('.') {
        Some(i) if i > 0 => (save_path[..i].to_string(), save_path[i..].to_string()),
        _ => (save_path.clone(), String::new()),
    };
    let mut final_path = save_path.clone();
    let mut suffix = 1u32;
    while std::path::Path::new(&final_path).exists() {
        final_path = format!("{base}_{suffix}{ext}");
        suffix += 1;
    }

    match client.get(&attachment.url).send().await {
        Ok(resp) => match resp.bytes().await {
            Ok(bytes) => match tokio::fs::write(&final_path, bytes).await {
                Ok(_) => println!(
                    "[SYSTEM] Downloaded attachment #{attachment_index} from message {} to '{final_path}'.",
                    target_message.id
                ),
                Err(e) => println!("[ERROR] Failed to download attachment: {e}"),
            },
            Err(e) => println!("[ERROR] Failed to download attachment: {e}"),
        },
        Err(e) => println!("[ERROR] Failed to download attachment: {e}"),
    }
}

async fn cmd_send(http: &Http, cache: &Cache, state: &State, line: &str) {
    let Some(cid) = *state.selected_channel.lock().unwrap() else {
        println!("[SYSTEM] No channel selected. Please use '/select <channel_id>' to select a channel for monitoring and sending messages.");
        return;
    };
    let guild_id = channel_guild_id(cache, cid);
    let processed = convert_names_to_mentions(line, guild_id, cache, http).await;
    let username = &state.settings.username;
    match cid
        .send_message(
            http,
            CreateMessage::new().content(format!("{username}: {processed}")),
        )
        .await
    {
        Ok(sent) => {
            state.add_to_channel_messages(Arc::new(sent));
            println!("{username}: {line}");
        }
        Err(e) => println!("[TRANSMISSION FAILED] Message can not be sent: {e}"),
    }
}

/// Fetch and print the last `FETCH_HISTORY_LIMIT` messages of a channel.
pub async fn refresh_channel(
    http: &Http,
    cache: &Cache,
    state: &State,
    client: &reqwest::Client,
    cid: ChannelId,
) {
    let limit = state.settings.fetch_history_limit.clamp(1, 255) as u8;
    match cid.messages(http, GetMessages::new().limit(limit)).await {
        Ok(mut msgs) => {
            state.clear_channel_messages();
            msgs.reverse(); // oldest first
            for msg in msgs {
                let msg = Arc::new(msg);
                state.add_to_channel_messages(msg.clone());
                print_discord_msg(cache, state, client, &msg, false, None).await;
            }
        }
        Err(e) => println!("[ERROR] Could not fetch messages: {e}"),
    }
}

/// List all readable channels of a guild, grouped by category.
pub async fn get_all_channels(
    http: &Http,
    cache: &Cache,
    guild_id: GuildId,
    state: &State,
) -> Result<(), String> {
    let guild: PartialGuild = Guild::get(http, guild_id)
        .await
        .map_err(|e| e.to_string())?;
    println!("=== Server: '{}' (ID: {}) ===", guild.name, guild.id);
    let channels: Vec<GuildChannel> = guild
        .channels(http)
        .await
        .map_err(|e| e.to_string())?
        .into_values()
        .collect();
    let bot_id = state.bot_user_id();

    let mut categories: Vec<&GuildChannel> = channels
        .iter()
        .filter(|c| c.kind == ChannelType::Category)
        .collect();
    categories.sort_by_key(|c| c.position);
    for cat in categories {
        println!("\n📂 {}:", cat.name);
        let mut children: Vec<&GuildChannel> = channels
            .iter()
            .filter(|c| c.parent_id == Some(cat.id) && c.kind != ChannelType::Category)
            .collect();
        children.sort_by_key(|c| c.position);
        for ch in children {
            if let Some(bot) = bot_id {
                if !can_read(cache, ch, bot) {
                    continue;
                }
            }
            print_channel_line(ch);
        }
    }

    let mut uncategorized: Vec<&GuildChannel> = channels
        .iter()
        .filter(|c| c.parent_id.is_none() && c.kind != ChannelType::Category)
        .collect();
    uncategorized.sort_by_key(|c| c.position);
    if !uncategorized.is_empty() {
        println!("\n📂 None Category:");
        for ch in uncategorized {
            if let Some(bot) = bot_id {
                if !can_read(cache, ch, bot) {
                    continue;
                }
            }
            print_channel_line(ch);
        }
    }

    println!(
        "\nUse '/select <channel_id>' to select a channel for monitoring and sending messages."
    );
    Ok(())
}

#[allow(deprecated)]
fn can_read(cache: &Cache, ch: &GuildChannel, bot: UserId) -> bool {
    match ch.permissions_for_user(cache, bot) {
        Ok(p) => p.view_channel(),
        Err(_) => true, // member not cached; assume readable
    }
}

fn print_channel_line(ch: &GuildChannel) {
    match ch.kind {
        ChannelType::Text | ChannelType::News => {
            println!("   💬  [Chat]  {} (ID: {})", ch.name, ch.id);
        }
        ChannelType::Voice => {
            println!("   🔊  [Voice] {} (ID: {})", ch.name, ch.id);
        }
        _ => {}
    }
}
