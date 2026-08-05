//! Shared runtime state, shared between the gateway event handlers and the
//! console command loop.

use crate::config::Settings;
use serenity::model::channel::Message;
use serenity::model::id::{ChannelId, MessageId, UserId};
use std::collections::VecDeque;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

pub struct State {
    pub settings: Settings,
    /// The channel currently selected with `/select` (None = monitor channel).
    pub selected_channel: Mutex<Option<ChannelId>>,
    /// Ring buffer of recent messages in the monitored/selected channel,
    /// oldest first, capped at `MSG_HISTORY_MAX`.
    pub channel_messages: Mutex<VecDeque<Arc<Message>>>,
    pub embed_view: AtomicBool,
    pub img_view: AtomicBool,
    /// Alert (mention) watch list; the bot's own ID is appended at startup.
    pub watch_ids: Mutex<Vec<u64>>,
    pub bot_user_id: Mutex<Option<UserId>>,
}

impl State {
    pub fn new(settings: Settings) -> Arc<Self> {
        Arc::new(Self {
            embed_view: AtomicBool::new(settings.embed_view_default),
            img_view: AtomicBool::new(settings.img_view_default),
            selected_channel: Mutex::new(None),
            channel_messages: Mutex::new(VecDeque::new()),
            watch_ids: Mutex::new(settings.watch_id.clone()),
            bot_user_id: Mutex::new(None),
            settings,
        })
    }

    pub fn bot_user_id(&self) -> Option<UserId> {
        *self.bot_user_id.lock().unwrap()
    }

    pub fn add_to_channel_messages(&self, msg: Arc<Message>) {
        let mut buf = self.channel_messages.lock().unwrap();
        if buf.iter().any(|m| m.id == msg.id) {
            return;
        }
        buf.push_back(msg);
        let max = self.settings.msg_history_max.max(1);
        while buf.len() > max {
            buf.pop_front();
        }
    }

    pub fn remove_from_channel_messages(&self, id: MessageId) {
        self.channel_messages.lock().unwrap().retain(|m| m.id != id);
    }

    pub fn clear_channel_messages(&self) {
        self.channel_messages.lock().unwrap().clear();
    }

    pub fn find_message(&self, id: MessageId) -> Option<Arc<Message>> {
        self.channel_messages
            .lock()
            .unwrap()
            .iter()
            .find(|m| m.id == id)
            .cloned()
    }

    /// Alert check: `@everyone`/`@here` or a mention of a watched user.
    pub fn is_watched(&self, msg: &Message) -> bool {
        let watch = self.watch_ids.lock().unwrap();
        if msg.mention_everyone {
            return true;
        }
        msg.mentions.iter().any(|u| watch.contains(&u.id.get()))
    }
}

/// Convenience: the currently active channel id (selected or monitor).
pub fn active_channel_id(state: &State) -> ChannelId {
    match *state.selected_channel.lock().unwrap() {
        Some(id) => id,
        None => ChannelId::new(state.settings.channel_id),
    }
}

/// Helper to read an atomic toggle.
pub fn flag(atomic: &AtomicBool) -> bool {
    atomic.load(Ordering::Relaxed)
}
