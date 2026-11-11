//! Licensing Plan: print the installed license plan as JSON.
//! Run:  cargo run --bin plan -- [license.json] [public.pem] [features.json]
//! With no arguments it uses the demo files in ../demo/.
use license_samples::{kid_of, license_plan};
use std::{env, fs};

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    let arg = |i: usize, default: &str| args.get(i).cloned().unwrap_or_else(|| format!("../demo/{default}"));
    let text = fs::read_to_string(arg(0, "license-gated.json")).expect("read license");
    let pem = fs::read_to_string(arg(1, "demo-public.pem")).expect("read public key");
    let all: Vec<String> = serde_json::from_str(&fs::read_to_string(arg(2, "features.json")).expect("read features")).expect("features.json must be a list");
    let all: Vec<&str> = all.iter().map(String::as_str).collect();

    let kid = kid_of(&text);
    let plan = license_plan(&text, &[(kid.as_str(), pem.as_str())], &all, chrono::Utc::now());
    println!("{}", serde_json::to_string_pretty(&plan).unwrap());
}
