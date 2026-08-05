//! Message logging to a file, in plain text or JSON-lines format,
//! matching the original `src/log.py` behavior.

use crate::fmt::{channel_name, resolve_markup};
use crate::state::State;
use serenity::cache::Cache;
use serenity::model::channel::Message;
use std::fs::OpenOptions;
use std::io::Write;

pub fn log_message(
    state: &State,
    cache: &Cache,
    msg: &Message,
    after: Option<&Message>,
    is_edit: bool,
    is_delete: bool,
) {
    if !state.settings.save_messages {
        return;
    }

    let guild_name = match msg.guild_id {
        Some(gid) => cache.guild(gid).map(|g| g.name.clone()).unwrap_or_default(),
        None => "Direct Message".to_string(),
    };
    let channel_name = channel_name(cache, msg.channel_id);
    let channel_id = msg.channel_id.get();
    let author_id = msg.author.id.get();
    let author_name = &msg.author.name;
    let is_bot = msg.author.bot;
    let time_str = msg.timestamp.format("%Y-%m-%d %H:%M:%S").to_string();
    let timestamp = msg.timestamp.to_rfc3339().unwrap_or_default();
    let attachment_urls: Vec<String> = msg.attachments.iter().map(|a| a.url.clone()).collect();

    if is_delete {
        if state.settings.save_as_json {
            let data = serde_json::json!({
                "type": "delete",
                "message_id": msg.id.get(),
                "timestamp": timestamp,
                "server": { "id": msg.guild_id.map(|g| g.get()), "name": guild_name },
                "channel": { "id": channel_id, "name": channel_name },
                "author": { "id": author_id, "name": author_name, "is_bot": is_bot },
                "content_before": resolve_markup(&msg.content, cache, msg.guild_id),
                "attachments": attachment_urls,
            });
            append_json_line(state, &data);
        } else {
            let attachment_info = if msg.attachments.is_empty() {
                String::new()
            } else {
                format!(" (첨부파일: {}개)", msg.attachments.len())
            };
            let line = format!(
                "[{time_str}] [{guild_name} / {channel_name}] {author_name}({author_id}) Deleted: {}{attachment_info}\n",
                resolve_markup(&msg.content, cache, msg.guild_id)
            );
            append_text(state, &line);
        }
        return;
    }

    if is_edit {
        let after = after.expect("is_edit requires `after` message");
        if state.settings.save_as_json {
            let data = serde_json::json!({
                "type": "edit",
                "message_id": msg.id.get(),
                "timestamp": after.timestamp.to_rfc3339().unwrap_or_default(),
                "server": { "id": msg.guild_id.map(|g| g.get()), "name": guild_name },
                "channel": { "id": channel_id, "name": channel_name },
                "author": { "id": author_id, "name": author_name, "is_bot": is_bot },
                "content_before": resolve_markup(&msg.content, cache, msg.guild_id),
                "content_after": resolve_markup(&after.content, cache, after.guild_id),
                "attachments_before": msg.attachments.iter().map(|a| a.url.clone()).collect::<Vec<_>>(),
                "attachments_after": after.attachments.iter().map(|a| a.url.clone()).collect::<Vec<_>>(),
            });
            append_json_line(state, &data);
        } else {
            let att_before = if msg.attachments.is_empty() {
                String::new()
            } else {
                format!(" (첨부파일: {}개)", msg.attachments.len())
            };
            let att_after = if after.attachments.is_empty() {
                String::new()
            } else {
                format!(" (첨부파일: {}개)", after.attachments.len())
            };
            let time = after.timestamp.format("%Y-%m-%d %H:%M:%S").to_string();
            let line = format!(
                "[{time}] [{guild_name} / {channel_name}] {author_name}({author_id}) 수정됨: {}{att_before} -> {}{att_after}\n",
                resolve_markup(&msg.content, cache, msg.guild_id),
                resolve_markup(&after.content, cache, after.guild_id)
            );
            append_text(state, &line);
        }
        return;
    }

    // Plain new message.
    if state.settings.save_as_json {
        let data = serde_json::json!({
            "type": "message",
            "message_id": msg.id.get(),
            "timestamp": timestamp,
            "server": { "id": msg.guild_id.map(|g| g.get()), "name": guild_name },
            "channel": { "id": channel_id, "name": channel_name },
            "author": { "id": author_id, "name": author_name, "is_bot": is_bot },
            "content": resolve_markup(&msg.content, cache, msg.guild_id),
            "attachments": attachment_urls,
        });
        append_json_line(state, &data);
    } else {
        let attachment_info = if msg.attachments.is_empty() {
            String::new()
        } else {
            format!(" (첨부파일: {}개)", msg.attachments.len())
        };
        let line = format!(
            "[{time_str}] [{guild_name} / {channel_name}] {author_name}({author_id}): {}{attachment_info}\n",
            resolve_markup(&msg.content, cache, msg.guild_id)
        );
        append_text(state, &line);
    }
}

fn append_json_line(state: &State, value: &serde_json::Value) {
    if let Ok(mut f) = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&state.settings.save_filename)
    {
        if let Ok(line) = serde_json::to_string(value) {
            let _ = writeln!(f, "{line}");
        }
    }
}

fn append_text(state: &State, line: &str) {
    if let Ok(mut f) = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&state.settings.save_filename)
    {
        let _ = f.write_all(line.as_bytes());
    }
}
