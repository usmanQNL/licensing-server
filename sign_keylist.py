#!/usr/bin/env python3
"""Root key tooling for the signed key list (SPEC.md section 2a).

Run this on your own PC. The root private key never goes to the server, to git, or to a customer.

Step 1, once: create the root key pair.
  python sign_keylist.py init-root --out root_private.pem
  Copy the printed public key into the app (packaging/keys/root-public.pem). Back up root_private.pem offline.

Step 2, whenever a signing key is added, rotated or retired: sign a new key list.
  python sign_keylist.py sign --root-key-file root_private.pem --keys keys.json --out keylist.json
  keys.json maps each signing kid to its public PEM, e.g. {"k1": "-----BEGIN PUBLIC KEY-----..."}.
  Add --revoked k0 to block a compromised signing kid.
  Upload keylist.json to the server (LICENSE_KEYLIST_PATH) BEFORE issuing any license with the new kid.
"""
import argparse
import base64
import json
import sys
from datetime import datetime, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT_KID = "root"


def canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def cmd_init_root(args) -> None:
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    with open(args.out, "xb") as f:  # "x": refuse to overwrite an existing root key
        f.write(pem)
    pub = key.public_key().public_bytes(serialization.Encoding.PEM,
                                        serialization.PublicFormat.SubjectPublicKeyInfo)
    print(f"wrote root private key to {args.out} (keep it offline and out of git)")
    print("root public key (put this in the app):")
    print(pub.decode("ascii"))


def cmd_sign(args) -> None:
    with open(args.root_key_file, "rb") as f:
        key = serialization.load_pem_private_key(f.read(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        sys.exit("error: the root key must be Ed25519")
    with open(args.keys, encoding="utf-8") as f:
        keys = json.load(f)
    if not keys:
        sys.exit("error: keys.json must list at least one signing key")
    for kid, pem in keys.items():
        try:
            serialization.load_pem_public_key(pem.encode("ascii"))
        except (ValueError, TypeError):
            sys.exit(f"error: public key for kid {kid!r} is not a valid PEM")
    payload = {
        "v": 1,
        "issued_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "keys": keys,
        "revoked": sorted(set(args.revoked or [])),
    }
    signature = key.sign(canonical_bytes(payload))
    envelope = {"kid": ROOT_KID, "payload": payload, "signature": b64url(signature)}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(envelope, f, indent=2)
        f.write("\n")
    print(f"wrote {args.out} with signing kids: {', '.join(sorted(keys))}")
    if payload["revoked"]:
        print(f"revoked kids: {', '.join(payload['revoked'])}")


def main():
    p = argparse.ArgumentParser(description="Root key and signed key list tooling.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("init-root", help="Create the root key pair (once).")
    s1.add_argument("--out", required=True, help="Path for the root private key PEM (must not exist).")
    s1.set_defaults(func=cmd_init_root)

    s2 = sub.add_parser("sign", help="Sign a key list with the root key.")
    s2.add_argument("--root-key-file", required=True, help="Path to the root private key PEM.")
    s2.add_argument("--keys", required=True, help="JSON file mapping signing kid to public PEM.")
    s2.add_argument("--revoked", nargs="*", help="Signing kids to block, e.g. --revoked k0.")
    s2.add_argument("--out", required=True, help="Output path, e.g. keylist.json.")
    s2.set_defaults(func=cmd_sign)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
