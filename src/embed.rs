//! Render Discord embeds and message components to terminal panels.

use crate::fmt::*;
use serenity::model::application::{ActionRow, ActionRowComponent};
use serenity::model::channel::{Embed, Message, ReactionType};

pub fn render_embeds_and_components(msg: &Message) -> Option<String> {
    let mut sections: Vec<String> = Vec::new();
    for embed in &msg.embeds {
        sections.push(render_embed(embed));
    }
    if !msg.components.is_empty() {
        sections.push(render_components(&msg.components));
    }
    if sections.is_empty() {
        return None;
    }
    let content = sections.join("\n");
    let subtitle = format!("Author: {}", msg.author.name);
    Some(render_panel(
        "Embeds / Components",
        Some(&subtitle),
        EMBED_BORDER,
        &content,
    ))
}

fn render_embed(embed: &Embed) -> String {
    let border = embed.colour.map(|c| c.0).unwrap_or(EMBED_BORDER);
    let mut lines: Vec<String> = Vec::new();

    if let Some(author) = &embed.author {
        lines.push(bold_cyan(&format!("👤 {}", author.name)));
    }
    if let Some(title) = &embed.title {
        lines.push(bold_white(&format!("📌 {title}")));
    }
    if let Some(desc) = &embed.description {
        lines.push(desc.clone());
    }
    if let Some(img) = &embed.image {
        lines.push(dim_cyan(&format!("🖼️ [Image: {}]", img.url)));
    }
    if let Some(thumb) = &embed.thumbnail {
        lines.push(dim_cyan(&format!("🖼️ [Thumbnail: {}]", thumb.url)));
    }
    if let Some(video) = &embed.video {
        lines.push(dim_cyan(&format!("🎬 [Video: {}]", video.url)));
    }

    if !embed.fields.is_empty() {
        // Group inline fields into rows of up to three, like the original
        // table renderer.
        let mut rows: Vec<Vec<String>> = Vec::new();
        let mut current: Vec<String> = Vec::new();
        for field in &embed.fields {
            let cell = format!(
                "{}\n{}",
                bold_white(&format!("🔹 {}", field.name)),
                field.value
            );
            if field.inline {
                current.push(cell);
                if current.len() == 3 {
                    rows.push(std::mem::take(&mut current));
                }
            } else {
                if !current.is_empty() {
                    rows.push(std::mem::take(&mut current));
                }
                rows.push(vec![cell]);
            }
        }
        if !current.is_empty() {
            rows.push(current);
        }
        for row in rows {
            let max = row.iter().map(|c| display_width(c)).max().unwrap_or(0);
            let joined: String = row
                .iter()
                .map(|c| {
                    let pad = max.saturating_sub(display_width(c)) + 2;
                    format!("{c}{}", " ".repeat(pad))
                })
                .collect();
            lines.push(joined.trim_end().to_string());
        }
    }

    let mut footer: Vec<String> = Vec::new();
    if let Some(f) = &embed.footer {
        if !f.text.is_empty() {
            footer.push(f.text.clone());
        }
    }
    if let Some(ts) = &embed.timestamp {
        footer.push(ts.format("%Y-%m-%d %H:%M:%S").to_string());
    }
    if !footer.is_empty() {
        lines.push(italic_dim(&format!("\n{}", footer.join(" | "))));
    }

    if lines.is_empty() {
        lines.push(italic_dim("Unknown or Media-only Embed"));
    }

    render_panel("", None, border, &lines.join("\n"))
}

fn render_components(rows: &[ActionRow]) -> String {
    let mut out = String::new();
    for row in rows {
        for comp in &row.components {
            match comp {
                ActionRowComponent::Button(button) => {
                    let label = button
                        .label
                        .clone()
                        .or_else(|| {
                            button.emoji.as_ref().map(|e| match e {
                                ReactionType::Custom { name, .. } => {
                                    name.clone().unwrap_or_else(|| "Button".to_string())
                                }
                                ReactionType::Unicode(s) => s.clone(),
                                _ => "Button".to_string(),
                            })
                        })
                        .unwrap_or_else(|| "Button".to_string());
                    out.push_str(&bold_cyan(&format!("[ {label} ] ")));
                }
                ActionRowComponent::SelectMenu(menu) => {
                    let placeholder = menu
                        .placeholder
                        .clone()
                        .unwrap_or_else(|| "Select an option...".to_string());
                    out.push_str(&bold_magenta(&format!("▼ {placeholder} (Selection Menu) ")));
                }
                ActionRowComponent::InputText(input) => {
                    let content = input.value.clone().unwrap_or_default();
                    if !content.is_empty() {
                        out.push_str(&dim_white(&format!("\n💬 {content}")));
                    }
                }
                _ => {}
            }
        }
    }
    out
}
