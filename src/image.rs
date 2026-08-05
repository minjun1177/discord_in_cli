//! Render image attachments as Unicode half-block art in the terminal
//! (an ANSI-truecolor re-implementation of `climage`'s unicode mode).

use crate::fmt::{is_image_attachment, render_panel, RESET};
use serenity::model::channel::Message;

const IMG_WIDTH: u32 = 50;
const IMG_BORDER: u32 = 0x00_B3_B3; // dim cyan

pub async fn render_images_async(client: &reqwest::Client, msg: &Message) {
    for attachment in msg.attachments.iter().filter(|a| is_image_attachment(a)) {
        match client.get(&attachment.url).send().await {
            Ok(resp) => match resp.bytes().await {
                Ok(bytes) => match render_image_bytes(&bytes) {
                    Ok(art) => {
                        let panel = render_panel(
                            &format!("🖼️ {}", attachment.filename),
                            None,
                            IMG_BORDER,
                            &art,
                        );
                        println!("\n{panel}");
                    }
                    Err(e) => println!(
                        "{}",
                        crate::fmt::dim_red(&format!(
                            "Failed to load image {}: {e}",
                            attachment.filename
                        ))
                    ),
                },
                Err(e) => println!(
                    "{}",
                    crate::fmt::dim_red(&format!(
                        "Failed to load image {}: {e}",
                        attachment.filename
                    ))
                ),
            },
            Err(e) => println!(
                "{}",
                crate::fmt::dim_red(&format!(
                    "Failed to load image {}: {e}",
                    attachment.filename
                ))
            ),
        }
    }
}

fn render_image_bytes(data: &[u8]) -> Result<String, String> {
    let img = image::load_from_memory(data).map_err(|e| e.to_string())?;
    let rgba = img.to_rgba8();
    let (w, h) = rgba.dimensions();
    if w == 0 || h == 0 {
        return Err("image has zero dimensions".to_string());
    }
    let new_h = (((h as f32 * IMG_WIDTH as f32 / w as f32).round()) as u32).max(1);
    let small = image::imageops::resize(
        &rgba,
        IMG_WIDTH,
        new_h,
        image::imageops::FilterType::Triangle,
    );

    let mut out = String::new();
    let mut y = 0u32;
    while y < new_h {
        for x in 0..IMG_WIDTH {
            let top = small.get_pixel(x, y);
            let (tr, tg, tb) = (top.0[0], top.0[1], top.0[2]);
            let (br, bg, bb) = if y + 1 < new_h {
                let b = small.get_pixel(x, y + 1);
                (b.0[0], b.0[1], b.0[2])
            } else {
                (0, 0, 0)
            };
            out.push_str(&format!(
                "\x1b[38;2;{tr};{tg};{tb}m\x1b[48;2;{br};{bg};{bb}m▀"
            ));
        }
        out.push_str(RESET);
        out.push('\n');
        y += 2;
    }
    Ok(out)
}
