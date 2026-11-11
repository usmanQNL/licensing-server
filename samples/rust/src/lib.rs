//! Licensing Plan and Licensing Gate, built on the verifier in verifiers/rust.
use chrono::{DateTime, Utc};
use licensing::{verify_license, Keys};
use serde_json::{json, Value};

const PLANS: [&str; 4] = ["opensource", "subscription", "gated", "full"];

/// Licensing Plan. Returns the plan as JSON. Fields the license does not carry are null.
/// Never panics for a bad license: it returns valid=false with every feature disabled.
/// `all_features` is every feature your app has (the table in licensing/licensing.md).
pub fn license_plan(text: &str, keys: Keys, all_features: &[&str], now: DateTime<Utc>) -> Value {
    let plan_in_file = serde_json::from_str::<Value>(text)
        .ok()
        .and_then(|d| d["payload"]["plan"].as_str().map(String::from));
    let (valid, reason, mut payload, in_grace) = match plan_in_file.as_deref() {
        Some(p) if PLANS.contains(&p) => {
            let r = verify_license(text, keys, p, &[], now);
            (r.valid, r.reason, r.payload, r.in_grace)
        }
        _ => (false, "invalid or unreadable license".to_string(), Value::Null, false),
    };
    let status = if valid {
        if in_grace { "grace" } else { "active" }
    } else if reason == "license expired" {
        "expired"
    } else {
        payload = Value::Null; // never show fields from a license that failed its checks
        "invalid"
    };

    let has = payload.is_object();
    let plan = match payload["plan"].as_str() {
        Some("full") => Some("subscription"),
        other => other,
    };
    let licensed: Vec<&str> = payload["features"]
        .as_array()
        .map(|a| a.iter().filter_map(|x| x.as_str()).collect())
        .unwrap_or_default();
    let mut names: Vec<&str> = all_features.to_vec();
    let mut extra: Vec<&str> = licensed.iter().copied().filter(|f| !all_features.contains(f)).collect();
    extra.sort();
    names.extend(extra);
    let features: Vec<Value> = names
        .iter()
        .map(|n| json!({"name": n, "enabled": valid && (plan == Some("subscription") || licensed.contains(n))}))
        .collect();

    json!({
        "valid": valid,
        "status": status,
        "reason": reason,
        "license_id": payload["license_id"],
        "customer": payload["customer"],
        "name": plan,
        "start": payload["issued_at"],
        "expires": payload["expires_at"],
        "perpetual": has && payload.get("expires_at").is_none(),
        "max_installs": if has { payload.get("max_installs").cloned().unwrap_or(json!(1)) } else { Value::Null },
        "features": features,
    })
}

/// Licensing Gate. True only if the license verifies and the feature is on.
pub fn is_feature_enabled(text: &str, keys: Keys, feature: &str, now: DateTime<Utc>) -> bool {
    license_plan(text, keys, &[feature], now)["features"][0]["enabled"].as_bool().unwrap_or(false)
}

/// Trust one PEM for whatever `kid` the license names (like passing a single PEM in Python or Node).
/// With several keys, build the `(kid, PEM)` list yourself instead.
pub fn kid_of(text: &str) -> String {
    serde_json::from_str::<Value>(text)
        .ok()
        .and_then(|d| d["kid"].as_str().map(String::from))
        .unwrap_or_default()
}
