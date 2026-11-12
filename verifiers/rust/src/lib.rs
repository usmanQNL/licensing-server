//! License verifier (SPEC.md sections 1 to 8). Full parity with the Python and Node verifiers:
//! license files, key rotation by `kid`, the daily online reply, and `evaluate`.
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use chrono::{DateTime, Duration, Utc};
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use serde_json::Value;

const SUPPORTED_VERSION: i64 = 1;
const GRACE_DAYS: i64 = 14;
const MODES: [&str; 3] = ["opensource", "subscription", "gated"];
// "full" was merged into "subscription". Licenses issued as "full" still verify.
fn canonical_plan(name: &str) -> &str {
    if name == "full" { "subscription" } else { name }
}

/// Trusted public keys as (kid, SPKI PEM) pairs. A single pair is used for files without a kid.
pub type Keys<'a> = &'a [(&'a str, &'a str)];

#[derive(Debug, PartialEq)]
pub struct LicenseResult {
    pub valid: bool,
    pub reason: String,
    pub in_grace: bool,
    pub payload: Value,
}

#[derive(Debug, PartialEq)]
pub struct OnlineResult {
    pub active: bool,
    pub status: String,
    pub reason: String,
    pub fresh: bool,
}

fn license_fail(reason: &str, payload: Value) -> LicenseResult {
    LicenseResult { valid: false, reason: reason.into(), in_grace: false, payload }
}

/// Reads the 32-byte Ed25519 key from an SPKI PEM block.
pub fn load_public_key(pem: &str) -> Option<VerifyingKey> {
    let body: String = pem.lines().filter(|l| !l.starts_with("-----")).collect();
    let der = base64::engine::general_purpose::STANDARD.decode(body).ok()?;
    if der.len() < 32 {
        return None;
    }
    let bytes: [u8; 32] = der[der.len() - 32..].try_into().ok()?;
    VerifyingKey::from_bytes(&bytes).ok()
}

/// Picks the key for a document's kid. Without a kid, a single trusted key is used.
fn pick_key(keys: Keys, kid: Option<&str>) -> Option<VerifyingKey> {
    let pem = match kid {
        Some(k) => keys.iter().find(|(id, _)| *id == k)?.1,
        None if keys.len() == 1 => keys[0].1,
        None => return None,
    };
    load_public_key(pem)
}

/// Canonical JSON: sorted keys (serde_json's default map is sorted), no whitespace.
fn canonical(v: &Value) -> String {
    serde_json::to_string(v).expect("serializing a Value cannot fail")
}

/// Verifies `doc["signature"]` over `doc["payload"]`. Returns the payload if the signature is valid.
fn verified_payload<'a>(doc: &'a Value, keys: Keys) -> Option<&'a Value> {
    let payload = doc.get("payload")?;
    let sig_bytes = URL_SAFE_NO_PAD.decode(doc.get("signature")?.as_str()?).ok()?;
    let key = pick_key(keys, doc.get("kid").and_then(|k| k.as_str()))?;
    let sig = Signature::from_slice(&sig_bytes).ok()?;
    key.verify(canonical(payload).as_bytes(), &sig).ok()?;
    Some(payload)
}

fn parse_time(text: &str) -> Option<DateTime<Utc>> {
    DateTime::parse_from_rfc3339(text).ok().map(|d| d.with_timezone(&Utc))
}

/// Verifies a license file for a mode. Never panics on bad input.
pub fn verify_license(text: &str, keys: Keys, mode: &str, features_needed: &[&str], now: DateTime<Utc>) -> LicenseResult {
    let mode = canonical_plan(mode);
    if !MODES.contains(&mode) {
        return license_fail("unknown mode", Value::Null);
    }
    let doc: Value = match serde_json::from_str(text) {
        Ok(d) => d,
        Err(_) => return license_fail("invalid or unreadable license", Value::Null),
    };
    let payload = match verified_payload(&doc, keys) {
        Some(p) => p.clone(),
        None => return license_fail("invalid or unreadable license", Value::Null),
    };

    if payload.get("v").and_then(|v| v.as_i64()) != Some(SUPPORTED_VERSION) {
        return license_fail("unsupported license version", payload);
    }
    let plan = canonical_plan(payload.get("plan").and_then(|p| p.as_str()).unwrap_or(""));
    if mode != "opensource" && plan != mode {
        return license_fail(&format!("license is for plan '{plan}', app is '{mode}'"), payload);
    }

    let mut in_grace = false;
    if mode == "subscription" || mode == "gated" {
        if let Some(exp_text) = payload.get("expires_at").and_then(|e| e.as_str()) {
            let expires = match parse_time(exp_text) {
                Some(d) => d,
                None => return license_fail("invalid expires_at", payload),
            };
            if now > expires {
                if now <= expires + Duration::days(GRACE_DAYS) {
                    in_grace = true;
                } else {
                    return license_fail("license expired", payload);
                }
            }
        }
    }

    if mode == "gated" {
        let features: Vec<&str> = payload
            .get("features")
            .and_then(|f| f.as_array())
            .map(|a| a.iter().filter_map(|x| x.as_str()).collect())
            .unwrap_or_default();
        let missing: Vec<&str> = features_needed.iter().copied().filter(|f| !features.contains(f)).collect();
        if !missing.is_empty() {
            return license_fail(&format!("feature not licensed: {}", missing.join(", ")), payload);
        }
    }

    LicenseResult {
        valid: true,
        reason: if in_grace { "in grace period".into() } else { "valid".into() },
        in_grace,
        payload,
    }
}

/// True if the clock is earlier than the newest time this app has seen (SPEC.md section 8).
pub fn clock_moved_back(now: DateTime<Utc>, last_seen: Option<DateTime<Utc>>) -> bool {
    matches!(last_seen, Some(seen) if now < seen - Duration::minutes(5))
}

/// issuer_url must be https. http is accepted only for localhost, for local tests.
pub fn valid_issuer_url(url: &str) -> bool {
    if url.len() > 2048 {
        return false;
    }
    let host = |rest: &str| -> String {
        let authority = rest.split(['/', '?', '#']).next().unwrap_or("");
        let authority = authority.rsplit('@').next().unwrap_or("");
        if let Some(stripped) = authority.strip_prefix('[') {
            return stripped.split(']').next().unwrap_or("").to_string();
        }
        authority.split(':').next().unwrap_or("").to_string()
    };
    if let Some(rest) = url.strip_prefix("https://") {
        return !host(rest).is_empty();
    }
    if let Some(rest) = url.strip_prefix("http://") {
        return matches!(host(rest).as_str(), "localhost" | "127.0.0.1" | "::1");
    }
    false
}

/// True unless both sides name an issuer and they differ. Licenses and replies from before
/// issuer_url existed have none, and still match.
pub fn same_issuer(license_issuer: Option<&str>, reply_issuer: Option<&str>) -> bool {
    match (license_issuer, reply_issuer) {
        (Some(a), Some(b)) if !a.is_empty() && !b.is_empty() => a.trim_end_matches('/') == b.trim_end_matches('/'),
        _ => true,
    }
}

/// Verifies a signed reply from POST /v1/check. Cache the reply text yourself (SPEC.md section 5
/// describes the cache file). Same as `check_online_reply_for_issuer` without an issuer check.
pub fn check_online_reply(text: &str, keys: Keys, license_id: &str, now: DateTime<Utc>, last_seen: Option<DateTime<Utc>>) -> OnlineResult {
    check_online_reply_for_issuer(text, keys, license_id, None, now, last_seen)
}

/// Verifies a signed reply from POST /v1/check. `issuer_url` is the license's issuer_url: when both it
/// and the reply have one, they must match.
pub fn check_online_reply_for_issuer(text: &str, keys: Keys, license_id: &str, issuer_url: Option<&str>, now: DateTime<Utc>, last_seen: Option<DateTime<Utc>>) -> OnlineResult {
    let invalid = |reason: &str| OnlineResult { active: false, status: "invalid".into(), reason: reason.into(), fresh: false };
    if clock_moved_back(now, last_seen) {
        return invalid("system clock moved backwards");
    }
    let doc: Value = match serde_json::from_str(text) {
        Ok(d) => d,
        Err(_) => return invalid("invalid or unreadable reply"),
    };
    let payload = match verified_payload(&doc, keys) {
        Some(p) => p,
        None => return invalid("invalid or unreadable reply"),
    };
    if payload.get("v").and_then(|v| v.as_i64()) != Some(SUPPORTED_VERSION) {
        return invalid("unsupported reply version");
    }
    if payload.get("license_id").and_then(|l| l.as_str()) != Some(license_id) {
        return invalid("reply is for a different license");
    }
    if !same_issuer(issuer_url, payload.get("issuer_url").and_then(|u| u.as_str())) {
        return invalid("reply is from a different issuer");
    }

    let status = payload.get("status").and_then(|s| s.as_str()).unwrap_or("unknown").to_string();
    let valid_until = match payload.get("valid_until").and_then(|v| v.as_str()).and_then(parse_time) {
        Some(d) => d,
        None => return invalid("invalid valid_until"),
    };
    if now > valid_until {
        return OnlineResult { active: false, status, reason: "cached reply is too old, check again".into(), fresh: false };
    }

    let (active, reason) = match status.as_str() {
        "active" => (true, "active"),
        "limit_reached" => (false, "seat limit reached for this license"),
        "revoked" => (false, "license revoked"),
        _ => {
            return OnlineResult {
                active: false,
                status: "unknown".into(),
                reason: "license not recognised by the server".into(),
                fresh: true,
            }
        }
    };
    OnlineResult { active, status, reason: reason.into(), fresh: true }
}

/// One decision for the app: should paid features be on right now?
/// Off when the local license is invalid, or a fresh reply says revoked, unknown, or limit_reached.
/// With no reply, or a reply past valid_until, the local license decides.
pub fn evaluate(text: &str, keys: Keys, mode: &str, license_id: &str, reply: Option<&str>, features_needed: &[&str], now: DateTime<Utc>, last_seen: Option<DateTime<Utc>>) -> LicenseResult {
    if clock_moved_back(now, last_seen) {
        return license_fail("system clock moved backwards", Value::Null);
    }
    let local = verify_license(text, keys, mode, features_needed, now);
    if !local.valid {
        return local;
    }
    let reply = match reply {
        Some(r) => r,
        None => return local,
    };
    let issuer = local.payload.get("issuer_url").and_then(|u| u.as_str());
    let online = check_online_reply_for_issuer(reply, keys, license_id, issuer, now, last_seen);
    if online.fresh && !online.active {
        return LicenseResult { valid: false, reason: online.reason, in_grace: local.in_grace, payload: local.payload };
    }
    local
}

// ---- Locating the license file (.env: <APP_NAME>_LICENSE_FILE) ----

/// Name of the .env variable that holds the license file's location, e.g. "QuellDAP" -> "QUELLDAP_LICENSE_FILE".
pub fn license_file_env_var(app_name: &str) -> String {
    env_stem(app_name) + "_LICENSE_FILE"
}

/// Name of the .env variable that holds the license cache file's location, e.g. "QuellDAP" -> "QUELLDAP_LICENSE_CACHE".
pub fn license_cache_env_var(app_name: &str) -> String {
    env_stem(app_name) + "_LICENSE_CACHE"
}

fn env_stem(app_name: &str) -> String {
    let mut stem = String::new();
    for c in app_name.to_uppercase().chars() {
        if c.is_ascii_alphanumeric() {
            stem.push(c);
        } else if !stem.is_empty() && !stem.ends_with('_') {
            stem.push('_');
        }
    }
    let mut stem = stem.trim_end_matches('_').to_string();
    if stem.is_empty() {
        stem = "APP".into();
    }
    if stem.starts_with(|c: char| c.is_ascii_digit()) {
        stem = format!("APP_{stem}");
    }
    stem
}

/// Used when <APP>_LICENSE_FILE is not set: license.json in the current working directory.
pub const DEFAULT_LICENSE_FILE: &str = "license.json";

/// Value of `key` in a .env file (KEY=VALUE lines). None when the file or key is missing.
pub fn read_dotenv_value(path: &std::path::Path, key: &str) -> Option<String> {
    let text = std::fs::read_to_string(path).ok()?;
    for line in text.lines() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let Some((k, v)) = line.split_once('=') else { continue };
        let k = k.trim();
        let k = k.strip_prefix("export ").map(str::trim).unwrap_or(k);
        if k == key {
            let v = v.trim();
            let unquoted = if v.len() >= 2 && (v.starts_with('"') && v.ends_with('"') || v.starts_with('\'') && v.ends_with('\'')) { &v[1..v.len() - 1] } else { v };
            return Some(unquoted.to_string());
        }
    }
    None
}

/// Path of the license file. <APP>_LICENSE_FILE holds the full path; it is read from the environment
/// first, then from <project_root>/.env. A relative value is joined to `project_root`. When the variable
/// is unset: license.json in the current working directory. The file may not exist: treat that as no license.
pub fn find_license_file(app_name: &str, project_root: &std::path::Path) -> std::path::PathBuf {
    match setting(&license_file_env_var(app_name), project_root) {
        Some(v) => project_root.join(v), // join keeps an absolute value as is
        None => std::env::current_dir().unwrap_or_default().join(DEFAULT_LICENSE_FILE),
    }
}

/// A variable from the environment, then from <project_root>/.env. Empty counts as unset.
fn setting(var: &str, project_root: &std::path::Path) -> Option<String> {
    std::env::var(var)
        .ok()
        .filter(|v| !v.is_empty())
        .or_else(|| read_dotenv_value(&project_root.join(".env"), var).filter(|v| !v.is_empty()))
}

/// The cache file used when <APP>_LICENSE_CACHE is unset: next to the license file, named after it.
/// license.json -> license.cache.json, LIC-1.license.json -> LIC-1.license.cache.json.
pub fn default_cache_file(license_file: &std::path::Path) -> std::path::PathBuf {
    let name = license_file.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
    let stem = if name.to_lowercase().ends_with(".json") { &name[..name.len() - 5] } else { name.as_str() };
    license_file.with_file_name(format!("{stem}.cache.json"))
}

/// Path of the license cache file (SPEC.md section 5). <APP>_LICENSE_CACHE holds the full path, read
/// from the environment first, then from <project_root>/.env. A relative value is joined to `project_root`.
/// When unset: <license file name>.cache.json next to the license file. The file may not exist yet.
pub fn find_license_cache(app_name: &str, project_root: &std::path::Path) -> std::path::PathBuf {
    match setting(&license_cache_env_var(app_name), project_root) {
        Some(v) => project_root.join(v),
        None => default_cache_file(&find_license_file(app_name, project_root)),
    }
}
