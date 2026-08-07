import discord
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import print
import climage
from PIL import Image
import io

console = Console()


def _render_image_sync(img: Image.Image) -> Text:
    try:
        # Try with unicode blocks first
        output = climage.convert_pil(img, is_unicode=True, width=50)
    except Exception:
        # Fallback to ascii/background spaces
        output = climage.convert_pil(img, is_unicode=False, width=50)
    
    return Text.from_ansi(output)


async def render_images_async(message: discord.Message) -> None:
    image_attachments = [a for a in message.attachments if a.content_type and a.content_type.startswith('image/')]
    
    if not image_attachments:
        return
        
    for attachment in image_attachments:
        try:
            data = await attachment.read()
            img = Image.open(io.BytesIO(data))
            img = img.convert("RGBA")
            text = _render_image_sync(img)
            
            panel = Panel(
                text,
                title=f"🖼️ {attachment.filename}",
                title_align="left",
                border_style="dim cyan"
            )
            print("")
            print(panel)
        except Exception as e:
            print(f"[dim red]Failed to load image {attachment.filename}: {e}[/]")


async def build_image_renderables(message: discord.Message) -> list:
    """Return a list of Rich Panel renderables for image attachments (TUI mode).

    Same logic as render_images_async but returns renderables instead of
    printing them, for use with Textual's RichLog widget.
    """
    image_attachments = [
        a for a in message.attachments
        if a.content_type and a.content_type.startswith('image/')
    ]
    if not image_attachments:
        return []

    panels = []
    for attachment in image_attachments:
        try:
            data = await attachment.read()
            img = Image.open(io.BytesIO(data))
            img = img.convert("RGBA")
            text = _render_image_sync(img)
            panel = Panel(
                text,
                title=f"🖼️ {attachment.filename}",
                title_align="left",
                border_style="dim cyan",
            )
            panels.append(panel)
        except Exception as e:
            panels.append(
                Text.from_markup(f"[dim red]  ✖ Failed to load {attachment.filename}: {e}[/]")
            )
    return panels
