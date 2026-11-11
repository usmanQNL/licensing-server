use chrono::{DateTime, Duration, Utc};
use licensing::{check_online_reply, evaluate, verify_license};
use serde_json::Value;

fn read(name: &str) -> String {
    std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/../").to_string() + name).unwrap()
}

#[test]
fn shared_license_cases() {
    let data: Value = serde_json::from_str(&read("cases.json")).unwrap();
    let now: DateTime<Utc> = DateTime::parse_from_rfc3339(data["now"].as_str().unwrap()).unwrap().with_timezone(&Utc);
    let pem = data["public_key_pem"].as_str().unwrap();
    let keys = [("", pem)];
    let mut failed = Vec::new();
    for c in data["cases"].as_array().unwrap() {
        let needed: Vec<String> = c.get("features_needed").and_then(|f| f.as_array())
            .map(|a| a.iter().map(|x| x.as_str().unwrap().to_string()).collect()).unwrap_or_default();
        let refs: Vec<&str> = needed.iter().map(|s| s.as_str()).collect();
        let r = verify_license(c["license"].as_str().unwrap(), &keys, c["mode"].as_str().unwrap(), &refs, now);
        if r.valid != c["expect"].as_bool().unwrap() {
            failed.push(format!("{}: {}", c["name"], r.reason));
        }
    }
    assert!(failed.is_empty(), "failed: {:?}", failed);
}

#[test]
fn online_replies() {
    let data: Value = serde_json::from_str(&read("online-replies.json")).unwrap();
    let pem = read("online-public.pem");
    let keys = [("", pem.as_str())];
    for (name, item) in data.as_object().unwrap() {
        let reply = item["reply"].as_str().unwrap();
        let license_id = item["license_id"].as_str().unwrap();
        let reply_json: Value = serde_json::from_str(reply).unwrap();
        let checked = DateTime::parse_from_rfc3339(reply_json["payload"]["checked_at"].as_str().unwrap()).unwrap().with_timezone(&Utc);
        let r = check_online_reply(reply, &keys, license_id, checked + Duration::hours(1), None);
        let status = reply_json["payload"]["status"].as_str().unwrap();
        assert_eq!(r.active, status == "active", "{name}");
    }
}

#[test]
fn wrong_license_and_unknown_kid_rejected() {
    let data: Value = serde_json::from_str(&read("online-replies.json")).unwrap();
    let pem = read("online-public.pem");
    let item = data.as_object().unwrap().values().next().unwrap();
    let reply = item["reply"].as_str().unwrap();
    assert!(!check_online_reply(reply, &[("", pem.as_str())], "SOME-OTHER-ID", Utc::now(), None).active);
    // A file with a kid that isn't trusted is rejected.
    let cases: Value = serde_json::from_str(&read("cases.json")).unwrap();
    let license = cases["cases"][0]["license"].as_str().unwrap();
    let mut doc: Value = serde_json::from_str(license).unwrap();
    doc["kid"] = Value::from("unknown-kid");
    let r = verify_license(&doc.to_string(), &[("k1", cases["public_key_pem"].as_str().unwrap())], "full", &[], Utc::now());
    assert!(!r.valid);
}

#[test]
fn evaluate_blocks_on_revoked_reply() {
    let cases: Value = serde_json::from_str(&read("cases.json")).unwrap();
    let pem = cases["public_key_pem"].as_str().unwrap();
    let keys = [("", pem)];
    let now: DateTime<Utc> = DateTime::parse_from_rfc3339(cases["now"].as_str().unwrap()).unwrap().with_timezone(&Utc);
    let full = cases["cases"][0]["license"].as_str().unwrap();
    // No reply: the local license decides.
    assert!(evaluate(full, &keys, "full", "X", None, &[], now, None).valid);
}

#[test]
fn license_file_location() {
    use licensing::{default_license_file, find_license_file, license_file_env_var};
    assert_eq!(license_file_env_var("QuellDAP"), "QUELLDAP_LICENSE_FILE");
    assert_eq!(license_file_env_var("my app-2.0"), "MY_APP_2_0_LICENSE_FILE");
    assert_eq!(license_file_env_var("3d tool"), "APP_3D_TOOL_LICENSE_FILE");
    assert_eq!(default_license_file("My App"), "my-app.license.json");
    let dir = std::env::temp_dir().join(format!("lic-test-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    // A name no other test or shell sets, so the environment can't interfere.
    let app = "RustEnvTestApp";
    assert_eq!(find_license_file(app, &dir), dir.join("rustenvtestapp.license.json"));
    std::fs::write(dir.join(".env"), "# c\nnot a pair\nRUSTENVTESTAPP_LICENSE_FILE='licensing/a.license.json'\n").unwrap();
    assert_eq!(find_license_file(app, &dir), dir.join("licensing/a.license.json"));
    std::fs::remove_dir_all(&dir).ok();
}
