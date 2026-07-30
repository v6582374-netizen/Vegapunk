use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};

use reqwest::header::{ACCEPT, AUTHORIZATION, CONTENT_TYPE};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::models::auth::{AuthProfile, AuthSession};
use crate::services::auth::{build_auth_start_url, generate_code_verifier, pkce_challenge};
use crate::services::ConfigManager;

const DEFAULT_AUTH_API_BASE: &str = "https://skills-market-api.guardssl.info/api/v1";

#[derive(Debug, Clone)]
struct PendingAuthState {
    code_verifier: String,
    nonce: String,
}

static PENDING_AUTH: OnceLock<Mutex<HashMap<String, PendingAuthState>>> = OnceLock::new();

fn pending_auth_states() -> &'static Mutex<HashMap<String, PendingAuthState>> {
    PENDING_AUTH.get_or_init(|| Mutex::new(HashMap::new()))
}

fn auth_api_base_url() -> String {
    std::env::var("SKILLS_MARKET_API_BASE").unwrap_or_else(|_| DEFAULT_AUTH_API_BASE.to_string())
}

fn build_auth_api_url(base_url: &str, path: &str) -> Result<reqwest::Url, String> {
    let base = base_url.trim_end_matches('/');
    let url = format!("{base}{path}");
    reqwest::Url::parse(&url).map_err(|e| format!("Invalid auth url: {e}"))
}

#[derive(Debug, Deserialize)]
struct AuthStartResponse {
    auth_url: String,
}

#[derive(Debug, Deserialize)]
struct AuthExchangeResponse {
    access_token: String,
    refresh_token: String,
    #[allow(dead_code)]
    access_expires_at: Option<u64>,
    #[allow(dead_code)]
    refresh_expires_at: Option<u64>,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct AuthMeResponse {
    pub user_id: String,
    pub provider: Option<String>,
    pub username: Option<String>,
    pub avatar_url: Option<String>,
    pub email: Option<String>,
}

#[derive(Debug, Deserialize)]
struct AuthRefreshResponse {
    access_token: String,
    #[allow(dead_code)]
    access_expires_at: Option<u64>,
}

async fn refresh_access_token(
    client: &Client,
    base_url: &str,
    refresh_token: &str,
) -> Result<String, String> {
    let refresh_url = build_auth_api_url(base_url, "/auth/refresh")?;
    let refresh_response = client
        .post(refresh_url)
        .header(CONTENT_TYPE, "application/json")
        .header(ACCEPT, "application/json")
        .json(&serde_json::json!({
            "refresh_token": refresh_token,
        }))
        .send()
        .await
        .map_err(|e| format!("Failed to refresh auth token: {e}"))?;

    if !refresh_response.status().is_success() {
        return Err(format!(
            "Auth refresh failed: HTTP {}",
            refresh_response.status()
        ));
    }

    let refresh_payload = refresh_response
        .json::<AuthRefreshResponse>()
        .await
        .map_err(|e| format!("Failed to parse auth refresh response: {e}"))?;

    Ok(refresh_payload.access_token)
}

#[derive(Debug, Serialize)]
pub struct AuthStartResult {
    pub auth_url: String,
    pub state: String,
}

pub fn save_auth_session(session: AuthSession) -> Result<(), String> {
    let manager = ConfigManager::new();
    let mut config = manager.load()?;
    config.auth_session = Some(session);
    manager.save(&config)
}

fn store_pending_state(state: String, code_verifier: String, nonce: String) {
    if let Ok(mut guard) = pending_auth_states().lock() {
        guard.insert(
            state,
            PendingAuthState {
                code_verifier,
                nonce,
            },
        );
    }
}

fn take_pending_state(state: &str) -> Option<PendingAuthState> {
    pending_auth_states()
        .lock()
        .ok()
        .and_then(|mut guard| guard.remove(state))
}

#[cfg(test)]
fn has_pending_state(state: &str) -> bool {
    pending_auth_states()
        .lock()
        .map(|guard| guard.contains_key(state))
        .unwrap_or(false)
}

#[cfg(test)]
fn set_pending_state(state: &str, code_verifier: &str, nonce: &str) {
    store_pending_state(
        state.to_string(),
        code_verifier.to_string(),
        nonce.to_string(),
    );
}

async fn start_oauth_auth(
    provider: &str,
    debug: Option<bool>,
    locale: Option<String>,
) -> Result<AuthStartResult, String> {
    let state = if debug.unwrap_or(false) {
        format!("debug-{}", Uuid::new_v4().simple())
    } else {
        Uuid::new_v4().simple().to_string()
    };
    let code_verifier = generate_code_verifier();
    let code_challenge = pkce_challenge(&code_verifier);
    let nonce = Uuid::new_v4().simple().to_string();
    let base_url = auth_api_base_url();
    let url = build_auth_start_url(
        &base_url,
        provider,
        &state,
        &code_challenge,
        &nonce,
        locale.as_deref(),
    )?;

    let client = Client::new();
    let response = client
        .get(url)
        .header(ACCEPT, "application/json")
        .send()
        .await
        .map_err(|e| format!("Failed to start auth: {e}"))?;

    if !response.status().is_success() {
        return Err(format!("Auth start failed: HTTP {}", response.status()));
    }

    let payload = response
        .json::<AuthStartResponse>()
        .await
        .map_err(|e| format!("Failed to parse auth start response: {e}"))?;

    store_pending_state(state.clone(), code_verifier, nonce);

    Ok(AuthStartResult {
        auth_url: payload.auth_url,
        state,
    })
}

#[tauri::command]
pub async fn start_github_auth(
    debug: Option<bool>,
    locale: Option<String>,
) -> Result<AuthStartResult, String> {
    start_oauth_auth("github", debug, locale).await
}

#[tauri::command]
pub async fn start_google_auth(
    debug: Option<bool>,
    locale: Option<String>,
) -> Result<AuthStartResult, String> {
    start_oauth_auth("google", debug, locale).await
}

#[tauri::command]
pub async fn exchange_github_auth(
    login_code: String,
    state: String,
) -> Result<AuthMeResponse, String> {
    let Some(pending) = take_pending_state(&state) else {
        return Err("登录状态已过期，请重试".to_string());
    };

    let client = Client::new();
    let base_url = auth_api_base_url();
    let exchange_url = build_auth_api_url(&base_url, "/auth/exchange")?;

    let response = client
        .post(exchange_url)
        .header(CONTENT_TYPE, "application/json")
        .header(ACCEPT, "application/json")
        .json(&serde_json::json!({
            "login_code": login_code,
            "code_verifier": pending.code_verifier,
            "nonce": pending.nonce,
        }))
        .send()
        .await
        .map_err(|e| format!("Failed to exchange auth code: {e}"))?;

    if !response.status().is_success() {
        return Err(format!("Auth exchange failed: HTTP {}", response.status()));
    }

    let tokens = response
        .json::<AuthExchangeResponse>()
        .await
        .map_err(|e| format!("Failed to parse auth exchange response: {e}"))?;

    let me = fetch_auth_me(&client, &base_url, &tokens.access_token)
        .await
        .map_err(|e| e.to_string())?;

    let profile = AuthProfile {
        username: me.username.clone().unwrap_or_else(|| "User".to_string()),
        avatar_url: me.avatar_url.clone(),
    };
    let provider = me.provider.clone().unwrap_or_else(|| "github".to_string());

    save_auth_session(AuthSession {
        provider,
        access_token: Some(tokens.access_token),
        refresh_token: Some(tokens.refresh_token),
        profile,
    })?;

    Ok(me)
}

#[tauri::command]
pub async fn exchange_google_auth(
    login_code: String,
    state: String,
) -> Result<AuthMeResponse, String> {
    exchange_github_auth(login_code, state).await
}

#[tauri::command]
pub async fn get_auth_profile() -> Result<Option<AuthMeResponse>, String> {
    let manager = ConfigManager::new();
    let mut config = manager.load()?;
    let Some(mut session) = config.auth_session.clone() else {
        return Ok(None);
    };

    let client = Client::new();
    let base_url = auth_api_base_url();

    let access_token = match session.access_token.clone() {
        Some(token) => token,
        None => {
            let Some(refresh_token) = session.refresh_token.clone() else {
                config.auth_session = None;
                manager.save(&config)?;
                return Ok(None);
            };
            let new_access = refresh_access_token(&client, &base_url, &refresh_token).await?;
            session.access_token = Some(new_access.clone());
            config.auth_session = Some(session.clone());
            manager.save(&config)?;
            new_access
        }
    };

    match fetch_auth_me(&client, &base_url, &access_token).await {
        Ok(profile) => Ok(Some(profile)),
        Err(AuthApiError::Unauthorized) => {
            let Some(refresh_token) = session.refresh_token.clone() else {
                config.auth_session = None;
                manager.save(&config)?;
                return Ok(None);
            };
            let new_access = refresh_access_token(&client, &base_url, &refresh_token).await?;
            session.access_token = Some(new_access.clone());
            config.auth_session = Some(session.clone());
            manager.save(&config)?;

            let profile = fetch_auth_me(&client, &base_url, &new_access)
                .await
                .map_err(|e| e.to_string())?;
            Ok(Some(profile))
        }
        Err(err) => Err(err.to_string()),
    }
}

#[tauri::command]
pub async fn logout_auth() -> Result<(), String> {
    let manager = ConfigManager::new();
    let mut config = manager.load()?;
    let Some(session) = config.auth_session.clone() else {
        return Ok(());
    };

    let refresh_token = session.refresh_token.clone();

    if refresh_token.is_none() {
        config.auth_session = None;
        manager.save(&config)?;
        return Ok(());
    }

    let client = Client::new();
    let base_url = auth_api_base_url();
    let logout_url = build_auth_api_url(&base_url, "/auth/logout")?;
    let response = client
        .post(logout_url)
        .header(CONTENT_TYPE, "application/json")
        .header(ACCEPT, "application/json")
        .json(&serde_json::json!({
            "refresh_token": refresh_token.clone().expect("refresh token"),
        }))
        .send()
        .await
        .map_err(|e| format!("Failed to logout: {e}"))?;

    if !response.status().is_success() {
        return Err(format!("Auth logout failed: HTTP {}", response.status()));
    }

    config.auth_session = None;
    manager.save(&config)
}

#[derive(Debug)]
enum AuthApiError {
    Unauthorized,
    Other(String),
}

impl std::fmt::Display for AuthApiError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            AuthApiError::Unauthorized => write!(f, "unauthorized"),
            AuthApiError::Other(value) => write!(f, "{value}"),
        }
    }
}

impl std::error::Error for AuthApiError {}

async fn fetch_auth_me(
    client: &Client,
    base_url: &str,
    access_token: &str,
) -> Result<AuthMeResponse, AuthApiError> {
    let me_url = build_auth_api_url(base_url, "/auth/me").map_err(AuthApiError::Other)?;
    let response = client
        .get(me_url)
        .header(AUTHORIZATION, format!("Bearer {access_token}"))
        .header(ACCEPT, "application/json")
        .send()
        .await
        .map_err(|e| AuthApiError::Other(format!("Failed to fetch auth profile: {e}")))?;

    if response.status().as_u16() == 401 {
        return Err(AuthApiError::Unauthorized);
    }

    if !response.status().is_success() {
        return Err(AuthApiError::Other(format!(
            "Auth profile request failed: HTTP {}",
            response.status()
        )));
    }

    response
        .json::<AuthMeResponse>()
        .await
        .map_err(|e| AuthApiError::Other(format!("Failed to parse auth profile: {e}")))
}

#[cfg(test)]
mod tests {
    use super::*;
    use mockito::Matcher;

    #[test]
    fn auth_session_persists_to_config() {
        crate::test_support::with_temp_home(|_| {
            let session = AuthSession {
                provider: "github".to_string(),
                access_token: Some("a".to_string()),
                refresh_token: Some("r".to_string()),
                profile: AuthProfile {
                    username: "octo".to_string(),
                    avatar_url: None,
                },
            };
            super::save_auth_session(session).expect("save auth session");
            let restored = ConfigManager::new().load().unwrap();
            let stored = restored.auth_session.unwrap();
            assert_eq!(stored.provider, "github");
            assert_eq!(stored.access_token.as_deref(), Some("a"));
            assert_eq!(stored.refresh_token.as_deref(), Some("r"));
        });
    }

    #[test]
    fn start_github_auth_returns_state_and_stores_pending() {
        crate::test_support::with_temp_home(|_| {
            let mut server = mockito::Server::new();
            std::env::set_var("SKILLS_MARKET_API_BASE", format!("{}/api/v1", server.url()));
            let _mock = server
                .mock("GET", "/api/v1/auth/github/start")
                .match_query(Matcher::Any)
                .with_status(200)
                .with_header("content-type", "application/json")
                .with_body(r#"{"auth_url":"https://example.com/auth"}"#)
                .create();

            tauri::async_runtime::block_on(async {
                let result = start_github_auth(Some(true), None)
                    .await
                    .expect("start auth");
                assert_eq!(result.auth_url, "https://example.com/auth");
                assert!(result.state.starts_with("debug-"));
                assert!(has_pending_state(&result.state));
            });
        });
    }

    #[test]
    fn exchange_github_auth_saves_session_and_returns_profile() {
        crate::test_support::with_temp_home(|_| {
            let mut server = mockito::Server::new();
            std::env::set_var("SKILLS_MARKET_API_BASE", format!("{}/api/v1", server.url()));

            let _exchange_mock = server
                .mock("POST", "/api/v1/auth/exchange")
                .match_header("content-type", "application/json")
                .match_body(Matcher::Json(serde_json::json!({
                    "login_code": "code1",
                    "code_verifier": "verifier",
                    "nonce": "nonce",
                })))
                .with_status(200)
                .with_header("content-type", "application/json")
                .with_body(
                    r#"{"access_token":"at1","refresh_token":"rt1","access_expires_at":1,"refresh_expires_at":2}"#,
                )
                .create();

            let _me_mock = server
                .mock("GET", "/api/v1/auth/me")
                .match_header("authorization", "Bearer at1")
                .with_status(200)
                .with_header("content-type", "application/json")
                .with_body(
                    r#"{"user_id":"u1","provider":"github","username":"octo","avatar_url":"https://img","email":"octo@example.com"}"#,
                )
                .create();

            set_pending_state("s1", "verifier", "nonce");

            tauri::async_runtime::block_on(async {
                let profile = exchange_github_auth("code1".to_string(), "s1".to_string())
                    .await
                    .expect("exchange auth");
                assert_eq!(profile.user_id, "u1");
                assert_eq!(profile.username.as_deref(), Some("octo"));
            });

            let restored = ConfigManager::new().load().unwrap();
            let session = restored.auth_session.expect("auth session saved");
            assert_eq!(session.provider, "github");
            assert_eq!(session.access_token.as_deref(), Some("at1"));
            assert_eq!(session.refresh_token.as_deref(), Some("rt1"));
            assert_eq!(session.profile.username, "octo");
        });
    }

    #[test]
    fn start_google_auth_returns_state_and_stores_pending() {
        crate::test_support::with_temp_home(|_| {
            let mut server = mockito::Server::new();
            std::env::set_var("SKILLS_MARKET_API_BASE", format!("{}/api/v1", server.url()));
            let _mock = server
                .mock("GET", "/api/v1/auth/google/start")
                .match_query(Matcher::Any)
                .with_status(200)
                .with_header("content-type", "application/json")
                .with_body(r#"{"auth_url":"https://example.com/google"}"#)
                .create();

            tauri::async_runtime::block_on(async {
                let result = start_google_auth(Some(true), None)
                    .await
                    .expect("start google auth");
                assert_eq!(result.auth_url, "https://example.com/google");
                assert!(result.state.starts_with("debug-"));
                assert!(has_pending_state(&result.state));
            });
        });
    }

    #[test]
    fn exchange_google_auth_saves_session_and_returns_profile() {
        crate::test_support::with_temp_home(|_| {
            let mut server = mockito::Server::new();
            std::env::set_var("SKILLS_MARKET_API_BASE", format!("{}/api/v1", server.url()));

            let _exchange_mock = server
                .mock("POST", "/api/v1/auth/exchange")
                .match_header("content-type", "application/json")
                .match_body(Matcher::Json(serde_json::json!({
                    "login_code": "gcode1",
                    "code_verifier": "verifier",
                    "nonce": "nonce",
                })))
                .with_status(200)
                .with_header("content-type", "application/json")
                .with_body(
                    r#"{"access_token":"gat1","refresh_token":"grt1","access_expires_at":1,"refresh_expires_at":2}"#,
                )
                .create();

            let _me_mock = server
                .mock("GET", "/api/v1/auth/me")
                .match_header("authorization", "Bearer gat1")
                .with_status(200)
                .with_header("content-type", "application/json")
                .with_body(
                    r#"{"user_id":"u2","provider":"google","username":"guser","avatar_url":"https://img","email":"g@example.com"}"#,
                )
                .create();

            set_pending_state("gs1", "verifier", "nonce");

            tauri::async_runtime::block_on(async {
                let profile = exchange_google_auth("gcode1".to_string(), "gs1".to_string())
                    .await
                    .expect("exchange google auth");
                assert_eq!(profile.user_id, "u2");
                assert_eq!(profile.username.as_deref(), Some("guser"));
            });

            let restored = ConfigManager::new().load().unwrap();
            let session = restored.auth_session.expect("auth session saved");
            assert_eq!(session.provider, "google");
            assert_eq!(session.access_token.as_deref(), Some("gat1"));
            assert_eq!(session.refresh_token.as_deref(), Some("grt1"));
            assert_eq!(session.profile.username, "guser");
        });
    }

    #[test]
    fn auth_tokens_persist_to_config() {
        crate::test_support::with_temp_home(|_| {
            let session = AuthSession {
                provider: "github".to_string(),
                access_token: Some("at".to_string()),
                refresh_token: Some("rt".to_string()),
                profile: AuthProfile {
                    username: "octo".to_string(),
                    avatar_url: None,
                },
            };
            super::save_auth_session(session).expect("save auth session");

            let restored = ConfigManager::new().load().unwrap();
            let stored = restored.auth_session.expect("auth session exists");
            assert_eq!(stored.access_token.as_deref(), Some("at"));
            assert_eq!(stored.refresh_token.as_deref(), Some("rt"));
        });
    }

    #[test]
    fn logout_auth_clears_session() {
        crate::test_support::with_temp_home(|_| {
            let mut server = mockito::Server::new();
            std::env::set_var("SKILLS_MARKET_API_BASE", format!("{}/api/v1", server.url()));
            let _mock = server
                .mock("POST", "/api/v1/auth/logout")
                .match_header("content-type", "application/json")
                .with_status(200)
                .with_header("content-type", "application/json")
                .with_body("{}")
                .create();

            let session = AuthSession {
                provider: "github".to_string(),
                access_token: Some("at".to_string()),
                refresh_token: Some("rt".to_string()),
                profile: AuthProfile {
                    username: "octo".to_string(),
                    avatar_url: None,
                },
            };
            save_auth_session(session).expect("save session");

            tauri::async_runtime::block_on(async {
                logout_auth().await.expect("logout");
            });

            let restored = ConfigManager::new().load().unwrap();
            assert!(restored.auth_session.is_none());
        });
    }

    #[test]
    fn get_auth_profile_returns_none_when_missing_session() {
        crate::test_support::with_temp_home(|_| {
            tauri::async_runtime::block_on(async {
                let profile = get_auth_profile().await.expect("get profile");
                assert!(profile.is_none());
            });
        });
    }
}
