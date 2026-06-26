import discord
import json

with open("settings.json", "r") as f:
    settings = json.load(f)

WATCH_IDS = list(settings.get("WATCH_ID"))

def init(bot: discord.Bot) -> None:
    WATCH_IDS.append(bot.user.id)
    return

def check(msg: discord.Message) -> bool:
    mentions = msg.raw_mentions
    for id in WATCH_IDS():
        if mentions.count(int(id)) > 0:
            return True
    return False
