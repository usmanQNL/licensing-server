//! Server-side Licensing Gate for an axum app.
//!
//! The server holds the installed license file. A route that needs a paid feature is wrapped in
//! `require_feature("...")` and answers HTTP 403 when the license doesn't include it.
//! GET /license/plan returns the plan JSON, so a frontend can show or hide UI from it.
//!
//! Run:  cd samples/rust/server && cargo run
//! Settings (environment variables, defaults are the demo files):
//!   LICENSE_FILE, LICENSE_PUBLIC_KEY, LICENSE_FEATURES, PORT
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

#[tokio::main]
async fn main() {
    let demo = |f: &str| format!("{}/../../demo/{f}", env!("CARGO_MANIFEST_DIR"));
    let setting = |name: &str, file: &str| env::var(name).unwrap_or_else(|_| demo(file));
    let cfg = Arc::new(Config {
        license_file: setting("LICENSE_FILE", "license-gated.json"),
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
