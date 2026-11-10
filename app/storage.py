"""Vendor-neutral storage. Implement these four methods to add a backend.

Collections (SPEC.md section 6):
  licenses: license_id, status ("active" | "revoked"), plan, customer
  installs: keyed by (license_id, install_hash); first_seen, last_seen
"""
import json
import os
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Storage(ABC):
    @abstractmethod
    def get_license(self, license_id: str) -> dict | None: ...

    @abstractmethod
    def get_install(self, license_id: str, install_hash: str) -> dict | None: ...

    @abstractmethod
    def save_install(self, license_id: str, install_hash: str, seen_at: str, token_hash: str | None = None) -> None: ...

    @abstractmethod
    def set_license_status(self, license_id: str, status: str) -> None: ...

    @abstractmethod
    def count_installs(self, license_id: str) -> int: ...

    # Admin and maintenance methods (used by the scripts, not by the server's check path).

    @abstractmethod
    def list_licenses(self, status: str | None = None, application: str | None = None) -> list[dict]:
        """Return license documents, each with a "license_id" key. Filter by status and/or application when given."""

    @abstractmethod
    def put_license(self, license_id: str, doc: dict) -> None:
        """Create or replace the license document for license_id."""

    @abstractmethod
    def delete_license(self, license_id: str) -> None:
        """Delete the license document and all of its install records. Missing ids are ignored."""


class JsonStorage(Storage):
    """Single JSON file. For local development and tests only."""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        if not os.path.exists(path):
            self._write({"licenses": {}, "installs": {}})

    def _read(self) -> dict:
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def _write(self, data: dict) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.path)

    def get_license(self, license_id):
        return self._read()["licenses"].get(license_id)

    def get_install(self, license_id, install_hash):
        return self._read()["installs"].get(f"{license_id}:{install_hash}")

    def save_install(self, license_id, install_hash, seen_at, token_hash=None):
        with self._lock:
            data = self._read()
            key = f"{license_id}:{install_hash}"
            record = data["installs"].get(key, {"first_seen": seen_at})
            if token_hash:
                record["token_hash"] = token_hash
            record["last_seen"] = seen_at
            data["installs"][key] = record
            self._write(data)

    def set_license_status(self, license_id, status):
        with self._lock:
            data = self._read()
            if license_id not in data["licenses"]:
                raise KeyError(license_id)
            data["licenses"][license_id]["status"] = status
            self._write(data)

    def count_installs(self, license_id):
        prefix = f"{license_id}:"
        return sum(1 for key in self._read()["installs"] if key.startswith(prefix))

    def list_licenses(self, status=None, application=None):
        out = []
        for license_id, doc in self._read()["licenses"].items():
            if status is not None and doc.get("status") != status:
                continue
            if application is not None and doc.get("application") != application:
                continue
            out.append({"license_id": license_id, **doc})
        return out

    def put_license(self, license_id, doc):
        with self._lock:
            data = self._read()
            data["licenses"][license_id] = {k: v for k, v in doc.items() if k != "license_id"}
            self._write(data)

    def delete_license(self, license_id):
        with self._lock:
            data = self._read()
            data["licenses"].pop(license_id, None)
            prefix = f"{license_id}:"
            data["installs"] = {k: v for k, v in data["installs"].items() if not k.startswith(prefix)}
            self._write(data)


class FirestoreStorage(Storage):
    """Google Cloud Firestore. Uses Application Default Credentials."""

    def __init__(self, project: str | None = None):
        from google.cloud import firestore  # imported here so JSON-only setups don't need it

        self.db = firestore.Client(project=project)

    def get_license(self, license_id):
        snap = self.db.collection("licenses").document(license_id).get()
        return snap.to_dict() if snap.exists else None

    def get_install(self, license_id, install_hash):
        snap = self.db.collection("installs").document(f"{license_id}:{install_hash}").get()
        return snap.to_dict() if snap.exists else None

    def save_install(self, license_id, install_hash, seen_at, token_hash=None):
        ref = self.db.collection("installs").document(f"{license_id}:{install_hash}")
        snap = ref.get()
        existing = snap.to_dict() if snap.exists else {}
        doc = {"license_id": license_id, "install_hash": install_hash,
               "first_seen": existing.get("first_seen", seen_at), "last_seen": seen_at,
               "token_hash": token_hash or existing.get("token_hash")}
        ref.set(doc)

    def set_license_status(self, license_id, status):
        self.db.collection("licenses").document(license_id).update({"status": status})

    def count_installs(self, license_id):
        # Server-side count: reads one result, not every install document.
        query = self.db.collection("installs").where("license_id", "==", license_id)
        return int(query.count(alias="n").get()[0][0].value)

    def list_licenses(self, status=None, application=None):
        query = self.db.collection("licenses")
        if status is not None:
            query = query.where("status", "==", status)
        if application is not None:
            query = query.where("application", "==", application)
        out = []
        for snap in query.stream():
            out.append({"license_id": snap.id, **snap.to_dict()})
        return out

    def put_license(self, license_id, doc):
        self.db.collection("licenses").document(license_id).set(
            {k: v for k, v in doc.items() if k != "license_id"})

    def delete_license(self, license_id):
        # Firestore batches hold at most 500 writes, so delete install records in chunks.
        installs = self.db.collection("installs").where("license_id", "==", license_id).stream()
        batch, n = self.db.batch(), 0
        for snap in installs:
            batch.delete(snap.reference)
            n += 1
            if n % 400 == 0:
                batch.commit()
                batch = self.db.batch()
        batch.delete(self.db.collection("licenses").document(license_id))
        batch.commit()


# ---- Adapter stubs for other clouds and databases ----------------------------------
# Each stub selects by LICENSE_STORAGE and fails with a clear message until it is implemented.
# The server reads only environment variables. Each platform provides them: see README "Other clouds".

class _StubStorage(Storage):
    name = "stub"
    hint = ""

    def _fail(self, *a, **k):
        raise NotImplementedError(
            f"LICENSE_STORAGE={self.name} is not implemented yet. {self.hint} "
            "Copy the FirestoreStorage class as a template, then implement the eight methods.")

    get_license = get_install = save_install = set_license_status = count_installs = _fail
    list_licenses = put_license = delete_license = _fail

    def __init__(self, *a, **k):
        self._fail()


class CosmosStorage(_StubStorage):
    """Azure Cosmos DB (NoSQL API). Connection: COSMOS_ENDPOINT and COSMOS_KEY, or Azure AD via DefaultAzureCredential."""
    name = "cosmos"
    hint = "Use azure-cosmos with the licenses and installs containers."


class DynamoStorage(_StubStorage):
    """AWS DynamoDB. Credentials: the default boto3 chain (IAM role on AWS, or AWS_* variables locally)."""
    name = "dynamodb"
    hint = "Use boto3 with a licenses table (key license_id) and an installs table (key license_id + install_hash)."


class PostgresStorage(_StubStorage):
    """Any Postgres host (DigitalOcean, AWS RDS, Azure Database, or your own). Connection: DATABASE_URL."""
    name = "postgres"
    hint = "Use psycopg with two tables, licenses and installs, and a unique key on (license_id, install_hash)."


def build_admin_storage(firestore_project: str | None = None, json_path: str | None = None) -> Storage:
    """Storage for the scripts (issue, admin, regenerate, purge). Pick the backend with one of:
    firestore_project (Firestore) or json_path (JSON file). Falls back to the server's env settings."""
    if firestore_project:
        return FirestoreStorage(firestore_project)
    if json_path:
        return JsonStorage(json_path)
    return build_storage()


def build_storage() -> Storage:
    backend = os.environ.get("LICENSE_STORAGE", "json")
    if backend == "json":
        return JsonStorage(os.environ.get("LICENSE_JSON_PATH", "license-data.json"))
    if backend == "firestore":
        return FirestoreStorage(os.environ.get("LICENSE_FIRESTORE_PROJECT"))
    if backend == "cosmos":
        return CosmosStorage()
    if backend == "dynamodb":
        return DynamoStorage()
    if backend == "postgres":
        return PostgresStorage()
    raise ValueError(f"unknown LICENSE_STORAGE backend: {backend}")
