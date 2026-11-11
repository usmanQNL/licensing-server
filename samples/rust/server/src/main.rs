//! Server-side Licensing Gate for an axum app.
//!
//! The server holds the installed license file. A route that needs a paid feature is wrapped in
//! `require_feature("...")` and answers HTTP 403 when the license doesn't include it.
//! GET /license/plan returns the plan JSON, so a frontend can show or hide UI from it.
//!
//! Run:  cd samples/rust/server && cargo run
//! Settings (environment variables, defaults are the demo files):
//!   APP_NAME (default Demo) and <APP_NAME>_LICENSE_FILE (the license's full path, from the environment or
//!   ./.env; unset: ./license.json, then the demo license), LICENSE_PUBLIC_KEY, LICENSE_FEATURES, PORT.
//!   For example APP_NAME=QuellDAP reads QUELLDAP_LICENSE_FILE=/srv/quelldap/license.json from .env.
use axum::{
    extract::{Request, State},
    http::StatusCode,
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::get,
    Json, Router,
};
use license_samples::{kid_of, license_plan};
use serde_json::{json, Value};
use std::{env, fs, sync::Arc};

struct Config {
    license_file: String,
    public_key: String,
    all_features: Vec<String>,
}

impl Config {
    /// Read and verify on every call, so a replaced license file or an expiry takes effect without a restart.
    fn current_plan(&self) -> Value {
        let text = fs::read_to_string(&self.license_file).unwrap_or_default(); // missing file: invalid, fail closed
        let kid = kid_of(&text);
        let all: Vec<&str> = self.all_features.iter().map(String::as_str).collect();
        license_plan(&text, &[(kid.as_str(), self.public_key.as_str())], &all, chrono::Utc::now())
    }
}

/// Middleware: HTTP 403 unless the installed license enables `feature`.
async fn gate(feature: &'static str, cfg: Arc<Config>, req: Request, next: Next) -> Response {
    let plan = cfg.current_plan();
    let enabled = plan["features"]
        .as_array()
        .and_then(|fs| fs.iter().find(|f| f["name"] == feature))
        .and_then(|f| f["enabled"].as_bool())
        .unwrap_or(false);
    if enabled {
        return next.run(req).await;
    }
    let reason = if plan["valid"] == true { json!("the license does not include this feature") } else { plan["reason"].clone() };
    (StatusCode::FORBIDDEN, Json(json!({"error": "feature_not_licensed", "feature": feature, "reason": reason}))).into_response()
}

/// Wraps a router so every route in it needs `feature`.
fn require_feature<S: Clone + Send + Sync + 'static>(feature: &'static str, cfg: Arc<Config>, routes: Router<S>) -> Router<S> {
    routes.layer(middleware::from_fn(move |req: Request, next: Next| gate(feature, cfg.clone(), req, next)))
}

async fn get_plan(State(cfg): State<Arc<Config>>) -> Json<Value> {
    Json(cfg.current_plan())
}

/// The project's .env holds the license's full path as <APP_NAME>_LICENSE_FILE. A real environment variable wins.
/// None: the caller falls back to ./license.json, then the demo license. The verifier crate
/// (verifiers/rust) has the same lookup as `find_license_file`.
fn license_file_setting() -> Option<String> {
    let app = env::var("APP_NAME").unwrap_or_else(|_| "Demo".into());
    let mut stem: String = app.to_uppercase().chars().map(|c| if c.is_ascii_alphanumeric() { c } else { '_' }).collect();
    while stem.contains("__") {
        stem = stem.replace("__", "_");
    }
    let mut stem = stem.trim_matches('_').to_string();
    if stem.starts_with(|c: char| c.is_ascii_digit()) {
        stem = format!("APP_{stem}");
    }
    let var = format!("{stem}_LICENSE_FILE");
    env::var(&var).ok().filter(|v| !v.is_empty()).or_else(|| {
        let text = fs::read_to_string(".env").ok()?;
        text.lines().find_map(|line| {
            let (k, v) = line.trim().split_once('=')?;
            let k = k.trim();
            (k.strip_prefix("export ").map(str::trim).unwrap_or(k) == var).then(|| v.trim().trim_matches(|c| c == '"' || c == '\'').to_string())
        })
    })
}

#[tokio::main]
async fn main() {
    let demo = |f: &str| format!("{}/../../demo/{f}", env!("CARGO_MANIFEST_DIR"));
    let setting = |name: &str, file: &str| env::var(name).unwrap_or_else(|_| demo(file));
    let cfg = Arc::new(Config {
        license_file: license_file_setting()
            .or_else(|| std::path::Path::new("license.json").exists().then(|| "license.json".to_string()))
            .unwrap_or_else(|| demo("license-gated.json")),
        public_key: fs::read_to_string(setting("LICENSE_PUBLIC_KEY", "demo-public.pem")).expect("read public key"),
        all_features: serde_json::from_str(&fs::read_to_string(setting("LICENSE_FEATURES", "features.json")).expect("read features"))
            .expect("features.json must be a list"),
    });

    let pdf = Router::new().route("/reports/pdf", get(|| async { Json(json!({"ok": true, "message": "PDF export ran"})) }));
    let sso = Router::new().route("/auth/sso", get(|| async { Json(json!({"ok": true, "message": "SSO is available"})) }));

    let app = Router::new()
        .route("/license/plan", get(get_plan))
        .route("/health", get(|| async { Json(json!({"ok": true})) })) // free routes need no gate
        .merge(require_feature("export_pdf", cfg.clone(), pdf))
        .merge(require_feature("sso", cfg.clone(), sso))
        .with_state(cfg);

    let port = env::var("PORT").unwrap_or_else(|_| "8000".into());
    let listener = tokio::net::TcpListener::bind(format!("0.0.0.0:{port}")).await.unwrap();
    println!("listening on http://localhost:{port}");
    axum::serve(listener, app).await.unwrap();
}
