//! Licensing Gate: is one feature enabled? Prints true or false. Exit code 0 for true, 1 for false.
//! Run:  cargo run --bin gate -- <feature> [license.json] [public.pem]
use license_samples::{is_feature_enabled, kid_of};
use std::{env, fs, process};

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    let Some(feature) = args.first() else {
        eprintln!("usage: gate <feature> [license.json] [public.pem]");
        process::exit(2);
    };
    let arg = |i: usize, default: &str| args.get(i).cloned().unwrap_or_else(|| format!("../demo/{default}"));
    let text = fs::read_to_string(arg(1, "license-gated.json")).expect("read license");
    let pem = fs::read_to_string(arg(2, "demo-public.pem")).expect("read public key");

    let kid = kid_of(&text);
    let enabled = is_feature_enabled(&text, &[(kid.as_str(), pem.as_str())], feature, chrono::Utc::now());
    println!("{enabled}");
    process::exit(if enabled { 0 } else { 1 });
}
