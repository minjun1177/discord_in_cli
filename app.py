from discord.ext import commands, tasks
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

bot = discord.Bot(intents=intents)

MONITOR_CHANNEL_ID = int(settings["CHANNEL_ID"])
USERNAME = settings.get("USERNAME", "Sparky")
ALLOW_MENTION_EVERYONE = settings.get("ALLOW_MENTION_EVERYONE", False)


async def watch_console():
    loop = asyncio.get_event_loop()
    
    await bot.wait_until_ready()
    channel = bot.get_channel(MONITOR_CHANNEL_ID)
    
    if not channel:
        print(f"[오류] ID가 {MONITOR_CHANNEL_ID}인 채널을 찾을 수 없습니다. ID를 확인해주세요.")
        return

    # print(f"[시스템] {channel.name}에서 ")

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
                await channel.send(f"{USERNAME}: {line}")
                print(f"[전송 완료] {USERNAME}: {line}")
            except Exception as e:
                print(f"[전송 실패] 메시지를 보내지 못했습니다: {e}")

@bot.event
async def on_ready():
    print(f"봇 로그인 완료: {bot.user}")
    asyncio.create_task(watch_console())

CUSTOM_EMOJI_RE = re.compile(r"<a?:([a-zA-Z0-9_]+):\d+>")


def resolve_markup(message):
    # clean_content handles user/channel/role mentions and @everyone/@here.
    content = message.clean_content
    # clean_content leaves custom emoji as-is; render them as :name:.
    return CUSTOM_EMOJI_RE.sub(r":\1:", content)


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.channel.id == MONITOR_CHANNEL_ID:
        print(f"[{message.channel.name}] {message.author.name}: {resolve_markup(message)}")
        
bot.run(settings.get("TOKEN", "OMG_NO_TOKEN"))