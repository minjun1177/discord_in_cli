import asyncio
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Static, Tree, RichLog, Label, OptionList
from textual.containers import Container, Vertical, Horizontal
from textual import on, events
import discord
from rich.text import Text

COMMAND_LIST = [
    "/status", "/select", "/exit", "/embed", "/img", "/setrpc", "/refresh",
    "/messages", "/edit", "/editmsg", "/reply", "/uploadfile", "/downloadfile",
    "/react", "/unreact", "/delete", "/pins", "/channels", "/thread", "/search",
    "/stop", "/help"
]

class ChatInput(Input):
    def on_key(self, event: events.Key) -> None:
        try:
            box = self.app.query_one("#suggestion-box", OptionList)
        except Exception:
            return
            
        if box.display:
            if event.key == "down":
                event.prevent_default()
                event.stop()
                if box.highlighted is None: box.highlighted = 0
                else: box.highlighted = min(box.option_count - 1, box.highlighted + 1)
            elif event.key == "up":
                event.prevent_default()
                event.stop()
                if box.highlighted is None: box.highlighted = box.option_count - 1
                else: box.highlighted = max(0, box.highlighted - 1)
            elif event.key == "tab":
                if box.highlighted is not None:
                    event.prevent_default()
                    event.stop()
                    option = box.get_option_at_index(box.highlighted)
                    self.value = str(option.prompt) + " "
                    self.cursor_position = len(self.value)
                    box.display = False

from textual.theme import Theme

class DiscordTUI(App):
    CSS_PATH = "tui.tcss"
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+l", "focus_input", "Focus Input"),
        ("ctrl+t", "focus_tree", "Focus Channels"),
        ("f2", "toggle_members", "Toggle Users"),
    ]

    def __init__(self, command_handler):
        super().__init__()
        self.command_handler = command_handler
        self.bot_user = None

    def on_mount(self) -> None:
        self.register_theme(
            Theme(
                name="discord",
                primary="#5865F2",
                secondary="#3ba55c",
                warning="#faa61a",
                error="#ed4245",
                success="#3ba55c",
                accent="#5865F2",
                background="#202225",
                surface="#36393f",
                panel="#2f3136",
                dark=True,
                variables={
                    "boost": "#40444b",
                }
            )
        )
        self.theme = "discord"
        self.query_one("#chat-input").focus()
        self.query_one("#channel-tree").root.expand()

    def compose(self) -> ComposeResult:
        with Horizontal(id="app-grid"):
            with Vertical(id="sidebar"):
                yield Label(" Channels", id="sidebar-header")
                yield Tree("Servers", id="channel-tree")
            with Vertical(id="main-content"):
                yield Label(" Discord CLI", id="header-bar")
                yield RichLog(id="messages", highlight=True, markup=True, wrap=True)
                yield OptionList(id="suggestion-box")
                with Container(id="input-area"):
                    yield ChatInput(placeholder="Type a message or /command...", id="chat-input")
            with Vertical(id="members-sidebar"):
                yield Label(" Members", id="members-header")
                yield Tree("Users", id="members-tree")
        yield Footer()

    def action_focus_input(self) -> None:
        self.query_one("#chat-input").focus()

    def action_focus_tree(self) -> None:
        self.query_one("#channel-tree").focus()

    def action_toggle_members(self) -> None:
        try:
            members_sidebar = self.query_one("#members-sidebar")
            members_sidebar.display = not members_sidebar.display
        except Exception:
            pass

    @on(Input.Changed, "#chat-input")
    def on_input_changed(self, event: Input.Changed) -> None:
        value = event.value
        try:
            box = self.query_one("#suggestion-box", OptionList)
        except Exception:
            return
            
        if not value.startswith("/") or " " in value:
            box.display = False
            return
            
        matches = [cmd for cmd in COMMAND_LIST if cmd.startswith(value)]
        
        if not matches:
            box.display = False
            return
            
        box.clear_options()
        for match in matches:
            box.add_option(match)
            
        box.display = True

    @on(Input.Submitted, "#chat-input")
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        try:
            box = self.query_one("#suggestion-box", OptionList)
            if box.display and box.highlighted is not None:
                option = box.get_option_at_index(box.highlighted)
                event.input.value = str(option.prompt) + " "
                event.input.cursor_position = len(event.input.value)
                box.display = False
                return
        except Exception:
            pass
            
        value = event.value
        event.input.value = ""
        try:
            self.query_one("#suggestion-box", OptionList).display = False
        except Exception:
            pass
            
        if value.strip():
            await self.command_handler(value)

    def write_message(self, content):
        rich_log = self.query_one("#messages", RichLog)
        rich_log.write(content)

    def update_header(self, text: str):
        try:
            self.query_one("#header-bar", Label).update(text)
        except Exception:
            pass

    def clear_messages(self):
        try:
            self.query_one("#messages", RichLog).clear()
        except Exception:
            pass

    def update_tree(self, target_guild: discord.Guild, bot_member: discord.Member, selected_channel_id=None):
        try:
            tree = self.query_one("#channel-tree", Tree)
            tree.clear()
            tree.root.expand()
            tree.root.label = target_guild.name

            active_threads = {}
            for thread in target_guild.threads:
                if thread.parent_id not in active_threads:
                    active_threads[thread.parent_id] = []
                active_threads[thread.parent_id].append(thread)

            for category, channels in target_guild.by_category():
                category_name = category.name if category else "No Category"
                cat_node = tree.root.add(category_name, expand=True)
                for channel in channels:
                    if channel.permissions_for(bot_member).read_messages:
                        if isinstance(channel, discord.ForumChannel):
                            prefix = "📝"
                        elif isinstance(channel, discord.VoiceChannel):
                            prefix = "🔊"
                        else:
                            prefix = "💬"
                            
                        label = f"{prefix} {channel.name}"
                        if channel.id == selected_channel_id:
                            label = f"[*] {label}"
                        
                        if channel.id in active_threads:
                            channel_node = cat_node.add(label, data={"id": channel.id})
                            for thread in active_threads[channel.id]:
                                thread_label = f"🧵 {thread.name}"
                                if thread.id == selected_channel_id:
                                    thread_label = f"[*] {thread_label}"
                                channel_node.add_leaf(thread_label, data={"id": thread.id})
                            # Keep channel node collapsed by default so it's not too cluttered
                            channel_node.collapse()
                        else:
                            cat_node.add_leaf(label, data={"id": channel.id})
                        
            self.update_members_tree(target_guild)
        except Exception:
            pass

    def update_members_tree(self, target_guild: discord.Guild):
        try:
            m_tree = self.query_one("#members-tree", Tree)
            m_tree.clear()
            m_tree.root.expand()
            m_tree.root.label = "Server Members"
            
            online_node = m_tree.root.add("Online", expand=True)
            offline_node = m_tree.root.add("Offline", expand=False)
            
            online_count = 0
            offline_count = 0
            
            for member in target_guild.members:
                if member.status == discord.Status.offline:
                    status_icon = "⚪"
                    offline_node.add_leaf(f"{status_icon} {member.display_name}")
                    offline_count += 1
                else:
                    if member.status == discord.Status.dnd:
                        status_icon = "🔴"
                    elif member.status == discord.Status.idle:
                        status_icon = "🌙"
                    else:
                        status_icon = "🟢"
                    online_node.add_leaf(f"{status_icon} {member.display_name}")
                    online_count += 1
                    
            online_node.label = f"Online — {online_count}"
            offline_node.label = f"Offline — {offline_count}"
        except Exception:
            pass

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        if event.node.data and "id" in event.node.data:
            channel_id = event.node.data["id"]
            asyncio.create_task(self.command_handler(f"/select {channel_id}"))
            self.query_one("#chat-input").focus()

_app_instance = None

def get_app():
    return _app_instance

def tui_print(*args, end="\n", **kwargs):
    if _app_instance:
        if len(args) == 1:
            content = args[0]
        else:
            content = " ".join(str(a) for a in args)
        
        try:
            _app_instance.call_from_thread(_app_instance.write_message, content)
        except Exception:
            _app_instance.write_message(content)
    else:
        import rich
        rich.print(*args, end=end, **kwargs)

async def start_tui(command_handler):
    global _app_instance
    _app_instance = DiscordTUI(command_handler)
    await _app_instance.run_async()
