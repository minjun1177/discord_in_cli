//! settings.json configuration loading.
//!
//! Mirrors the original Python implementation's settings keys (see
//! `settings.inc.json`). All IDs may be given as strings or numbers.

use serde::de::{Deserializer, Error as DeError};
use serde::Deserialize;
use std::fs;

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub struct Settings {
    #[serde(default, deserialize_with = "de_opt_u64")]
    pub server_id: Option<u64>,
    #[serde(deserialize_with = "de_u64")]
    pub channel_id: u64,
    pub token: String,
    #[serde(default)]
    pub allow_mention_everyone: bool,
    #[serde(default = "default_true")]
    pub save_messages: bool,
    #[serde(default)]
    pub save_as_json: bool,
    #[serde(default = "default_save_filename")]
    pub save_filename: String,
    #[serde(default = "default_fetch_limit")]
    pub fetch_history_limit: u64,
    #[serde(rename = "EMBED_VIEW_default", default)]
    pub embed_view_default: bool,
    #[serde(rename = "IMG_VIEW_default", default)]
    pub img_view_default: bool,
    #[serde(default = "default_msg_history_max")]
    pub msg_history_max: usize,
    #[serde(default = "default_username")]
    pub username: String,
    #[serde(default, deserialize_with = "de_u64_vec")]
    pub watch_id: Vec<u64>,
}

fn default_true() -> bool {
    true
}

fn default_save_filename() -> String {
    "messages.log".to_string()
}

fn default_fetch_limit() -> u64 {
    10
}

fn default_msg_history_max() -> usize {
    50
}

fn default_username() -> String {
    "Sparky".to_string()
}

/// Accepts a JSON string or a number for snowflake IDs.
#[derive(Deserialize)]
#[serde(untagged)]
enum U64Repr {
    Str(String),
    Num(u64),
}

impl U64Repr {
    fn into_u64<E: DeError>(self) -> Result<u64, E> {
        match self {
            U64Repr::Num(n) => Ok(n),
            U64Repr::Str(s) => s.parse().map_err(E::custom),
        }
    }
}

fn de_u64<'de, D: Deserializer<'de>>(d: D) -> Result<u64, D::Error> {
    U64Repr::deserialize(d)?.into_u64()
}

fn de_opt_u64<'de, D: Deserializer<'de>>(d: D) -> Result<Option<u64>, D::Error> {
    let opt = Option::<U64Repr>::deserialize(d)?;
    opt.map(U64Repr::into_u64).transpose()
}

#[derive(Deserialize)]
#[serde(untagged)]
enum U64VecRepr {
    List(Vec<U64Repr>),
    One(U64Repr),
}

fn de_u64_vec<'de, D: Deserializer<'de>>(d: D) -> Result<Vec<u64>, D::Error> {
    match U64VecRepr::deserialize(d)? {
        U64VecRepr::List(items) => items.into_iter().map(U64Repr::into_u64).collect(),
        U64VecRepr::One(item) => Ok(vec![item.into_u64()?]),
    }
}

impl Settings {
    /// Load `settings.json` from the current working directory.
    pub fn load() -> Result<Self, String> {
        let raw = fs::read_to_string("settings.json")
            .map_err(|e| format!("Failed to read settings.json: {e}"))?;
        serde_json::from_str(&raw).map_err(|e| format!("Failed to parse settings.json: {e}"))
    }
}
