import discord, json, re

with open("settings.json", "r") as f:
    settings = json.load(f)

CUSTOM_EMOJI_RE = re.compile(r"<a?:([a-zA-Z0-9_]+):\d+>")

MONITOR_CHANNEL_ID = int(settings["CHANNEL_ID"])
USERNAME = settings.get("USERNAME", "Sparky")
ALLOW_MENTION_EVERYONE = settings.get("ALLOW_MENTION_EVERYONE", False)
SAVE_MESSAGES = settings.get("SAVE_MESSAGES", True)
SAVE_FILENAME = settings.get("SAVE_FILENAME", "messages.log")
SAVE_AS_JSON = settings.get("SAVE_AS_JSON", False)

def resolve_markup(message: discord.Message) -> str:
    # clean_content handles user/channel/role mentions and @everyone/@here.
    content = message.clean_content
    # clean_content leaves custom emoji as-is; render them as :name:.
    return CUSTOM_EMOJI_RE.sub(r":\1:", content)

def log_message(message: discord.Message, after: discord.Message | None = None, is_edit: bool = False, is_delete: bool = False, is_json: bool = False) -> None:
    if not SAVE_MESSAGES:
        return
        
    guild_name = message.guild.name if message.guild else "Direct Message"
    guild_id = message.guild.id if message.guild else None

    if is_delete:
        if is_json:
            log_data = {
                "type": "delete",
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
                "content_before": resolve_markup(message),
                "attachments": [attachment.url for attachment in message.attachments]
            }
            
            with open(SAVE_FILENAME, "a", encoding="utf-8") as f:
                json.dump(log_data, f, ensure_ascii=False)
                f.write("\n")
        else:
            time_str = message.created_at.strftime("%Y-%m-%d %H:%M:%S")

            attachment_info = f" (첨부파일: {len(message.attachments)}개)" if message.attachments else ""

            log_line = f"[{time_str}] [{guild_name} / {message.channel.name}] {message.author.name}({message.author.id}) Deleted: {resolve_markup(message)}{attachment_info}\n"
            
            with open(SAVE_FILENAME, "a", encoding="utf-8") as f:
                f.write(log_line)

    elif is_edit:
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

    else:
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