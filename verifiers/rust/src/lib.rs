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
    if mode == "subscription" {
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

/// Verifies a signed reply from POST /v1/check. Cache the reply text yourself.
pub fn check_online_reply(text: &str, keys: Keys, license_id: &str, now: DateTime<Utc>, last_seen: Option<DateTime<Utc>>) -> OnlineResult {
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
    let online = check_online_reply(reply, keys, license_id, now, last_seen);
    if online.fresh && !online.active {
        return LicenseResult { valid: false, reason: online.reason, in_grace: local.in_grace, payload: local.payload };
    }
    local
}
