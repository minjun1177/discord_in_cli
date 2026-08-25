from discord.ext import commands, tasks
from datetime import timezone, datetime
import discord
import os
import json
import asyncio
import sys
import re
from rich.markup import escape as rich_escape
from src.tui import start_tui, get_app
from src.tui import tui_print as print
import pyperclip
import src.log as log
import src.alert as alert
import src.embed_render as embed_render
import src.image_render as image_render

with open("settings.json", "r") as f:
    settings = json.load(f)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

bot = discord.Bot(intents=intents)

MONITOR_CHANNEL_ID = int(settings["CHANNEL_ID"])
USERNAME = settings.get("USERNAME", "Sparky")
ALLOW_MENTION_EVERYONE = settings.get("ALLOW_MENTION_EVERYONE", False)
SAVE_MESSAGES = settings.get("SAVE_MESSAGES", True)
SAVE_FILENAME = settings.get("SAVE_FILENAME", "messages.log")
SAVE_AS_JSON = settings.get("SAVE_AS_JSON", False)
SERVER_ID = int(settings.get("SERVER_ID", None)) if settings.get("SERVER_ID") else None
FETCH_HISTORY_LIMIT = int(settings.get("FETCH_HISTORY_LIMIT", 10))
EMBED_VIEW_DEF = settings.get("EMBED_VIEW_default", False)
MSG_HISTORY_MAX = int(settings.get("MSG_HISTORY_MAX", 50))

def _esc(text) -> str:
    """Escape user-controlled text so Discord content is never parsed as Rich markup."""
    return rich_escape(str(text))

global SELECT_CHANNEL_ID
SELECT_CHANNEL_ID = None

global embed_view_enabled
embed_view_enabled = EMBED_VIEW_DEF

global img_view_enabled
img_view_enabled = settings.get("IMG_VIEW_default", False)

channel_messages: list[discord.Message] = []

def _add_to_channel_messages(msg: discord.Message) -> None:
    if any(m.id == msg.id for m in channel_messages):
        return
    channel_messages.append(msg)
    if len(channel_messages) > MSG_HISTORY_MAX:
        channel_messages.pop(0)

async def print_discord_msg(msg, is_edit=False, before=None) -> None:
    embed_count = len(msg.embeds)
    image_attachments = [a for a in msg.attachments if a.content_type and a.content_type.startswith('image/')]
    if not image_attachments and msg.attachments:
        exts = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.tiff')
        image_attachments = [a for a in msg.attachments if a.filename and a.filename.lower().endswith(exts)]
    img_count = len(image_attachments)
    
    clean_content = before.clean_content if is_edit and before else msg.clean_content
    has_content = bool(clean_content.strip())
    
    hidden_texts = []
    if not embed_view_enabled and embed_count > 0:
        hidden_texts.append(f"{embed_count} Embed(s) hidden")
    if not img_view_enabled and img_count > 0:
        hidden_texts.append(f"{img_count} Image(s) hidden")
        
    hide_main_text = not has_content and len(hidden_texts) > 0
    
    author_name = _esc(msg.author.name)
    author_name_colored = f"[#B4009E]{author_name}[/]" if msg.author.bot else author_name
    bot_suffix = "(bot)" if msg.author.bot else ""
    time_str = msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
    
    ch_target = before.channel if is_edit and before else msg.channel
    ch_name = _esc(getattr(ch_target, 'name', 'DM'))
    
    if alert.check(msg):
        prefix = f"[#EA9800 on #2B251C]{author_name}{bot_suffix}"
        suffix = "[/]"
    else:
        prefix = f"{author_name_colored}{bot_suffix}"
        suffix = ""
        
    if is_edit and before:
        action = " Modified"
        if hide_main_text:
            text = f"\\[{', '.join(hidden_texts)}]"
        else:
            text = _esc(f"{before.content} -> {msg.content}")
    else:
        action = ""
        if hide_main_text:
            text = f"\\[{', '.join(hidden_texts)}]"
        else:
            text = _esc(resolve_markup(msg))
            
    highlights = settings.get("HIGHLIGHTS", [])
    if highlights and has_content:
        for word in highlights:
            if word.lower() in text.lower():
                print('\a', end='') # Bell sound
                text = re.sub(f"({re.escape(word)})", r"[black on yellow]\1[/]", text, flags=re.IGNORECASE)

    if action:
        print(f"{prefix} ({time_str}){action}: {text}{suffix}")
    else:
        print(f"{prefix} ({time_str}): {text}{suffix}")
        
    if msg.embeds or msg.components:
        if embed_view_enabled:
            renderables = embed_render.build_embed_renderables(msg)
            for r in renderables: print(r)
        elif embed_count > 0 and has_content:
            print("  [bold dim]\\[Embed][/]")
            
    if img_count > 0:
        if img_view_enabled:
            renderables = await image_render.build_image_renderables(msg)
            for r in renderables: print(r)
        elif has_content:
            print(f"  [bold dim]\\[{img_count} Image(s) hidden][/]")

async def get_all_channels(target_guild: discord.Guild) -> None:
    bot_member = target_guild.me 
    if not bot_member:
        bot_member = target_guild.get_member(bot.user.id)

    print(f"=== Server: '{target_guild.name}' (ID: {target_guild.id}) ===")
    
    for category, channels in target_guild.by_category():
        category_name = category.name if category else "None Category"
        print(f"\n📂 {category_name}:")
        
        for channel in channels:
            if channel.permissions_for(bot_member).read_messages:
                
                if isinstance(channel, discord.TextChannel):
                    print(f"   💬  [Chat]  {channel.name} (ID: {channel.id})")
                
                elif isinstance(channel, discord.VoiceChannel):
                    print(f"   🔊  [Voice] {channel.name} (ID: {channel.id})")
    print("\nUse '/select <channel_id>' to select a channel for monitoring and sending messages.")

async def get_target_message(target: str, channel: discord.abc.Messageable) -> discord.Message | None:
    if target.startswith("~") and target[1:].isdigit():
        index = int(target[1:])
        if index < 1 or index > len(channel_messages):
            print(f"[ERROR] Index ~{index} is out of range. You have {len(channel_messages)} message(s) in history.")
            return None
        return channel_messages[-index]
    elif target.isdigit():
        try:
            return await channel.fetch_message(int(target))
        except discord.NotFound:
            print(f"[ERROR] Message ID {target} was not found in the selected channel.")
            return None
        except Exception as e:
            print(f"[ERROR] Failed to fetch message ID {target}: {e}")
            return None
    else:
        print("[ERROR] Target must be ~N or <message_id>.")
        return None

async def process_command(line: str) -> None:
    global SELECT_CHANNEL_ID, embed_view_enabled, img_view_enabled
    
    channel = bot.get_channel(SELECT_CHANNEL_ID if SELECT_CHANNEL_ID else MONITOR_CHANNEL_ID)
    
    if not channel:
        print(f"[ERROR] Channel with ID {SELECT_CHANNEL_ID if SELECT_CHANNEL_ID else MONITOR_CHANNEL_ID} not found. Please check the ID.")
        return

    if True:
        line = line.strip()
        
        if not line:
            return

        parts_for_alias = line.split()
        if parts_for_alias and parts_for_alias[0] in settings.get("ALIASES", {}):
            alias_name = parts_for_alias[0]
            alias_command = settings["ALIASES"][alias_name]
            additional_args = line[len(alias_name):].strip()
            new_command = f"{alias_command} {additional_args}".strip()
            print(f"[SYSTEM] Executing alias '{alias_name}' -> '{new_command}'")
            line = new_command
        
        if line == "/status":
            print(f"[SYSTEM] Bot connected to '{channel.name if channel else 'Unknown'}' (ID: {channel.id if channel else 'Unknown'}) in server '{channel.guild.name if channel and channel.guild else 'Unknown'}' (ID: {channel.guild.id if channel and channel.guild else 'Unknown'}).")
        elif line == "/stop":
            print("[SYSTEM] Stopping bot...")
            await bot.close()
            tui_app = get_app()
            if tui_app:
                tui_app.exit()
            return
        elif "@everyone" in line and not ALLOW_MENTION_EVERYONE:
            print("[ERROR] '@everyone' is not allowed.")
        elif line.startswith("/select"):
            parts = line.split()
            if len(parts) == 2 and parts[1].isdigit():
                temp_id = int(parts[1])
                selected_channel = bot.get_channel(temp_id)
                if selected_channel is None and SERVER_ID:
                    g = bot.get_guild(SERVER_ID)
                    if g: selected_channel = g.get_thread(temp_id)
                if selected_channel is None:
                    try:
                        selected_channel = await bot.fetch_channel(temp_id)
                    except Exception:
                        pass
                        
                if selected_channel:
                    SELECT_CHANNEL_ID = temp_id
                    channel = selected_channel
                    channel_messages.clear()
                    
                    tui_app = get_app()
                    if tui_app:
                        tui_app.clear_messages()
                        is_thread = isinstance(selected_channel, discord.Thread)
                        prefix_char = "🧵" if is_thread else ("📝" if isinstance(selected_channel, discord.ForumChannel) else "#")
                        tui_app.update_header(f" {selected_channel.guild.name} - {prefix_char}{selected_channel.name}")
                        if SERVER_ID:
                            tui_app.update_tree(bot.get_guild(SERVER_ID), bot.get_guild(SERVER_ID).me, SELECT_CHANNEL_ID)
                            
                    try:
                        messages = [msg async for msg in selected_channel.history(limit=FETCH_HISTORY_LIMIT)]
                        for msg in reversed(messages):
                            _add_to_channel_messages(msg)
                            await print_discord_msg(msg)
                    except Exception as e:
                        print(f"[ERROR] Could not fetch messages: {e}")
                else:
                    print(f"[ERROR] Channel/Thread with ID {temp_id} not found.")
            else:
                print("[ERROR] Invalid command. Use '/select <channel_id>'.")
        elif line.startswith("/embed"):
            parts = line.split()
            if len(parts) == 2 and parts[1] in ("open", "close"):
                embed_view_enabled = parts[1] == "open"
                status = "enabled" if embed_view_enabled else "disabled"
                print(f"[SYSTEM] Embed rendering is now {status}.")
                current_ch = bot.get_channel(SELECT_CHANNEL_ID) if SELECT_CHANNEL_ID else None
                if current_ch:
                    print(f"[SYSTEM] Refreshing messages from '{current_ch.name}'...")
                    try:
                        messages = [msg async for msg in current_ch.history(limit=FETCH_HISTORY_LIMIT)]
                        channel_messages.clear()
                        for msg in reversed(messages):
                            _add_to_channel_messages(msg)
                            await print_discord_msg(msg)
                    except Exception as e:
                        print(f"[ERROR] Could not refresh messages: {e}")
            else:
                print("[ERROR] Usage: /embed open or /embed close")
        elif line.startswith("/img"):
            parts = line.split()
            if len(parts) == 2 and parts[1] in ("open", "close"):
                img_view_enabled = parts[1] == "open"
                status = "enabled" if img_view_enabled else "disabled"
                print(f"[SYSTEM] Image rendering is now {status}.")
                current_ch = bot.get_channel(SELECT_CHANNEL_ID) if SELECT_CHANNEL_ID else None
                if current_ch:
                    print(f"[SYSTEM] Refreshing messages from '{current_ch.name}'...")
                    try:
                        messages = [msg async for msg in current_ch.history(limit=FETCH_HISTORY_LIMIT)]
                        channel_messages.clear()
                        for msg in reversed(messages):
                            _add_to_channel_messages(msg)
                            await print_discord_msg(msg)
                    except Exception as e:
                        print(f"[ERROR] Could not refresh messages: {e}")
            else:
                print("[ERROR] Usage: /img open or /img close")
        elif line.startswith("/react"):
            parts = line.split(maxsplit=2)
            if len(parts) < 3:
                print("[ERROR] Usage: /react ~N <emoji>")
                return
            target_msg = await get_target_message(parts[1], channel)
            if target_msg:
                try:
                    await target_msg.add_reaction(parts[2])
                    print(f"[SYSTEM] Reacted to message {target_msg.id} with {parts[2]}")
                except Exception as e:
                    print(f"[ERROR] Failed to react: {e}")
        elif line.startswith("/unreact"):
            parts = line.split(maxsplit=2)
            if len(parts) < 3:
                print("[ERROR] Usage: /unreact ~N <emoji>")
                return
            target_msg = await get_target_message(parts[1], channel)
            if target_msg:
                try:
                    await target_msg.remove_reaction(parts[2], bot.user)
                    print(f"[SYSTEM] Removed reaction {parts[2]} from message {target_msg.id}")
                except Exception as e:
                    print(f"[ERROR] Failed to unreact: {e}")
        elif line.startswith("/delete"):
            parts = line.split()
            if len(parts) < 2:
                print("[ERROR] Usage: /delete ~N or /delete <id>")
                return
            target_msg = await get_target_message(parts[1], channel)
            if target_msg:
                try:
                    await target_msg.delete()
                    print(f"[SYSTEM] Deleted message {target_msg.id}")
                except discord.Forbidden:
                    print("[ERROR] You don't have permission to delete this message.")
                except Exception as e:
                    print(f"[ERROR] Failed to delete: {e}")
        elif line == "/pins":
            try:
                pins = await channel.pins()
                print(f"[SYSTEM] Pinned messages in {channel.name}:")
                for p in pins:
                    print(f"  - {p.author.name}: {p.content[:50]}... (ID: {p.id})")
            except Exception as e:
                print(f"[ERROR] Failed to fetch pins: {e}")
        elif line == "/channels":
            if SERVER_ID is None:
                print("[ERROR] SERVER_ID is not set.")
                return
            target_guild = bot.get_guild(SERVER_ID)
            if target_guild:
                await get_all_channels(target_guild)
        elif line.startswith("/thread"):
            parts = line.split()
            if len(parts) < 2:
                print("[ERROR] Usage: /thread enter <thread_id> | /thread exit")
                return
            subcmd = parts[1]
            if subcmd == "enter":
                if len(parts) < 3:
                    print("[ERROR] Usage: /thread enter <thread_id>")
                    return
                thread_id = int(parts[2])
                try:
                    target_thread = bot.get_channel(thread_id) or await bot.fetch_channel(thread_id)
                    if isinstance(target_thread, discord.Thread):
                        SELECT_CHANNEL_ID = thread_id
                        channel = target_thread
                        channel_messages.clear()
                        
                        tui_app = get_app()
                        if tui_app:
                            tui_app.clear_messages()
                            tui_app.update_header(f" {target_thread.guild.name} - 🧵 {target_thread.name}")
                            
                        messages = [msg async for msg in target_thread.history(limit=FETCH_HISTORY_LIMIT)]
                        for msg in reversed(messages):
                            _add_to_channel_messages(msg)
                            await print_discord_msg(msg)
                    else:
                        print(f"[ERROR] ID {thread_id} is not a thread.")
                except Exception as e:
                    print(f"[ERROR] Failed to enter thread: {e}")
            elif subcmd == "exit":
                if isinstance(channel, discord.Thread):
                    SELECT_CHANNEL_ID = channel.parent_id
                    channel = channel.parent
                    channel_messages.clear()
                    
                    tui_app = get_app()
                    if tui_app:
                        tui_app.clear_messages()
                        tui_app.update_header(f" {channel.guild.name} - #{channel.name}")
                        if SERVER_ID:
                            tui_app.update_tree(bot.get_guild(SERVER_ID), bot.get_guild(SERVER_ID).me, SELECT_CHANNEL_ID)
                            
                    print(f"[SYSTEM] Exited thread. Returned to channel '{channel.name}' (ID: {channel.id})")
                else:
                    print("[ERROR] You are not in a thread.")
        elif line.startswith("/search"):
            parts = line.split(maxsplit=1)
            if len(parts) < 2:
                print("[ERROR] Usage: /search <query>")
                return
            query = parts[1].lower()
            print(f"[SYSTEM] Searching for '{query}' in cached messages...")
            found = 0
            for m in channel_messages:
                if query in m.content.lower() or query in m.author.name.lower():
                    await print_discord_msg(m)
                    found += 1
            print(f"[SYSTEM] Found {found} message(s).")
        elif line.startswith("/highlight"):
            parts = line.split(maxsplit=2)
            if len(parts) < 2:
                print("[ERROR] Usage: /highlight list | /highlight add <word> | /highlight remove <word>")
                return
            subcmd = parts[1]
            highlights = settings.get("HIGHLIGHTS", [])
            if subcmd == "list":
                print(f"[SYSTEM] Current highlights: {', '.join(highlights) if highlights else 'None'}")
            elif subcmd == "add" and len(parts) == 3:
                word = parts[2]
                if word not in highlights:
                    highlights.append(word)
                    settings["HIGHLIGHTS"] = highlights
                    with open("settings.json", "w") as f:
                        json.dump(settings, f, indent=4)
                    print(f"[SYSTEM] Added highlight: {word}")
                else:
                    print(f"[SYSTEM] '{word}' is already highlighted.")
            elif subcmd == "remove" and len(parts) == 3:
                word = parts[2]
                if word in highlights:
                    highlights.remove(word)
                    settings["HIGHLIGHTS"] = highlights
                    with open("settings.json", "w") as f:
                        json.dump(settings, f, indent=4)
                    print(f"[SYSTEM] Removed highlight: {word}")
                else:
                    print(f"[ERROR] Highlight '{word}' not found.")
        elif line.startswith("/copy"):
            parts = line.split()
            if len(parts) < 2:
                print("[ERROR] Usage: /copy ~N or /copy <id>")
                return
            target_msg = await get_target_message(parts[1], channel)
            if target_msg:
                try:
                    pyperclip.copy(target_msg.content)
                    print(f"[SYSTEM] Copied message {target_msg.id} content to clipboard.")
                except Exception as e:
                    print(f"[ERROR] Failed to copy to clipboard: {e}")
        elif line == "/exit":
            print("[SYSTEM] Exiting channel selection mode.")
            SELECT_CHANNEL_ID = None
            channel_messages.clear()
            channel = bot.get_channel(MONITOR_CHANNEL_ID)
            
            tui_app = get_app()
            if tui_app:
                tui_app.clear_messages()
                if channel:
                    tui_app.update_header(f" {channel.guild.name} - #{channel.name}")
                    
            if SERVER_ID is None:
                print("[ERROR] SERVER_ID is not set in settings.json. Please provide a valid server ID.")
                return
            await get_all_channels(bot.get_guild(SERVER_ID))
        elif line.startswith("/setrpc"):
            # cmd like this: /setrpc <text> [status] but status can be optional and can be one of: online, idle, dnd, offline
            # status is always the LAST word if it matches a known status keyword
            VALID_STATUSES = {"online", "idle", "dnd", "offline"}
            raw = line[len("/setrpc"):].strip()
            if not raw:
                print("[ERROR] Usage: /setrpc <activity text> [online|idle|dnd|offline]")
            else:
                new_status = discord.Status.online
                tokens = raw.rsplit(maxsplit=1)
                if len(tokens) == 2 and tokens[1].lower() in VALID_STATUSES:
                    activity_text = tokens[0]
                    status_str = tokens[1].lower()
                else:
                    activity_text = raw
                    status_str = "online"

                if status_str == "online":
                    new_status = discord.Status.online
                elif status_str == "idle":
                    new_status = discord.Status.idle
                elif status_str == "dnd":
                    new_status = discord.Status.dnd
                elif status_str == "offline":
                    new_status = discord.Status.invisible

                activity = discord.Activity(
                    type=discord.ActivityType.playing,
                    name=activity_text
                )
                await bot.change_presence(status=new_status, activity=activity)
                print(f"[SYSTEM] Rich Presence set to '{activity_text}' with status '{new_status}'.")
                if SELECT_CHANNEL_ID:
                    current_ch = bot.get_channel(SELECT_CHANNEL_ID)
                    if current_ch:
                        try:
                            messages = [msg async for msg in current_ch.history(limit=FETCH_HISTORY_LIMIT)]
                            channel_messages.clear()
                            for msg in reversed(messages):
                                _add_to_channel_messages(msg)
                                await print_discord_msg(msg)
                        except Exception as e:
                            print(f"[ERROR] Could not refresh messages: {e}")
        elif line == "/refresh":
            current_ch = bot.get_channel(SELECT_CHANNEL_ID) if SELECT_CHANNEL_ID else None
            if current_ch:
                print(f"[SYSTEM] Refreshing messages from '{current_ch.name}'...")
                try:
                    messages = [msg async for msg in current_ch.history(limit=FETCH_HISTORY_LIMIT)]
                    channel_messages.clear()
                    for msg in reversed(messages):
                        _add_to_channel_messages(msg)
                        await print_discord_msg(msg)
                except Exception as e:
                    print(f"[ERROR] Could not refresh messages: {e}")
            else:
                print("[ERROR] No channel selected to refresh.")
        elif line.startswith("/messages"):
            parts = line.split(maxsplit=1)
            if len(parts) == 2 and parts[1] == "all":
                my_messages = [(i, msg) for i, msg in enumerate(reversed(channel_messages), 1)]
            else:
                my_messages = [(i, msg) for i, msg in enumerate(reversed(channel_messages), 1)
                               if msg.author == bot.user]
            if not my_messages:
                print("[SYSTEM] No sent messages in history.")
            else:
                print(f"[SYSTEM] Your sent messages (newest first):")
                for i, msg in reversed(my_messages):
                    author_name = _esc(msg.author.name)
                    author_name = f"[#B4009E]{author_name}[/]" if msg.author.bot else author_name
                    resolved = resolve_markup(msg)
                    resolved = convert_names_to_mentions(resolved, channel)
                    preview = _esc(resolved[:50] + ("..." if len(resolved) > 50 else ""))
                    time_str = msg.created_at.strftime('%H:%M:%S')
                    print(f"  ~{i}  {author_name} ({time_str}) {preview}")
                print(f"[SYSTEM] Use '/edit <new text>' or '/edit ~N <new text>' to edit.")
                print(f"[SYSTEM] Use '/reply <text>' or '/reply ~N <text>' to reply to a message.")

        elif line.startswith("/edit"):
            # /edit <new_content>         -> edit last message in channel
            # /edit ~N <new_content>      -> edit Nth most recent channel message
            # /editmsg <id> <new_content> -> edit by message ID (fallback)
            raw = line.split(maxsplit=1)
            cmd = raw[0]  # "/edit" or "/editmsg"
            rest = raw[1].strip() if len(raw) > 1 else ""

            if cmd == "/editmsg":
                parts = rest.split(maxsplit=1)
                if len(parts) < 2 or not parts[0].isdigit():
                    print("[ERROR] Usage: /editmsg <message_id> <new_content>")
                    return
                message_id = int(parts[0])
                new_content = parts[1]
                try:
                    target_message = await channel.fetch_message(message_id)
                    await target_message.edit(content=new_content)
                    print(f"[SYSTEM] Edited message ID {message_id} to: {new_content}")
                except discord.NotFound:
                    print(f"[ERROR] Message with ID {message_id} not found in the selected channel.")
                except discord.Forbidden:
                    print(f"[ERROR] Bot does not have permission to edit message ID {message_id}.")
                except Exception as e:
                    print(f"[ERROR] Failed to edit message ID {message_id}: {e}")
            else:
                # /edit command — history-based editing
                if not rest:
                    print("[ERROR] Usage: /edit <new text>  or  /edit ~N <new text>")
                    print("        /edit hello world     → edit last message")
                    print("        /edit ~3 hello world  → edit 3rd most recent message")
                    print("        /messages             → list recent channel messages")
                    return

                if not channel_messages:
                    print("[ERROR] No messages in history to edit. Use /select or /refresh first.")
                    return

                index = 1
                new_content = rest
                if rest.startswith("~"):
                    idx_parts = rest.split(maxsplit=1)
                    idx_str = idx_parts[0][1:]  # strip '~'
                    if idx_str.isdigit() and len(idx_parts) == 2:
                        index = int(idx_str)
                        new_content = idx_parts[1]
                    else:
                        print("[ERROR] Usage: /edit ~N <new text>  (N = message number from /messages)")
                        return

                if index < 1 or index > len(channel_messages):
                    print(f"[ERROR] Index ~{index} is out of range. You have {len(channel_messages)} message(s) in history. Use /messages to see them.")
                    return

                target_message = channel_messages[-index]
                if target_message.author != bot.user:
                    print(f"[ERROR] ~{index} is a message by '{target_message.author.name}'. You can only edit the bot's own messages (marked ★ in /messages).")
                    return
                try:
                    await target_message.edit(content=f"{USERNAME}: {new_content}")
                    print(f"[SYSTEM] Edited message ~{index} to: {new_content}")
                except discord.NotFound:
                    print(f"[ERROR] Message ~{index} was deleted and can no longer be edited.")
                    channel_messages.remove(target_message)
                except discord.Forbidden:
                    print(f"[ERROR] Bot does not have permission to edit that message.")
                except Exception as e:
                    print(f"[ERROR] Failed to edit message: {e}")
        elif line.startswith("/reply"):
            # /reply <content>        -> reply to the last message
            # /reply ~N <content>     -> reply to the Nth most recent message
            rest = line[len("/reply"):].strip()

            if not rest:
                print("[ERROR] Usage: /reply <text>  or  /reply ~N <text>")
                print("        /reply hello          → reply to last message")
                print("        /reply ~3 hello       → reply to 3rd most recent message")
                return

            if not channel_messages:
                print("[ERROR] No messages in history to reply to. Use /select or /refresh first.")
                return

            # Parse optional ~N index
            index = 1  # default: most recent
            reply_content = rest
            if rest.startswith("~"):
                idx_parts = rest.split(maxsplit=1)
                idx_str = idx_parts[0][1:]  # strip '~'
                if idx_str.isdigit() and len(idx_parts) == 2:
                    index = int(idx_str)
                    reply_content = idx_parts[1]
                else:
                    print("[ERROR] Usage: /reply ~N <text>  (N = message number from /messages)")
                    return

            if index < 1 or index > len(channel_messages):
                print(f"[ERROR] Index ~{index} is out of range. You have {len(channel_messages)} message(s) in history.")
                return

            target_message = channel_messages[-index]
            try:
                processed_reply = convert_names_to_mentions(reply_content, channel)
                sent_msg = await channel.send(
                    f"{USERNAME}: {processed_reply}",
                    reference=target_message.to_reference(),
                    mention_author=False
                )
                _add_to_channel_messages(sent_msg)
                resolved_target = resolve_markup(target_message)
                target_preview = _esc(resolved_target[:30] + ("..." if len(resolved_target) > 30 else ""))
                print(f"[SYSTEM] Replied to ~{index} ({_esc(target_message.author.name)}: {target_preview})")
            except discord.NotFound:
                print(f"[ERROR] Message ~{index} was deleted and can no longer be replied to.")
                channel_messages.remove(target_message)
            except discord.HTTPException as e:
                print(f"[ERROR] Failed to reply: {e}")
        elif line.startswith("/uploadfile"):
            parts = line.split(maxsplit=1)
            if len(parts) != 2:
                print("[ERROR] Usage: /uploadfile <file_path>")
                return
            file_path = parts[1]
            if not os.path.isfile(file_path):
                print(f"[ERROR] File '{file_path}' does not exist.")
                return
            try:
                with open(file_path, 'rb') as f:
                    discord_file = discord.File(f)
                    sent_msg = await channel.send(f"{USERNAME} uploaded a file:", file=discord_file)
                    _add_to_channel_messages(sent_msg)
                    print(f"[SYSTEM] Uploaded file '{file_path}' to channel '{channel.name}'.")
            except Exception as e:
                print(f"[ERROR] Failed to upload file: {e}")

        elif line.startswith("/downloadfile"):
            # /downloadfile ~N [attachment_index] [save_path]
            # /downloadfile <message_id> [attachment_index] [save_path]
            parts = line.split(maxsplit=3)
            if len(parts) < 2:
                print("[ERROR] Usage: /downloadfile ~N [attachment_index] [save_path]")
                print("        /downloadfile <message_id> [attachment_index] [save_path]")
                print("        Examples:")
                print("        /downloadfile ~1")
                print("        /downloadfile ~2 1")
                print("        /downloadfile ~3 2 downloads")
                print("        /downloadfile 123456789012345678 1 C:/tmp/file.png")
                return

            target = parts[1]
            attachment_index = 1
            save_target = None

            if len(parts) >= 3:
                if parts[2].isdigit():
                    attachment_index = int(parts[2])
                    if len(parts) == 4:
                        save_target = parts[3]
                else:
                    save_target = parts[2]
                    if len(parts) == 4:
                        print("[ERROR] Invalid arguments. If you provide both attachment_index and save_path, use: /downloadfile <target> <attachment_index> <save_path>")
                        return

            if attachment_index < 1:
                print("[ERROR] attachment_index must be >= 1")
                return

            target_message = None
            if target.startswith("~") and target[1:].isdigit():
                index = int(target[1:])
                if index < 1 or index > len(channel_messages):
                    print(f"[ERROR] Index ~{index} is out of range. You have {len(channel_messages)} message(s) in history.")
                    return
                target_message = channel_messages[-index]
            elif target.isdigit():
                try:
                    target_message = await channel.fetch_message(int(target))
                except discord.NotFound:
                    print(f"[ERROR] Message ID {target} was not found in the selected channel.")
                    return
                except Exception as e:
                    print(f"[ERROR] Failed to fetch message ID {target}: {e}")
                    return
            else:
                print("[ERROR] Target must be ~N or <message_id>.")
                return

            if not target_message.attachments:
                print("[ERROR] The target message has no attachments.")
                return

            if attachment_index > len(target_message.attachments):
                print(f"[ERROR] attachment_index {attachment_index} is out of range. This message has {len(target_message.attachments)} attachment(s).")
                return

            attachment = target_message.attachments[attachment_index - 1]
            # Sanitize the server-controlled filename to prevent path traversal when
            # joining it into a save directory (e.g. a filename like "../../evil").
            file_name = os.path.basename(attachment.filename or f"attachment_{attachment.id}")

            if save_target:
                if os.path.isdir(save_target) or save_target.endswith(("/", "\\")):
                    os.makedirs(save_target, exist_ok=True)
                    save_path = os.path.join(save_target, file_name)
                else:
                    parent = os.path.dirname(save_target)
                    if parent:
                        os.makedirs(parent, exist_ok=True)
                    save_path = save_target
            else:
                default_dir = "downloads"
                os.makedirs(default_dir, exist_ok=True)
                save_path = os.path.join(default_dir, file_name)

            base, ext = os.path.splitext(save_path)
            final_path = save_path
            suffix = 1
            while os.path.exists(final_path):
                final_path = f"{base}_{suffix}{ext}"
                suffix += 1

            try:
                await attachment.save(final_path)
                print(f"[SYSTEM] Downloaded attachment #{attachment_index} from message {target_message.id} to '{final_path}'.")
            except Exception as e:
                print(f"[ERROR] Failed to download attachment: {e}")
        elif line.startswith("/help"):
            print("[SYSTEM] Available commands:")
            print("  /status                           - Show bot connection status.")
            print("  /stop                             - Stop the bot.")
            print("  /select <channel_id>              - Select a channel for monitoring and sending messages.")
            print("  /exit                             - Exit channel selection mode.")
            print("  /embed open|close                 - Enable or disable embed rendering.")
            print("  /img open|close                   - Enable or disable image rendering.")
            print("  /setrpc <text> \\[status]           - Set Rich Presence text and optional status (online, idle, dnd, offline).")
            print("  /refresh                          - Refresh messages from the selected channel.")
            print("  /messages \\[all]                   - List recent messages sent by the bot (or all if 'all' is specified).")
            print("  /edit <new text>                  - Edit the last message sent by the bot.")
            print("  /edit ~N <new text>               - Edit the Nth most recent message sent by the bot.")
            print("  /editmsg <id> <new text>          - Edit a message by its ID (bot's own messages only).")
            print("  /reply <text>                     - Reply to the last message in the channel.")
            print("  /reply ~N <text>                  - Reply to the Nth most recent message in the channel.")
            print("  /uploadfile <file_path>           - Upload a file to the selected channel.")
            print("  /downloadfile ~N \\[index] \\[path]   - Download an attachment from a message in history (~N) or by message ID. Optional attachment index and save path can be specified.")
            print("  /react ~N <emoji>                 - Add a reaction to a message.")
            print("  /unreact ~N <emoji>               - Remove a reaction from a message.")
            print("  /delete ~N                        - Delete a message.")
            print("  /pins                             - Show pinned messages in the current channel.")
            print("  /channels                         - List all channels in the server.")
            print("  /thread enter <id> | exit         - Enter or exit a thread.")
            print("  /search <query>                   - Search for a keyword in cached messages.")
            print("  /highlight add|remove|list <word> - Highlight messages containing the keyword.")
            print("  /copy ~N                          - Copy message text to clipboard.")
            print("  /alias list|set|remove            - List, set, or remove aliases.")
        elif line.startswith("/alias"):
            parts = line.split(maxsplit=3)
            if len(parts) == 1:
                print("[ERROR] Usage: /alias list | /alias set <alias_name> <command> | /alias remove <alias_name>")
                return
            
            subcmd = parts[1]
            if subcmd == "list":
                print("[SYSTEM] Current aliases:")
                aliases = settings.get("ALIASES", {})
                if not aliases:
                    print("  (No aliases set)")
                else:
                    for alias, command in aliases.items():
                        print(f"  {alias} -> {command}")
            elif subcmd == "set":
                if len(parts) < 4:
                    print("[ERROR] Usage: /alias set <alias_name> <command> [args...]")
                    return
                alias_name = parts[2]
                command_str = parts[3]
                settings.setdefault("ALIASES", {})[alias_name] = command_str
                with open("settings.json", "w") as f:
                    json.dump(settings, f, indent=4)
                print(f"[SYSTEM] Alias '{alias_name}' set to '{command_str}'.")
            elif subcmd == "remove":
                if len(parts) < 3:
                    print("[ERROR] Usage: /alias remove <alias_name>")
                    return
                alias_name = parts[2]
                if "ALIASES" in settings and alias_name in settings["ALIASES"]:
                    del settings["ALIASES"][alias_name]
                    with open("settings.json", "w") as f:
                        json.dump(settings, f, indent=4)
                    print(f"[SYSTEM] Alias '{alias_name}' removed.")
                else:
                    print(f"[ERROR] Alias '{alias_name}' not found.")
            else:
                print("[ERROR] Unknown alias command. Usage: list, set, remove")
        elif line.startswith("/"):
            print(f"[ERROR] Unknown command: {line}. Type '/help' for a list of commands.")
        else:
            if SELECT_CHANNEL_ID is None:
                print("[SYSTEM] No channel selected. Please use '/select <channel_id>' to select a channel for monitoring and sending messages.")
            else:
                try:
                    processed_line = convert_names_to_mentions(line, channel)

                    sent_msg = await channel.send(f"{USERNAME}: {processed_line}")
                    _add_to_channel_messages(sent_msg)
                    print(f"{USERNAME}: {line}")
                except Exception as e:
                    print(f"[TRANSMISSION FAILED] Message can not be sent: {e}")

@bot.event
async def on_presence_update(before, after):
    if SERVER_ID and after.guild.id == SERVER_ID:
        tui_app = get_app()
        if tui_app:
            try:
                tui_app.call_from_thread(tui_app.update_members_tree, after.guild)
            except Exception:
                tui_app.update_members_tree(after.guild)

@bot.event
async def on_ready() -> None:
    print(f"Logged in as: {bot.user}")

    target_guild = None
    if SERVER_ID:
        target_guild = bot.get_guild(SERVER_ID)
        if target_guild:
            game = discord.Game(f"Watching {target_guild.name} | Logined as {USERNAME}")
            await bot.change_presence(status=discord.Status.online, activity=game)
            await get_all_channels(target_guild)
        else:
            print(f"Error: Server with ID {SERVER_ID} not found. Please ensure the bot is invited to the server.")
    else:
        print("Error: SERVER_ID is not set in settings.json. Please provide a valid server ID.")
        raise ValueError("Error: SERVER_ID is not set in settings.json. Please provide a valid server ID.")
    alert.init(bot)
    
    tui_app = get_app()
    if tui_app:
        ch = bot.get_channel(SELECT_CHANNEL_ID if SELECT_CHANNEL_ID else MONITOR_CHANNEL_ID)
        if ch:
            tui_app.update_header(f" {ch.guild.name} - #{ch.name}")
        if SERVER_ID and target_guild:
            tui_app.update_tree(target_guild, target_guild.me, SELECT_CHANNEL_ID)

CUSTOM_EMOJI_RE = re.compile(r"<a?:([a-zA-Z0-9_]+):\d+>")


def resolve_markup(message: discord.Message) -> str:
    # clean_content handles user/channel/role mentions and @everyone/@here.
    content = message.clean_content
    # clean_content leaves custom emoji as-is; render them as :name:.
    return CUSTOM_EMOJI_RE.sub(r":\1:", content)

def convert_names_to_mentions(text: str, channel: discord.abc.Messageable) -> str:
    mention_pattern = re.compile(r"@([^\s]+)")

    if not isinstance(channel, discord.TextChannel):
        return text

    guild = channel.guild

    def _resolve(match: re.Match) -> str:
        name = match.group(1)
        name_lower = name.lower()
        for member in guild.members:
            if (member.display_name.lower() == name_lower
                    or member.name.lower() == name_lower
                    or (getattr(member, 'global_name', None) and member.global_name.lower() == name_lower)):
                return f"<@{member.id}>"
        return match.group(0)

    # Replace each matched mention independently. The previous str.replace("@name", ...)
    # corrupted longer tokens (e.g. "@john" inside "@johnny" -> "<@111>ny").
    return mention_pattern.sub(_resolve, text)

@bot.event
async def on_message(message: discord.Message) -> None:
    # Only filter out *guild* messages from other channels. DMs (message.guild is None)
    # must still be handled below even when a channel is selected.
    if message.guild is not None and SELECT_CHANNEL_ID is not None and message.channel.id != SELECT_CHANNEL_ID:
        return

    if message.channel.id == SELECT_CHANNEL_ID or message.channel.id == MONITOR_CHANNEL_ID:
        _add_to_channel_messages(message)
        if message.author == bot.user:
            return
        await print_discord_msg(message)
        log.log_message(message, is_json=SAVE_AS_JSON)
    
    # when message is dm
    if message.guild is None and message.author is not None and message.content is not None:
        _add_to_channel_messages(message)
        if message.author == bot.user:
            return
        await print_discord_msg(message)

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message) -> None:
    if SELECT_CHANNEL_ID is not None and before.channel.id != SELECT_CHANNEL_ID:
        return
    if (before.content == after.content
            and before.attachments == after.attachments
            and before.embeds == after.embeds):
        return
    if before.author == bot.user:
        return
    if before.channel.id == SELECT_CHANNEL_ID or before.channel.id == MONITOR_CHANNEL_ID:
        await print_discord_msg(after, is_edit=True, before=before)
        log.log_message(before, after, is_edit=True, is_json=SAVE_AS_JSON)

@bot.event
async def on_message_delete(message: discord.Message) -> None:
    if SELECT_CHANNEL_ID is not None and message.channel.id != SELECT_CHANNEL_ID:
        return
    # Remove from channel_messages buffer
    if message.channel.id == SELECT_CHANNEL_ID or message.channel.id == MONITOR_CHANNEL_ID:
        ch_name = _esc(getattr(message.channel, 'name', 'DM'))
        author_name = _esc(message.author.name)
        deleted_at = message.created_at.strftime('%Y-%m-%d %H:%M:%S')
        if alert.check(message):
            print(f"[#EA9800 on #2B251C]\\[{ch_name}] {author_name}{'(bot)' if message.author.bot else ''} Deleted ({deleted_at}): {_esc(resolve_markup(message))}[/]")
        else:
            author_name_colored = f"[#B4009E]{author_name}[/]" if message.author.bot else author_name
            print(f"\\[{ch_name}] {author_name_colored}{'(bot)' if message.author.bot else ''} Deleted ({deleted_at}): {_esc(resolve_markup(message))}")
    log.log_message(message, is_delete=True, is_json=SAVE_AS_JSON)

async def main():
    asyncio.create_task(bot.start(settings.get("TOKEN", "OMG_NO_TOKEN")))
    await start_tui(process_command)

if __name__ == "__main__":
    asyncio.run(main())
