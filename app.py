from discord.ext import commands, tasks
from datetime import timezone, datetime
import discord
import os
import json
import asyncio
import sys
import re

import log
import src.alert

"""
동작방식?
1. 디스코드 서버-채널 침투
2. 채널에서 메시지 감시
3. 출력
4. input 받기
5. 디스코드 채널에 메시지 보내기
6. 3-5 반복
7. :emart:
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

async def watch_console() -> None:
    loop = asyncio.get_event_loop()
    
    await bot.wait_until_ready()
    channel = bot.get_channel(MONITOR_CHANNEL_ID)
    
    if not channel:
        print(f"[ERROR] Channel with ID {MONITOR_CHANNEL_ID} not found. Please check the ID.")
        return

    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        line = line.strip()
        
        if not line:
            continue
        
        if line == "status":
            print(f"[SYSTEM] Bot connected to '{channel.name}'")
        elif line == "stop":
            print("[SYSTEM] Stopping bot...")
            await bot.close()
            break
        elif "@everyone" in line and not ALLOW_MENTION_EVERYONE:
            print("[ERROR] '@everyone' is not allowed.")
        else:
            try:
                processed_line = convert_names_to_mentions(line, channel)

                await channel.send(f"{USERNAME}: {processed_line}")
                print(f"[TRANSMISSION SUCCEEDED] {USERNAME}: {line}")
            except Exception as e:
                print(f"[TRANSMISSION FAILED] Message can not be sent: {e}")

@bot.event
async def on_ready() -> None:
    print(f"봇 로그인 완료: {bot.user}")
    src.alert.init(bot)
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
    if message.author == bot.user:
        return

    if message.channel.id == MONITOR_CHANNEL_ID:
        print(f"[{message.channel.name}] {message.author.name} ({message.created_at.strftime('%Y-%m-%d %H:%M:%S')}): {resolve_markup(message)}")
        log.log_message(message, is_json=SAVE_AS_JSON)

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if after.author.bot or before.content == after.content:
        return
    if before.channel.id == MONITOR_CHANNEL_ID:
        print(f"[{before.channel.name}] {after.author.name} Modified ({after.created_at.strftime('%Y-%m-%d %H:%M:%S')}) {before.content} -> {after.content}")
        log.log_message(before, after, is_edit=True, is_json=SAVE_AS_JSON)

@bot.event
async def on_message_delete(message: discord.Message):
    if message.author == bot.user:
        return
    if message.channel.id == MONITOR_CHANNEL_ID:
        print(f"[{message.channel.name}] {message.author.name} Deleted ({message.created_at.strftime('%Y-%m-%d %H:%M:%S')}): {resolve_markup(message)}")
        log.log_message(message, is_delete=True, is_json=SAVE_AS_JSON)

bot.run(settings.get("TOKEN", "OMG_NO_TOKEN"))