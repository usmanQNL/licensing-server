"""Tests for locating the license file through <APP>_LICENSE_FILE (environment or .env)."""
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "verifiers" / "python"))
from licensing import DEFAULT_LICENSE_FILE, find_license_file, license_file_env_var, read_dotenv  # noqa: E402


def test_env_var_name():
    assert license_file_env_var("QuellDAP") == "QUELLDAP_LICENSE_FILE"
    assert license_file_env_var("my app-2.0") == "MY_APP_2_0_LICENSE_FILE"
    assert license_file_env_var("3d tool") == "APP_3D_TOOL_LICENSE_FILE"


def test_default_file_name():
    assert DEFAULT_LICENSE_FILE == "license.json"


def test_read_dotenv(tmp_path):
    (tmp_path / ".env").write_text('# c\nexport A="x y"\nB=licenses/b.license.json\n\nbad line\n', encoding="utf-8")
    assert read_dotenv(str(tmp_path / ".env")) == {"A": "x y", "B": "licenses/b.license.json"}
    assert read_dotenv(str(tmp_path / "missing.env")) == {}


def test_find_license_file_order(tmp_path, monkeypatch):
    monkeypatch.delenv("QUELLDAP_LICENSE_FILE", raising=False)
    # Unset: license.json in the current working directory.
    monkeypatch.chdir(tmp_path / "..")
    assert find_license_file("QuellDAP", str(tmp_path)) == os.path.abspath("license.json")
    # .env holds a full path.
    full = tmp_path / "elsewhere" / "q.license.json"
    (tmp_path / ".env").write_text(f"QUELLDAP_LICENSE_FILE={full}\n", encoding="utf-8")
    assert find_license_file("QuellDAP", str(tmp_path)) == str(full)
    # A relative value still works, resolved against the project root.
    (tmp_path / ".env").write_text("QUELLDAP_LICENSE_FILE=licensing/quelldap.license.json\n", encoding="utf-8")
    assert find_license_file("QuellDAP", str(tmp_path)) == str(tmp_path / "licensing" / "quelldap.license.json")
    # A real environment variable wins over .env.
    monkeypatch.setenv("QUELLDAP_LICENSE_FILE", "other.license.json")
    assert find_license_file("QuellDAP", str(tmp_path)) == os.path.abspath(str(tmp_path / "other.license.json"))
