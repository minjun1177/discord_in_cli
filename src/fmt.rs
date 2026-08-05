//! ANSI terminal helpers, markup resolution, and message printing.
//!
//! Replicates the terminal output of the original Python implementation
//! (`rich` markup) with raw ANSI truecolor escapes:
//! - bot usernames are purple `#B4009E`
//! - alert (mention) messages are orange `#EA9800` on dark `#2B251C`

use crate::state::State;
use regex::Regex;
use serenity::cache::Cache;
use serenity::model::channel::{Attachment, Message};
use serenity::model::guild::Member;
use serenity::model::id::{ChannelId, GuildId, UserId};
use std::collections::HashMap;

pub const RESET: &str = "\x1b[0m";
pub const BOT_PURPLE: u32 = 0xB4_00_9E;
pub const ALERT_FG: u32 = 0xEA_98_00;
pub const ALERT_BG: u32 = 0x2B_25_1C;
pub const EMBED_BORDER: u32 = 0x72_89_DA; // Discord blurple

pub fn hex_rgb(hex: u32) -> (u8, u8, u8) {
    ((hex >> 16) as u8, (hex >> 8) as u8, hex as u8)
}

pub fn ansi_fg(hex: u32) -> String {
    let (r, g, b) = hex_rgb(hex);
    format!("\x1b[38;2;{r};{g};{b}m")
}

pub fn ansi_bg(hex: u32) -> String {
    let (r, g, b) = hex_rgb(hex);
    format!("\x1b[48;2;{r};{g};{b}m")
}

pub fn color(hex: u32, s: &str) -> String {
    format!("{}{}{}", ansi_fg(hex), s, RESET)
}

pub fn color_on(fg: u32, bg: u32, s: &str) -> String {
    format!("{}{}{}{}", ansi_fg(fg), ansi_bg(bg), s, RESET)
}

pub fn bold_dim(s: &str) -> String {
    format!("\x1b[1;2m{s}{RESET}")
}

pub fn bold_cyan(s: &str) -> String {
    format!("\x1b[1;36m{s}{RESET}")
}

pub fn bold_magenta(s: &str) -> String {
    format!("\x1b[1;35m{s}{RESET}")
}

pub fn bold_white(s: &str) -> String {
    format!("\x1b[1;37m{s}{RESET}")
}

pub fn dim_cyan(s: &str) -> String {
    format!("\x1b[2;36m{s}{RESET}")
}

pub fn dim_white(s: &str) -> String {
    format!("\x1b[2;37m{s}{RESET}")
}

pub fn italic_dim(s: &str) -> String {
    format!("\x1b[3;2m{s}{RESET}")
}

pub fn dim_red(s: &str) -> String {
    format!("\x1b[2;31m{s}{RESET}")
}

/// Strip ANSI escape sequences (for width calculation).
pub fn strip_ansi(s: &str) -> String {
    static RE: std::sync::OnceLock<Regex> = std::sync::OnceLock::new();
    let re = RE.get_or_init(|| Regex::new(r"\x1b\[[0-9;]*m").unwrap());
    re.replace_all(s, "").into_owned()
}

pub fn display_width(s: &str) -> usize {
    strip_ansi(s).chars().count()
}

/// Draw a simple `rich`-style panel with a colored border.
pub fn render_panel(title: &str, subtitle: Option<&str>, border_hex: u32, content: &str) -> String {
    let b = ansi_fg(border_hex);
    let lines: Vec<&str> = content.split('\n').collect();
    let content_w = lines.iter().map(|l| display_width(l)).max().unwrap_or(0);
    let title_w = title.chars().count();
    let sub_w = subtitle.map(|s| s.chars().count()).unwrap_or(0);
    let inner = content_w.max(title_w).max(sub_w) + 4;

    let mut out = String::new();
    // Top border with title.
    let dashes = inner.saturating_sub(title_w + 4);
    out.push_str(&format!(
        "{b}╭─ {title} {}{b}─╮{RESET}\n",
        "─".repeat(dashes)
    ));
    // Content lines.
    for line in &lines {
        let pad = inner.saturating_sub(display_width(line) + 2);
        out.push_str(&format!(
            "{b}│{RESET} {line}{}{b} │{RESET}\n",
            " ".repeat(pad)
        ));
    }
    // Bottom border, optionally with a right-aligned subtitle.
    match subtitle {
        Some(sub) => {
            let pad = inner.saturating_sub(sub_w + 1);
            out.push_str(&format!("{b}╰─{}{}─{b}╯{RESET}\n", "─".repeat(pad), sub));
        }
        None => out.push_str(&format!("{b}╰{}{b}╯{RESET}\n", "─".repeat(inner))),
    }
    out
}

/// Channel display name from the cache, falling back to the raw id.
pub fn channel_name(cache: &Cache, cid: ChannelId) -> String {
    for gid in cache.guilds() {
        if let Some(guild) = cache.guild(gid) {
            if let Some(ch) = guild.channels.get(&cid) {
                return ch.name.clone();
            }
        }
    }
    cid.to_string()
}

/// Guild id that contains a channel, from the cache.
pub fn channel_guild_id(cache: &Cache, cid: ChannelId) -> Option<GuildId> {
    for gid in cache.guilds() {
        if let Some(guild) = cache.guild(gid) {
            if guild.channels.contains_key(&cid) {
                return Some(gid);
            }
        }
    }
    None
}

/// Resolve a user mention to its display name in the guild, or username.
fn resolve_user(cache: &Cache, guild_id: Option<GuildId>, id: UserId) -> Option<String> {
    if let Some(gid) = guild_id {
        if let Some(guild) = cache.guild(gid) {
            if let Some(member) = guild.members.get(&id) {
                return Some(member.display_name().to_string());
            }
        }
    }
    cache.user(id).map(|u| u.name.clone())
}

fn resolve_role(
    cache: &Cache,
    guild_id: Option<GuildId>,
    id: serenity::model::id::RoleId,
) -> Option<String> {
    let gid = guild_id?;
    let guild = cache.guild(gid)?;
    guild.roles.get(&id).map(|r| r.name.clone())
}

fn resolve_channel(cache: &Cache, id: ChannelId) -> Option<String> {
    for gid in cache.guilds() {
        if let Some(guild) = cache.guild(gid) {
            if let Some(ch) = guild.channels.get(&id) {
                return Some(ch.name.clone());
            }
        }
    }
    None
}

/// `clean_content` equivalent: resolve `<@user>`, `<@&role>`, `<#channel>`
/// mentions and render custom emoji `<a?:name:id>` as `:name:`.
pub fn resolve_markup(content: &str, cache: &Cache, guild_id: Option<GuildId>) -> String {
    static EMOJI_RE: std::sync::OnceLock<Regex> = std::sync::OnceLock::new();
    let emoji = EMOJI_RE.get_or_init(|| Regex::new(r"<(a?):([A-Za-z0-9_]+):\d+>").unwrap());
    let resolved = emoji.replace_all(content, ":$2:").into_owned();

    static MENTION_RE: std::sync::OnceLock<Regex> = std::sync::OnceLock::new();
    let mention = MENTION_RE.get_or_init(|| Regex::new(r"<(@!?|@&|#)(\d+)>").unwrap());
    let mut out = resolved.clone();
    let matches: Vec<(String, u64, String)> = mention
        .captures_iter(&resolved)
        .map(|c| {
            (
                c[1].to_string(),
                c[2].parse().unwrap_or(0),
                c[0].to_string(),
            )
        })
        .collect();
    for (kind, id, full) in matches {
        let replacement = if kind == "#" {
            resolve_channel(cache, ChannelId::new(id)).map(|n| format!("#{n}"))
        } else if kind.starts_with("@&") {
            resolve_role(cache, guild_id, serenity::model::id::RoleId::new(id))
                .map(|n| format!("@{n}"))
        } else {
            resolve_user(cache, guild_id, UserId::new(id)).map(|n| format!("@{n}"))
        };
        if let Some(repl) = replacement {
            out = out.replace(&full, &repl);
        }
    }
    out
}

/// Collect guild members: from the cache first, falling back to the REST API.
pub async fn collect_members(
    cache: &Cache,
    http: &serenity::http::Http,
    gid: GuildId,
) -> HashMap<UserId, Member> {
    if let Some(guild) = cache.guild(gid) {
        let map: HashMap<_, _> = guild.members.iter().map(|(k, v)| (*k, v.clone())).collect();
        if !map.is_empty() {
            return map;
        }
    }
    if let Ok(guild) = serenity::model::guild::Guild::get(http, gid).await {
        if let Ok(members) = guild.members(http, None, None).await {
            return members.into_iter().map(|m| (m.user.id, m)).collect();
        }
    }
    HashMap::new()
}

/// Convert `@name` tokens in outgoing text to real Discord mentions, matching
/// on display name, username, or global name (case-insensitive).
pub async fn convert_names_to_mentions(
    text: &str,
    guild_id: Option<GuildId>,
    cache: &Cache,
    http: &serenity::http::Http,
) -> String {
    static NAME_RE: std::sync::OnceLock<Regex> = std::sync::OnceLock::new();
    let name_re = NAME_RE.get_or_init(|| Regex::new(r"@([^\s]+)").unwrap());
    let Some(gid) = guild_id else {
        return text.to_string();
    };
    let members = collect_members(cache, http, gid).await;
    let mut out = text.to_string();
    let names: Vec<String> = name_re
        .captures_iter(text)
        .map(|c| c[1].to_string())
        .collect();
    for name in names {
        let lower = name.to_lowercase();
        let found = members.values().find(|m| {
            m.display_name().to_lowercase() == lower
                || m.user.name.to_lowercase() == lower
                || m.user
                    .global_name
                    .as_deref()
                    .map(|g| g.to_lowercase() == lower)
                    .unwrap_or(false)
        });
        if let Some(member) = found {
            out = out.replace(&format!("@{name}"), &format!("<@{}>", member.user.id));
        }
    }
    out
}

pub fn is_image_attachment(att: &Attachment) -> bool {
    if let Some(ct) = &att.content_type {
        if ct.starts_with("image/") {
            return true;
        }
    }
    const EXTS: [&str; 7] = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"];
    let lower = att.filename.to_lowercase();
    EXTS.iter().any(|e| lower.ends_with(e))
}

/// Print an incoming (or edited) Discord message to the terminal.
#[allow(clippy::too_many_arguments)]
pub async fn print_discord_msg(
    cache: &Cache,
    state: &State,
    client: &reqwest::Client,
    msg: &Message,
    is_edit: bool,
    before: Option<&Message>,
) {
    let embed_count = msg.embeds.len();
    let img_count = msg
        .attachments
        .iter()
        .filter(|a| is_image_attachment(a))
        .count();

    let has_content = if is_edit {
        before
            .map(|b| !b.content.trim().is_empty())
            .unwrap_or_else(|| !msg.content.trim().is_empty())
    } else {
        !msg.content.trim().is_empty()
    };

    let mut hidden_texts: Vec<String> = Vec::new();
    if !crate::state::flag(&state.embed_view) && embed_count > 0 {
        for i in 0..embed_count {
            hidden_texts.push(format!("Embed {} was hide", i + 1));
        }
    }
    if !crate::state::flag(&state.img_view) && img_count > 0 {
        for i in 0..img_count {
            hidden_texts.push(format!("Image {} was hide", i + 1));
        }
    }
    let hide_main_text = !has_content && !hidden_texts.is_empty();

    let author_colored = if msg.author.bot {
        color(BOT_PURPLE, &msg.author.name)
    } else {
        msg.author.name.clone()
    };
    let bot_suffix = if msg.author.bot { "(bot)" } else { "" };
    let time_str = msg.timestamp.format("%Y-%m-%d %H:%M:%S").to_string();
    let ch_name = if is_edit {
        before
            .map(|b| channel_name(cache, b.channel_id))
            .unwrap_or_else(|| channel_name(cache, msg.channel_id))
    } else {
        channel_name(cache, msg.channel_id)
    };

    let prefix = if state.is_watched(msg) {
        color_on(
            ALERT_FG,
            ALERT_BG,
            &format!("[{ch_name}] {}{bot_suffix}", msg.author.name),
        )
    } else {
        format!("[{ch_name}] {author_colored}{bot_suffix}")
    };

    let (action, text) = if is_edit {
        let action = " Modified";
        let text = if hide_main_text {
            format!("[{}]", hidden_texts.join(", "))
        } else {
            let before_content = before.map(|b| b.content.clone()).unwrap_or_default();
            format!("{before_content} -> {}", msg.content)
        };
        (action.to_string(), text)
    } else {
        let action = String::new();
        let text = if hide_main_text {
            format!("[{}]", hidden_texts.join(", "))
        } else {
            resolve_markup(&msg.content, cache, msg.guild_id)
        };
        (action, text)
    };

    if action.is_empty() {
        println!("{prefix} ({time_str}): {text}");
    } else {
        println!("{prefix}{action} ({time_str}) {text}");
    }

    if !msg.embeds.is_empty() || !msg.components.is_empty() {
        if crate::state::flag(&state.embed_view) {
            if let Some(panel) = crate::embed::render_embeds_and_components(msg) {
                println!("\n{panel}");
            }
        } else if embed_count > 0 && has_content {
            println!("  {}", bold_dim("[Embed]"));
        }
    }

    if img_count > 0 {
        if crate::state::flag(&state.img_view) {
            crate::image::render_images_async(client, msg).await;
        } else if has_content {
            println!("  {}", bold_dim(&format!("[Image {img_count} was hide]")));
        }
    }
}

/// Print a deletion notice for a message.
pub fn print_deleted(cache: &Cache, state: &State, msg: &Message) {
    let ch_name = channel_name(cache, msg.channel_id);
    let time_str = msg.timestamp.format("%Y-%m-%d %H:%M:%S").to_string();
    let bot_suffix = if msg.author.bot { "(bot)" } else { "" };
    let content = resolve_markup(&msg.content, cache, msg.guild_id);
    if state.is_watched(msg) {
        println!(
            "{}",
            color_on(
                ALERT_FG,
                ALERT_BG,
                &format!(
                    "[{ch_name}] {}{bot_suffix} Deleted ({time_str}): {content}",
                    msg.author.name
                )
            )
        );
    } else {
        let author_colored = if msg.author.bot {
            color(BOT_PURPLE, &msg.author.name)
        } else {
            msg.author.name.clone()
        };
        println!("[{ch_name}] {author_colored}{bot_suffix} Deleted ({time_str}): {content}");
    }
}

/// Truncated preview used by `/messages`.
pub fn message_preview(
    content: &str,
    cache: &Cache,
    guild_id: Option<GuildId>,
    max: usize,
) -> String {
    let resolved = resolve_markup(content, cache, guild_id);
    let mut out: String = resolved.chars().take(max).collect();
    if resolved.chars().count() > max {
        out.push_str("...");
    }
    out
}
