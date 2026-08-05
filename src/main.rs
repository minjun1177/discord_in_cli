//! discord_in_cli — Discord chat in your terminal, rewritten in Rust.

mod config;
mod console;
mod embed;
mod fmt;
mod handler;
mod image;
mod log;
mod state;

use serenity::cache::Settings as CacheSettings;
use serenity::client::ClientBuilder;
use serenity::model::gateway::GatewayIntents;
use std::sync::Mutex;

#[tokio::main]
async fn main() {
    let settings = match config::Settings::load() {
        Ok(s) => s,
        Err(e) => {
            eprintln!("{e}");
            std::process::exit(1);
        }
    };

    let state = state::State::new(settings.clone());

    let (tx, rx) = tokio::sync::mpsc::unbounded_channel::<String>();
    console::spawn_stdin_reader(tx);

    // Keep message contents in the cache so edit/delete events can display
    // the old message text (like py-cord's internal cache).
    let mut cache_settings = CacheSettings::default();
    cache_settings.max_messages = 2000;

    let intents = GatewayIntents::GUILDS
        | GatewayIntents::GUILD_MEMBERS
        | GatewayIntents::GUILD_MESSAGES
        | GatewayIntents::DIRECT_MESSAGES
        | GatewayIntents::MESSAGE_CONTENT;

    let handler = handler::Handler {
        state: state.clone(),
        rx: Mutex::new(Some(rx)),
        http_client: reqwest::Client::new(),
    };

    let mut client = match ClientBuilder::new(&settings.token, intents)
        .event_handler(handler)
        .cache_settings(cache_settings)
        .await
    {
        Ok(client) => client,
        Err(e) => {
            eprintln!("Failed to create client: {e}");
            std::process::exit(1);
        }
    };

    if let Err(why) = client.start().await {
        eprintln!("Client error: {why:?}");
    }
}
