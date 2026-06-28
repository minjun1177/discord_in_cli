from discord.ext import commands, tasks
from datetime import timezone, datetime
import discord
import os
import json
import asyncio
import sys
import re
from rich import print

import src.log as log
import src.alert as alert
import src.embed_render as embed_render
import src.image_render as image_render

with open("settings.json", "r") as f:
    settings = json.load(f)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

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

global SELECT_CHANNEL_ID
SELECT_CHANNEL_ID = None

global embed_view_enabled
embed_view_enabled = EMBED_VIEW_DEF

global img_view_enabled
img_view_enabled = settings.get("IMG_VIEW_default", False)

async def print_discord_msg(msg, is_edit=False, before=None):
    global embed_view_enabled, img_view_enabled
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
        hidden_texts.extend([f"Embed {i+1} was hide" for i in range(embed_count)])
    if not img_view_enabled and img_count > 0:
        hidden_texts.extend([f"Image {i+1} was hide" for i in range(img_count)])
        
    hide_main_text = not has_content and len(hidden_texts) > 0
    
    author_name_colored = f"[#B4009E]{msg.author.name}[/]" if msg.author.bot else msg.author.name
    bot_suffix = "(bot)" if msg.author.bot else ""
    time_str = msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
    
    ch_name = before.channel.name if is_edit and before else msg.channel.name
    
    if alert.check(msg):
        prefix = f"[#EA9800 on #2B251C]\\[{ch_name}] {msg.author.name}{bot_suffix}"
        suffix = "[/]"
    else:
        prefix = f"\\[{ch_name}] {author_name_colored}{bot_suffix}"
        suffix = ""
        
    if is_edit and before:
        action = " Modified"
        if hide_main_text:
            text = f"\\[{', '.join(hidden_texts)}]"
        else:
            text = f"{before.content} -> {msg.content}"
    else:
        action = ""
        if hide_main_text:
            text = f"\\[{', '.join(hidden_texts)}]"
        else:
            text = resolve_markup(msg)
            
    if action:
        print(f"{prefix}{action} ({time_str}) {text}{suffix}")
    else:
        print(f"{prefix} ({time_str}): {text}{suffix}")
        
    if msg.embeds or msg.components:
        if embed_view_enabled:
            embed_render.render_embeds_and_components(msg)
        elif embed_count > 0 and has_content:
            print("  [bold dim]\\[Embed][/]")
            
    if img_count > 0:
        if img_view_enabled:
            await image_render.render_images_async(msg)
        elif has_content:
            print(f"  [bold dim]\\[Image {img_count} was hide][/]")

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

async def watch_console() -> None:
    global SELECT_CHANNEL_ID, embed_view_enabled, img_view_enabled
    loop = asyncio.get_event_loop()
    
    await bot.wait_until_ready()
    channel = bot.get_channel(SELECT_CHANNEL_ID if SELECT_CHANNEL_ID else MONITOR_CHANNEL_ID)
    
    if not channel:
        print(f"[ERROR] Channel with ID {SELECT_CHANNEL_ID if SELECT_CHANNEL_ID else MONITOR_CHANNEL_ID} not found. Please check the ID.")
        return

    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        line = line.strip()
        
        if not line:
            continue
        
        if line == "/status":
            print(f"[SYSTEM] Bot connected to '{channel.name if channel else 'Unknown'}' (ID: {channel.id if channel else 'Unknown'}) in server '{channel.guild.name if channel and channel.guild else 'Unknown'}' (ID: {channel.guild.id if channel and channel.guild else 'Unknown'}).")
        elif line == "/stop":
            print("[SYSTEM] Stopping bot...")
            await bot.close()
            break
        elif "@everyone" in line and not ALLOW_MENTION_EVERYONE:
            print("[ERROR] '@everyone' is not allowed.")
        elif line.startswith("/select"):
            parts = line.split()
            if len(parts) == 2 and parts[1].isdigit():
                temp_id = int(parts[1])
                selected_channel = bot.get_channel(temp_id)
                if selected_channel:
                    SELECT_CHANNEL_ID = temp_id
                    channel = selected_channel
                    print(f"[SYSTEM] Selected channel ID: {SELECT_CHANNEL_ID} ('{selected_channel.name}')")
                    print(f"[SYSTEM] Fetching last {FETCH_HISTORY_LIMIT} messages from '{selected_channel.name}'...")
                    try:
                        messages = [msg async for msg in selected_channel.history(limit=FETCH_HISTORY_LIMIT)]
                        for msg in reversed(messages):
                            await print_discord_msg(msg)
                    except Exception as e:
                        print(f"[ERROR] Could not fetch messages: {e}")
                else:
                    print(f"[ERROR] Channel with ID {temp_id} not found.")
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
                        for msg in reversed(messages):
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
                        for msg in reversed(messages):
                            await print_discord_msg(msg)
                    except Exception as e:
                        print(f"[ERROR] Could not refresh messages: {e}")
            else:
                print("[ERROR] Usage: /img open or /img close")
        elif line == "/exit":
            print("[SYSTEM] Exiting channel selection mode.")
            SELECT_CHANNEL_ID = None
            channel = bot.get_channel(MONITOR_CHANNEL_ID)
            if SERVER_ID is None:
                print("[ERROR] SERVER_ID is not set in settings.json. Please provide a valid server ID.")
                return
            await get_all_channels(bot.get_guild(SERVER_ID))
        elif line.startswith("/"):
            print(f"[ERROR] Unknown command: {line}")
        else:
            if SELECT_CHANNEL_ID is None:
                print("[SYSTEM] No channel selected. Please use '/select <channel_id>' to select a channel for monitoring and sending messages.")
            else:
                try:
                    processed_line = convert_names_to_mentions(line, channel)

                    await channel.send(f"{USERNAME}: {processed_line}")
                    print(f"{USERNAME}: {line}")
                except Exception as e:
                    print(f"[TRANSMISSION FAILED] Message can not be sent: {e}")

@bot.event
async def on_ready() -> None:
    print(f"Logged in as: {bot.user}")
    
    target_guild = None
    if SERVER_ID:
        target_guild = bot.get_guild(SERVER_ID)
        game = discord.Game(f"Logined as {USERNAME}")
        await bot.change_presence(status=discord.Status.online, activity=game)

        if target_guild:
            await get_all_channels(target_guild)
        else:
            print(f"Error: Server with ID {SERVER_ID} not found. Please ensure the bot is invited to the server.")
    else:
        print("Error: SERVER_ID is not set in settings.json. Please provide a valid server ID.")
        raise ValueError("Error: SERVER_ID is not set in settings.json. Please provide a valid server ID.")
    alert.init(bot)
    asyncio.create_task(watch_console())

CUSTOM_EMOJI_RE = re.compile(r"<a?:([a-zA-Z0-9_]+):\d+>")


def resolve_markup(message: discord.Message) -> str:
    # clean_content handles user/channel/role mentions and @everyone/@here.
    content = message.clean_content
    # clean_content leaves custom emoji as-is; render them as :name:.
    return CUSTOM_EMOJI_RE.sub(r":\1:", content)

def convert_names_to_mentions(text: str, channel: discord.abc.Messageable) -> str:
    mention_pattern = re.compile(r"@([^\s]+)")
    matches = mention_pattern.findall(text)
    
    if isinstance(channel, discord.TextChannel):
        guild = channel.guild
        
        for name in matches:
            name_lower = name.lower()
            target_member = None
            
            for member in guild.members:
                if member.display_name.lower() == name_lower:
                    target_member = member
                    break
                elif member.name.lower() == name_lower:
                    target_member = member
                    break
                elif getattr(member, 'global_name', None) and member.global_name.lower() == name_lower:
                    target_member = member
                    break
            
            if target_member:
                text = text.replace(f"@{name}", f"<@{target_member.id}>")
                
    return text

@bot.event
async def on_message(message: discord.Message):
    if SELECT_CHANNEL_ID is not None and message.channel.id != SELECT_CHANNEL_ID:
        return
    if message.author == bot.user:
        return

    if message.channel.id == SELECT_CHANNEL_ID or message.channel.id == MONITOR_CHANNEL_ID:
        await print_discord_msg(message)
        log.log_message(message, is_json=SAVE_AS_JSON)

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if SELECT_CHANNEL_ID is not None and before.channel.id != SELECT_CHANNEL_ID:
        return
    if (before.content == after.content
            and before.attachments == after.attachments
            and before.embeds == after.embeds):
        return
    if before.channel.id == SELECT_CHANNEL_ID or before.channel.id == MONITOR_CHANNEL_ID:
        await print_discord_msg(after, is_edit=True, before=before)
        log.log_message(before, after, is_edit=True, is_json=SAVE_AS_JSON)

@bot.event
async def on_message_delete(message: discord.Message):
    if SELECT_CHANNEL_ID is not None and message.channel.id != SELECT_CHANNEL_ID:
        return
    if message.author == bot.user:
        return
    if message.channel.id == SELECT_CHANNEL_ID or message.channel.id == MONITOR_CHANNEL_ID:
        if alert.check(message):
            print(f"[#EA9800 on #2B251C]\\[{message.channel.name}] {message.author.name}{'(bot)' if message.author.bot else ''} Deleted ({message.created_at.strftime('%Y-%m-%d %H:%M:%S')}): {resolve_markup(message)}[/]")
        else:
            author_name = f"[#B4009E]{message.author.name}[/]" if message.author.bot else message.author.name
            print(f"\\[{message.channel.name}] {author_name}{'(bot)' if message.author.bot else ''} Deleted ({message.created_at.strftime('%Y-%m-%d %H:%M:%S')}): {resolve_markup(message)}")
        log.log_message(message, is_delete=True, is_json=SAVE_AS_JSON)

bot.run(settings.get("TOKEN", "OMG_NO_TOKEN"))