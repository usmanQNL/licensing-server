"""Signing key source for the admin scripts (app/keysource.py). Fake CLIs, no cloud needed."""
import os
import pathlib
import stat
import sys

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import keysource  # noqa: E402

ENV = ("LICENSE_SIGNING_KEY_FILE", "LICENSE_KEY_SOURCE", "LICENSE_SECRET_NAME", "LICENSE_GCP_PROJECT",
       "LICENSE_FIRESTORE_PROJECT", "LICENSE_AZURE_VAULT")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def pem(tmp_path):
    path = tmp_path / "k.pem"
    path.write_bytes(Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return path


def fake_cli(bin_dir, name, signed_in, pem_path):
    """A shell script standing in for gcloud/aws/az. Unix only."""
    bin_dir.mkdir(exist_ok=True)
    login = "echo me@example.com; exit 0" if signed_in else "exit 1"
    script = bin_dir / name
    script.write_text(
        "#!/bin/sh\n"
        f'case "$1" in auth|sts|account) {login} ;; esac\n'
        f'cat "{pem_path}"\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)


def test_resolve_order(monkeypatch):
    assert keysource.resolve("a.pem", None, None) == ("file", "a.pem")
    monkeypatch.setenv("LICENSE_SIGNING_KEY_FILE", "env.pem")
    assert keysource.resolve(None, None, None) == ("file", "env.pem")
    # An explicit --key-secret beats the env key file.
    monkeypatch.setenv("LICENSE_FIRESTORE_PROJECT", "fs-proj")
    assert keysource.resolve(None, "s", None) == ("secret", ("gcloud", "s", "fs-proj"))
    monkeypatch.delenv("LICENSE_SIGNING_KEY_FILE")
    monkeypatch.setenv("LICENSE_GCP_PROJECT", "gcp-proj")
    assert keysource.resolve(None, None, None) == ("secret", ("gcloud", "license-signing-key", "gcp-proj"))
    assert keysource.resolve(None, None, "flag-proj")[1][2] == "flag-proj"


def test_key_file(pem):
    assert isinstance(keysource.load_signing_key(str(pem), None, None), Ed25519PrivateKey)
    with pytest.raises(keysource.KeySourceError, match="cannot read"):
        keysource.load_signing_key(str(pem) + ".missing", None, None)


def test_cli_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(keysource.KeySourceError, match="'gcloud' was not found on PATH"):
        keysource.load_signing_key(None, "s", "p")


@pytest.mark.skipif(os.name == "nt", reason="fake CLIs are shell scripts")
@pytest.mark.parametrize("source,tool", [("gcloud", "gcloud"), ("aws", "aws"), ("azure", "az")])
def test_cli_signed_in_or_not(monkeypatch, tmp_path, pem, source, tool):
    monkeypatch.setenv("LICENSE_KEY_SOURCE", source)
    monkeypatch.setenv("LICENSE_AZURE_VAULT", "v")
    bin_dir = tmp_path / "bin"
    fake_cli(bin_dir, tool, signed_in=False, pem_path=pem)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    with pytest.raises(keysource.KeySourceError, match="not signed in"):
        keysource.load_signing_key(None, "s", "p")
    fake_cli(bin_dir, tool, signed_in=True, pem_path=pem)
    assert isinstance(keysource.load_signing_key(None, "s", "p"), Ed25519PrivateKey)


def test_unknown_source(monkeypatch):
    monkeypatch.setenv("LICENSE_KEY_SOURCE", "dropbox")
    with pytest.raises(keysource.KeySourceError, match="must be one of"):
        keysource.load_signing_key(None, "s", None)
