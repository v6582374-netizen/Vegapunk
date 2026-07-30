#[cfg(test)]
use std::fs;
#[cfg(test)]
use std::path::Path;
#[cfg(test)]
use std::sync::{Mutex, OnceLock};
#[cfg(test)]
use std::time::{SystemTime, UNIX_EPOCH};

#[cfg(test)]
pub fn with_temp_home<F: FnOnce(&Path)>(f: F) {
    static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
    let _guard = LOCK
        .get_or_init(|| Mutex::new(()))
        .lock()
        .unwrap_or_else(|e| e.into_inner());

    let mut temp_dir = std::env::temp_dir();
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    temp_dir.push(format!("skills-manager-test-{}", nanos));
    fs::create_dir_all(&temp_dir).unwrap();

    let old_home = std::env::var("HOME").ok();
    let old_userprofile = std::env::var("USERPROFILE").ok();
    std::env::set_var("HOME", &temp_dir);
    std::env::set_var("USERPROFILE", &temp_dir);

    f(&temp_dir);

    if let Some(value) = old_home {
        std::env::set_var("HOME", value);
    }
    if let Some(value) = old_userprofile {
        std::env::set_var("USERPROFILE", value);
    }

    let _ = fs::remove_dir_all(&temp_dir);
}
