from discord.ext import commands, tasks
from datetime import timezone, datetime
import discord
import os
import json
import asyncio
import sys
import re

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
        print(f"[오류] ID가 {MONITOR_CHANNEL_ID}인 채널을 찾을 수 없습니다. ID를 확인해주세요.")
        return

    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        line = line.strip()
        
        if not line:
            continue
        
        if line == "status":
            print(f"[시스템] 현재 '{channel.name}' 연결되어 있습니다.")
        elif line == "stop":
            print("봇을 종료합니다...")
            await bot.close()
            break
        elif "@everyone" in line and not ALLOW_MENTION_EVERYONE:
            print("[오류] @everyone 언급은 허용되지 않습니다.")
        else:
            try:
                processed_line = convert_names_to_mentions(line, channel)

                await channel.send(f"{USERNAME}: {processed_line}")
                print(f"[전송 완료] {USERNAME}: {line}")
            except Exception as e:
                print(f"[전송 실패] 메시지를 보내지 못했습니다: {e}")

@bot.event
async def on_ready() -> None:
    print(f"봇 로그인 완료: {bot.user}")
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

def log_message(message: discord.Message, after: discord.Message | None = None, is_edit: bool = False, is_json: bool = False) -> None:
    if not SAVE_MESSAGES:
        return
        
    guild_name = message.guild.name if message.guild else "Direct Message"
    guild_id = message.guild.id if message.guild else None

    if is_edit:
        if is_json:
            log_data = {
                "type": "edit",
                "message_id": message.id,
                "timestamp": after.created_at.isoformat(),
                "server": {
                    "id": guild_id,
                    "name": guild_name
                },
                "channel": {
                    "id": message.channel.id,
                    "name": message.channel.name if hasattr(message.channel, 'name') else "DM"
                },
                "author": {
                    "id": message.author.id,
                    "name": message.author.name,
                    "is_bot": message.author.bot
                },
                "content_before": resolve_markup(message),
                "content_after": resolve_markup(after),
                "attachments_before": [attachment.url for attachment in message.attachments],
                "attachments_after": [attachment.url for attachment in after.attachments]
            }
            
            with open(SAVE_FILENAME, "a", encoding="utf-8") as f:
                json.dump(log_data, f, ensure_ascii=False)
                f.write("\n")
        else:
            time_str = after.created_at.strftime("%Y-%m-%d %H:%M:%S")
            
            attachment_info_before = f" (첨부파일: {len(message.attachments)}개)" if message.attachments else ""
            attachment_info_after = f" (첨부파일: {len(after.attachments)}개)" if after.attachments else ""
            
            log_line = f"[{time_str}] [{guild_name} / {message.channel.name}] {message.author.name}({message.author.id}) 수정됨: {resolve_markup(message)}{attachment_info_before} -> {resolve_markup(after)}{attachment_info_after}\n"
            
            with open(SAVE_FILENAME, "a", encoding="utf-8") as f:
                f.write(log_line)

    if is_json:
        log_data = {
            "type": "message",
            "message_id": message.id,
            "timestamp": message.created_at.isoformat(),
            "server": {
                "id": guild_id,
                "name": guild_name
            },
            "channel": {
                "id": message.channel.id,
                "name": message.channel.name if hasattr(message.channel, 'name') else "DM"
            },
            "author": {
                "id": message.author.id,
                "name": message.author.name,
                "is_bot": message.author.bot
            },
            "content": resolve_markup(message),
            "attachments": [attachment.url for attachment in message.attachments]
        }
        
        with open(SAVE_FILENAME, "a", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False)
            f.write("\n")
            
    else:
        time_str = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
        
        attachment_info = f" (첨부파일: {len(message.attachments)}개)" if message.attachments else ""
        
        log_line = f"[{time_str}] [{guild_name} / {message.channel.name}] {message.author.name}({message.author.id}): {resolve_markup(message)}{attachment_info}\n"
        
        with open(SAVE_FILENAME, "a", encoding="utf-8") as f:
            f.write(log_line)

@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    if message.channel.id == MONITOR_CHANNEL_ID:
        print(f"[{message.channel.name}] {message.author.name} ({message.created_at.strftime('%Y-%m-%d %H:%M:%S')}): {resolve_markup(message)}")
        log_message(message, is_json=SAVE_AS_JSON)

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if after.author.bot or before.content == after.content:
        return
    if before.channel.id == MONITOR_CHANNEL_ID:
        print(f"[{before.channel.name}] {after.author.name} 수정됨 ({after.created_at.strftime('%Y-%m-%d %H:%M:%S')}) {before.content} -> {after.content}")
        log_message(before, after, is_edit=True, is_json=SAVE_AS_JSON)

@bot.event
async def on_message_delete(message: discord.Message):
    if message.author == bot.user:
        return
    if message.channel.id == MONITOR_CHANNEL_ID:
        print(f"[{message.channel.name}] {message.author.name} Deleted ({message.created_at.strftime('%Y-%m-%d %H:%M:%S')}): {resolve_markup(message)}")

bot.run(settings.get("TOKEN", "OMG_NO_TOKEN"))