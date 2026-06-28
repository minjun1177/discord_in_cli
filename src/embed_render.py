import discord
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import print

console = Console()


def render_embeds_and_components(message: discord.Message) -> None:
    render_components = []

    if message.embeds:
        for embed in message.embeds:
            hex_color = (
                f"#{embed.color.value:06x}" if embed.color else "#7289da"
            )

            embed_elements = []

            if embed.title:
                embed_elements.append(Text(f"📌 {embed.title}", style="bold white"))
            if embed.description:
                embed_elements.append(Text(f"{embed.description}\n"))

            if embed.fields:
                field_table = Table(
                    show_header=False, expand=True, box=None, padding=(0, 2, 1, 0)
                )
                field_table.add_column(justify="left")
                field_table.add_column(justify="left")
                field_table.add_column(justify="left")

                current_row = []
                for field in embed.fields:
                    field_text = Text()
                    field_text.append(f"🔹 {field.name}\n", style="bold white")
                    field_text.append(f"{field.value}")

                    if field.inline:
                        current_row.append(field_text)
                        if len(current_row) == 3:
                            field_table.add_row(*current_row)
                            current_row = []
                    else:
                        if current_row:
                            while len(current_row) < 3:
                                current_row.append("")
                            field_table.add_row(*current_row)
                            current_row = []
                        field_table.add_row(field_text, "", "")

                if current_row:
                    while len(current_row) < 3:
                        current_row.append("")
                    field_table.add_row(*current_row)

                embed_elements.append(field_table)

            footer_text = []
            if embed.footer and embed.footer.text:
                footer_text.append(embed.footer.text)
            if embed.timestamp:
                footer_text.append(embed.timestamp.strftime("%Y-%m-%d %H:%M:%S"))

            if footer_text:
                embed_elements.append(
                    Text(f"\n{' | '.join(footer_text)}", style="italic dim")
                )

            if embed_elements:
                embed_panel = Panel(
                    Group(*embed_elements),
                    border_style=hex_color,
                    padding=(0, 1),
                )
                render_components.append(embed_panel)

    if message.components:
        render_components.append(Text("\n[ UI Components ]", style="bold yellow"))

        def extract_items(component_list):
            extracted = []
            for item in component_list:
                if hasattr(item, 'children'):
                    extracted.extend(item.children)
                elif hasattr(item, 'items'):
                    extracted.extend(extract_items(item.items))
                elif hasattr(item, 'accessory') and item.accessory:
                    extracted.append(item.accessory)
                    extracted.append(item)
                else:
                    extracted.append(item)
            return extracted

        all_children = extract_items(message.components)

        row_components_text = Text()
        for child in all_children:
            type_name = child.__class__.__name__.lower()

            if "button" in type_name or (hasattr(child, 'type') and child.type == discord.ComponentType.button):
                label = getattr(child, 'label', None) or (child.emoji.name if getattr(child, 'emoji', None) else "Button")
                row_components_text.append(f"[ {label} ] ", style="bold cyan")

            elif "select" in type_name or (hasattr(child, 'type') and "select" in str(child.type)):
                placeholder = getattr(child, 'placeholder', None) or "Select an option..."
                row_components_text.append(f"▼ {placeholder} (Selection Menu) ", style="bold magenta")

            elif "textdisplay" in type_name:
                content = getattr(child, 'content', '') or getattr(child, 'text', '')
                if content:
                    row_components_text.append(f"\n💬 {content}", style="dim white")

            elif "separator" in type_name:
                row_components_text.append("\n" + "─" * 40, style="dim gray")

            else:
                if hasattr(child, 'text') and child.text:
                    row_components_text.append(f"\n📄 {child.text}", style="dim")

        render_components.append(row_components_text)

    if not render_components:
        return

    wrapper_panel = Panel(
        Group(*render_components),
        title="[bold]Embeds / Components[/bold]",
        title_align="left",
        border_style="#7289da",
        subtitle=f"[dim]Author: {message.author}[/dim]",
        subtitle_align="right",
    )

    print("")
    print(wrapper_panel)