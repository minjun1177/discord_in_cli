from discord.ext import commands, tasks
from datetime import timezone, datetime
import discord
import os
import json
import asyncio
import sys
import re

import log

"""
동작방식?
1. 디스코드 서버-채널 침투
2. 채널에서 메시지 감시
3. 출력
4. input 받기
5. 디스코드 채널에 메시지 보내기
6. 3-5 반복
7. :emart:

채널 선택 동작방식?
1. 서버에 침투
2. 서버의 모든 채널 출력
3. 채널 선택 - "/select <채널ID>" 입력
4. 선택한 채널에서 메시지 감시 - 모든 메시지 감시하되 채널ID가 선택한 채널ID와 일치하는 경우에만 출력
5. input 받기
6. 디스코드 채널에 메시지 보내기
7. 만약 "/exit" 입력 시 채널 선택 모드로 돌아가기
8. 4-7 반복
"""

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

global SELECT_CHANNEL_ID
SELECT_CHANNEL_ID = None

async def get_all_channels(target_guild: discord.Guild) -> None:
    bot_member = target_guild.me 
    if not bot_member:
        bot_member = target_guild.get_member(bot.user.id)

    print(f"=== Server: {target_guild.name} (ID: {target_guild.id}) ===")
    
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
    global SELECT_CHANNEL_ID
    loop = asyncio.get_event_loop()
    
    await bot.wait_until_ready()
    channel = bot.get_channel(SELECT_CHANNEL_ID if SELECT_CHANNEL_ID is not None else MONITOR_CHANNEL_ID)
    
    if not channel:
        print(f"[ERROR] Channel with ID {SELECT_CHANNEL_ID if SELECT_CHANNEL_ID is not None else MONITOR_CHANNEL_ID} not found. Please check the ID.")
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
                            print(f"[{msg.channel.name}] {msg.author.name}{'(bot)' if msg.author.bot else ''} ({msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}): {resolve_markup(msg)}")
                    except Exception as e:
                        print(f"[ERROR] Could not fetch messages: {e}")
                else:
                    print(f"[ERROR] Channel with ID {temp_id} not found.")
            else:
                print("[ERROR] Invalid command. Use '/select <channel_id>'.")
        elif line == "/exit":
            print("[SYSTEM] Exiting channel selection mode.")
            SELECT_CHANNEL_ID = None
            channel = bot.get_channel(MONITOR_CHANNEL_ID)
            await get_all_channels(bot.get_guild(SERVER_ID))
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
        
        if target_guild:
            await get_all_channels(target_guild)
        else:
            print(f"Error: Server with ID {SERVER_ID} not found. Please ensure the bot is invited to the server.")
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
        print(f"[{message.channel.name}] {message.author.name}{'(bot)' if message.author.bot else ''} ({message.created_at.strftime('%Y-%m-%d %H:%M:%S')}): {resolve_markup(message)}")
        log.log_message(message, is_json=SAVE_AS_JSON)

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if SELECT_CHANNEL_ID is not None and before.channel.id != SELECT_CHANNEL_ID:
        return
    if after.author.bot or before.content == after.content:
        return
    if before.channel.id == SELECT_CHANNEL_ID or before.channel.id == MONITOR_CHANNEL_ID:
        print(f"[{before.channel.name}] {after.author.name}{'(bot)' if after.author.bot else ''} Modified ({after.created_at.strftime('%Y-%m-%d %H:%M:%S')}) {before.content} -> {after.content}")
        log.log_message(before, after, is_edit=True, is_json=SAVE_AS_JSON)

@bot.event
async def on_message_delete(message: discord.Message):
    if SELECT_CHANNEL_ID is not None and message.channel.id != SELECT_CHANNEL_ID:
        return
    if message.author == bot.user:
        return
    if message.channel.id == SELECT_CHANNEL_ID or message.channel.id == MONITOR_CHANNEL_ID:
        print(f"[{message.channel.name}] {message.author.name}{'(bot)' if message.author.bot else ''} Deleted ({message.created_at.strftime('%Y-%m-%d %H:%M:%S')}): {resolve_markup(message)}")
        log.log_message(message, is_delete=True, is_json=SAVE_AS_JSON)

bot.run(settings.get("TOKEN", "OMG_NO_TOKEN"))