import discord
import json

with open("settings.json", "r") as f:
    settings = json.load(f)

watch_ids_setting = settings.get("WATCH_ID", [])
if isinstance(watch_ids_setting, list):
    WATCH_IDS = []
    for x in watch_ids_setting:
        try:
            WATCH_IDS.append(int(x))
        except (ValueError, TypeError):
            pass
elif isinstance(watch_ids_setting, (int, str)):
    try:
        WATCH_IDS = [int(watch_ids_setting)]
    except (ValueError, TypeError):
        WATCH_IDS = []
else:
    WATCH_IDS = []

def init(bot: discord.Bot) -> None:
    if bot.user and bot.user.id not in WATCH_IDS:
        WATCH_IDS.append(bot.user.id)
    return

def check(msg: discord.Message) -> bool:
    try:
        mentioned_ids = set(msg.raw_mentions)
        for m in msg.mentions:
            mentioned_ids.add(m.id)
        
        for id in WATCH_IDS:
            if id in mentioned_ids:
                return True
        return False
    except Exception as e:
        print(f"Error in check function: {e}")
        return False