use crate::models::update::{GithubRelease, UpdateInfo};
use semver::Version;
use serde::Deserialize;
use std::error::Error;

const REPO_OWNER: &str = "jiweiyeah";
const REPO_NAME: &str = "Skills-Manager";

#[derive(Debug, Deserialize)]
struct GithubErrorBody {
    message: Option<String>,
}

pub async fn check_for_updates(
    current_version: &str,
    github_token: Option<&str>,
) -> Result<UpdateInfo, Box<dyn Error>> {
    let client = reqwest::Client::new();
    let url = format!(
        "https://api.github.com/repos/{}/{}/releases/latest",
        REPO_OWNER, REPO_NAME
    );

    let mut request = client
        .get(&url)
        .header("User-Agent", "Skills-Manager-App")
        .header("Accept", "application/vnd.github+json");

    if let Some(token) = github_token.map(|t| t.trim()).filter(|t| !t.is_empty()) {
        request = request.bearer_auth(token);
    }

    let response = request.send().await?;
    let status = response.status();
    let body = response.text().await?;

    if !status.is_success() {
        let message = serde_json::from_str::<GithubErrorBody>(&body)
            .ok()
            .and_then(|err| err.message)
            .unwrap_or_else(|| body.clone());
        let hint = match status.as_u16() {
            403 if message.to_lowercase().contains("rate limit") => {
                " (configure a GitHub token in settings to raise the limit)"
            }
            404 => " (no published release found for this repository)",
            401 => " (invalid or expired GitHub token)",
            _ => "",
        };
        return Err(format!("GitHub API {}: {}{}", status, message, hint).into());
    }

    let resp: GithubRelease = serde_json::from_str(&body)
        .map_err(|e| format!("failed to parse GitHub release response: {}", e))?;

    let clean_latest = resp.tag_name.trim_start_matches('v');
    let latest_v = Version::parse(clean_latest)?;
    let current_v = Version::parse(current_version)?;

    Ok(UpdateInfo {
        has_update: latest_v > current_v,
        latest_version: resp.tag_name,
        download_url: resp.html_url,
        release_notes: resp.body,
    })
}
