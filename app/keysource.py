"""Read the Ed25519 signing key for the admin scripts (issue_license.py, regenerate_licenses.py).

The key comes from one of, in this order:
  1. --key-file PATH, or LICENSE_SIGNING_KEY_FILE      a PEM file outside the project
  2. --key-secret NAME, or LICENSE_SECRET_NAME         a secret in your cloud secret store
     (default name license-signing-key), fetched with the CLI named by LICENSE_KEY_SOURCE:
     gcloud (default), aws or azure. The project for gcloud is --project, else
     LICENSE_GCP_PROJECT, else LICENSE_FIRESTORE_PROJECT.

These are the same variables the Docker build scripts use. They hold names and paths, not the key.
A cloud secret is used only when its CLI is installed and signed in (gcloud auth login, aws configure
or aws sso login, az login); otherwise the script stops before signing anything and says what to run.
The CLI is found with shutil.which, so it works on Windows, where gcloud is gcloud.cmd.
"""
import os
import shutil
import subprocess

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

DEFAULT_SECRET_NAME = "license-signing-key"
SOURCES = ("gcloud", "aws", "azure")


class KeySourceError(Exception):
    """The key could not be read. The message says why and what to do."""


def find_cli(name: str) -> str:
    """Full path to a command line tool. On Windows this finds gcloud.cmd, az.cmd and so on."""
    path = shutil.which(name)
    if not path:
        raise KeySourceError(
            f"'{name}' was not found on PATH. Install it, or open a new terminal after installing, "
            f"or use --key-file / LICENSE_SIGNING_KEY_FILE instead.")
    return path


SIGN_IN = {
    "gcloud": ("gcloud", ["auth", "list", "--filter=status:ACTIVE", "--format=value(account)"], "gcloud auth login"),
    "aws": ("aws", ["sts", "get-caller-identity", "--output", "text"], "aws configure  (or aws sso login)"),
    "azure": ("az", ["account", "show", "--output", "none"], "az login"),
}


def check_cli_ready(source: str) -> None:
    """--key-secret is allowed only when the cloud CLI is installed and signed in. Fails early otherwise."""
    if source not in SIGN_IN:
        raise KeySourceError(f"LICENSE_KEY_SOURCE must be one of {', '.join(SOURCES)}, not {source!r}")
    tool, args, login = SIGN_IN[source]
    cli = find_cli(tool)
    try:
        result = subprocess.run([cli, *args], capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise KeySourceError(f"could not run {tool}: {e}") from None
    signed_in = result.returncode == 0 and (source != "gcloud" or result.stdout.strip())
    if not signed_in:
        raise KeySourceError(
            f"{tool} is installed but not signed in. Run: {login}\n"
            f"Or use --key-file / LICENSE_SIGNING_KEY_FILE instead of a cloud secret.")


def secret_command(source: str, secret: str, project: str | None) -> list:
    if source == "gcloud":
        cmd = [find_cli("gcloud"), "secrets", "versions", "access", "latest", "--secret", secret]
        if project:
            cmd += ["--project", project]
        return cmd
    if source == "aws":
        return [find_cli("aws"), "secretsmanager", "get-secret-value", "--secret-id", secret,
                "--query", "SecretString", "--output", "text"]
    if source == "azure":
        vault = os.environ.get("LICENSE_AZURE_VAULT")
        if not vault:
            raise KeySourceError("set LICENSE_AZURE_VAULT to your Key Vault name")
        return [find_cli("az"), "keyvault", "secret", "show", "--vault-name", vault, "--name", secret,
                "--query", "value", "-o", "tsv"]
    raise KeySourceError(f"LICENSE_KEY_SOURCE must be one of {', '.join(SOURCES)}, not {source!r}")


def resolve(key_file: str | None, key_secret: str | None, project: str | None) -> tuple:
    """Pick the key source from the flags, then the environment. Returns ("file", path) or
    ("secret", (source, name, project))."""
    if key_file:
        return "file", key_file
    if not key_secret and os.environ.get("LICENSE_SIGNING_KEY_FILE"):
        return "file", os.environ["LICENSE_SIGNING_KEY_FILE"]
    source = (os.environ.get("LICENSE_KEY_SOURCE") or "gcloud").lower()
    name = key_secret or os.environ.get("LICENSE_SECRET_NAME") or DEFAULT_SECRET_NAME
    if source == "gcloud":
        project = project or os.environ.get("LICENSE_GCP_PROJECT") or os.environ.get("LICENSE_FIRESTORE_PROJECT")
    return "secret", (source, name, project)


def describe(key_file: str | None, key_secret: str | None, project: str | None) -> str:
    kind, value = resolve(key_file, key_secret, project)
    if kind == "file":
        return f"key file {value}"
    source, name, proj = value
    return f"{source} secret {name}" + (f" (project {proj})" if proj else "")


def load_signing_key(key_file: str | None, key_secret: str | None, project: str | None) -> Ed25519PrivateKey:
    kind, value = resolve(key_file, key_secret, project)
    if kind == "file":
        try:
            with open(value, "rb") as f:
                pem = f.read()
        except OSError as e:
            raise KeySourceError(f"cannot read the key file {value}: {e.strerror}") from None
    else:
        source, name, proj = value
        check_cli_ready(source)
        cmd = secret_command(source, name, proj)
        try:
            result = subprocess.run(cmd, capture_output=True)
        except OSError as e:
            raise KeySourceError(f"could not run {cmd[0]}: {e}") from None
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", "replace").strip()
            raise KeySourceError(f"{source} could not read the secret {name!r}:\n{detail}")
        pem = result.stdout
    try:
        key = serialization.load_pem_private_key(pem.strip() + b"\n", password=None)
    except ValueError:
        raise KeySourceError("the signing key is empty or not a PEM private key") from None
    if not isinstance(key, Ed25519PrivateKey):
        raise KeySourceError("the signing key must be Ed25519")
    return key
