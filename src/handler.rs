//! Gateway event handlers (the Rust counterpart of `app.py`'s bot events).

use crate::fmt::{channel_name, print_deleted, print_discord_msg};
use crate::state::State;
use serenity::async_trait;
use serenity::client::{Context, EventHandler};
use serenity::gateway::ActivityData;
use serenity::model::channel::Message;
use serenity::model::event::MessageUpdateEvent;
use serenity::model::gateway::Ready;
use serenity::model::id::{ChannelId, GuildId, MessageId};
use serenity::model::user::OnlineStatus;
use std::sync::{Arc, Mutex};
use tokio::sync::mpsc::UnboundedReceiver;

pub struct Handler {
    pub state: Arc<State>,
    /// Console stdin receiver, taken once when the bot is ready.
    pub rx: Mutex<Option<UnboundedReceiver<String>>>,
    pub http_client: reqwest::Client,
}

/// Two messages are considered "unchanged" if content, attachment URLs, and
/// embed counts are identical (approximation of the Python comparison).
fn messages_equal_enough(before: &Message, after: &Message) -> bool {
    before.content == after.content
        && before.attachments.len() == after.attachments.len()
        && before
            .attachments
            .iter()
            .zip(&after.attachments)
            .all(|(a, b)| a.url == b.url)
        && before.embeds.len() == after.embeds.len()
}

#[async_trait]
impl EventHandler for Handler {
    async fn ready(&self, ctx: Context, ready: Ready) {
        println!("Logged in as: {}", ready.user.name);

        let guild_id = match self.state.settings.server_id {
            Some(id) => GuildId::new(id),
            None => {
                println!("Error: SERVER_ID is not set in settings.json. Please provide a valid server ID.");
                std::process::exit(1);
            }
        };

        ctx.set_presence(
            Some(ActivityData::playing(format!(
                "Logined as {}",
                self.state.settings.username
            ))),
            OnlineStatus::Online,
        );

        self.state
            .bot_user_id
            .lock()
            .unwrap()
            .replace(ready.user.id);
        {
            let mut watch = self.state.watch_ids.lock().unwrap();
            if !watch.contains(&ready.user.id.get()) {
                watch.push(ready.user.id.get());
            }
        }

        if let Err(e) =
            crate::console::get_all_channels(&ctx.http, &ctx.cache, guild_id, &self.state).await
        {
            println!("Error: Server with ID {guild_id} not found. Please ensure the bot is invited to the server. ({e})");
        }

        if let Some(rx) = self.rx.lock().unwrap().take() {
            let http = ctx.http.clone();
            let cache = ctx.cache.clone();
            let shard = ctx.shard.clone();
            let state = self.state.clone();
            let client = self.http_client.clone();
            tokio::spawn(async move {
                crate::console::run_console(http, cache, shard, state, client, rx).await;
            });
        }
    }

    async fn message(&self, ctx: Context, new_message: Message) {
        let selected = *self.state.selected_channel.lock().unwrap();
        if let Some(sel) = selected {
            if new_message.channel_id != sel {
                return;
            }
        }
        let monitor = ChannelId::new(self.state.settings.channel_id);
        let target = selected.unwrap_or(monitor);
        if new_message.channel_id != target && new_message.channel_id != monitor {
            return;
        }
        self.state
            .add_to_channel_messages(Arc::new(new_message.clone()));
        if Some(new_message.author.id) == self.state.bot_user_id() {
            return;
        }
        print_discord_msg(
            &ctx.cache,
            &self.state,
            &self.http_client,
            &new_message,
            false,
            None,
        )
        .await;
        crate::log::log_message(&self.state, &ctx.cache, &new_message, None, false, false);
    }

    async fn message_update(
        &self,
        ctx: Context,
        old_if_available: Option<Message>,
        new: Option<Message>,
        event: MessageUpdateEvent,
    ) {
        let selected = *self.state.selected_channel.lock().unwrap();
        if let Some(sel) = selected {
            if event.channel_id != sel {
                return;
            }
        }
        let monitor = ChannelId::new(self.state.settings.channel_id);
        let target = selected.unwrap_or(monitor);
        if event.channel_id != target && event.channel_id != monitor {
            return;
        }
        if let Some(author) = &event.author {
            if Some(author.id) == self.state.bot_user_id() {
                return;
            }
        }

        let before: Option<Message> = self
            .state
            .find_message(event.id)
            .map(|m| (*m).clone())
            .or_else(|| old_if_available);
        let after: Option<Message> = new;

        if let (Some(b), Some(a)) = (&before, &after) {
            if messages_equal_enough(b, a) {
                return;
            }
        }

        match after {
            Some(after_msg) => {
                print_discord_msg(
                    &ctx.cache,
                    &self.state,
                    &self.http_client,
                    &after_msg,
                    true,
                    before.as_ref(),
                )
                .await;
                crate::log::log_message(
                    &self.state,
                    &ctx.cache,
                    before.as_ref().unwrap_or(&after_msg),
                    Some(&after_msg),
                    true,
                    false,
                );
            }
            None => {
                // Cache miss — fall back to the raw event fields.
                let ch_name = channel_name(&ctx.cache, event.channel_id);
                let before_content = before
                    .map(|m| m.content)
                    .unwrap_or_else(|| "(unknown)".to_string());
                let after_content = event
                    .content
                    .clone()
                    .unwrap_or_else(|| "(unknown)".to_string());
                println!("[{ch_name}] Modified: {before_content} -> {after_content}");
            }
        }
    }

    async fn message_delete(
        &self,
        ctx: Context,
        channel_id: ChannelId,
        deleted_message_id: MessageId,
        _guild_id: Option<GuildId>,
    ) {
        let selected = *self.state.selected_channel.lock().unwrap();
        if let Some(sel) = selected {
            if channel_id != sel {
                return;
            }
        }
        let msg = self
            .state
            .find_message(deleted_message_id)
            .map(|m| (*m).clone())
            .or_else(|| {
                ctx.cache
                    .message(channel_id, deleted_message_id)
                    .map(|m| (*m).clone())
            });
        self.state.remove_from_channel_messages(deleted_message_id);
        if let Some(m) = &msg {
            if Some(m.author.id) == self.state.bot_user_id() {
                return;
            }
        }
        let monitor = ChannelId::new(self.state.settings.channel_id);
        let target = selected.unwrap_or(monitor);
        if channel_id != target && channel_id != monitor {
            return;
        }
        match msg {
            Some(m) => {
                print_deleted(&ctx.cache, &self.state, &m);
                crate::log::log_message(&self.state, &ctx.cache, &m, None, false, true);
            }
            None => {
                println!(
                    "[{}] Deleted (message id {deleted_message_id})",
                    channel_name(&ctx.cache, channel_id)
                );
            }
        }
    }
}
