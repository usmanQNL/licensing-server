// License verifier (SPEC.md sections 1 to 4). Uses only Node's built-in crypto.
'use strict';
const crypto = require('crypto');

const SUPPORTED_VERSION = 1;
const GRACE_MS = 14 * 24 * 60 * 60 * 1000;
const MODES = ['opensource', 'subscription', 'gated'];
// 'full' was merged into 'subscription'. Licenses issued as 'full' still verify.
const LEGACY_PLAN_ALIASES = { full: 'subscription' };
const canonicalPlan = (name) => LEGACY_PLAN_ALIASES[name] || name;

// Canonical JSON: keys sorted at every level, no whitespace.
function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object') {
    return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
  }
  return JSON.stringify(value);
}

function parseTime(text) {
  return Date.parse(text);
}

// keys: a PEM string, or { kid: PEM } to support key rotation.
function pickKey(keys, kid) {
  if (typeof keys === 'string') return keys;
  if (kid === undefined || !(kid in keys)) throw new Error('no trusted key for kid ' + kid);
  return keys[kid];
}

// Never throws for bad license input. Returns { valid, reason, payload, inGrace }.
function verifyLicense(text, keys, mode, { featuresNeeded = [], now = Date.now() } = {}) {
  mode = canonicalPlan(mode);
  if (!MODES.includes(mode)) throw new Error('unknown mode: ' + mode);

  let doc, payload, signature;
  try {
    doc = JSON.parse(text);
    payload = doc.payload;
    signature = Buffer.from(doc.signature, 'base64url');
    const key = crypto.createPublicKey(pickKey(keys, doc.kid));
    if (key.asymmetricKeyType !== 'ed25519') return { valid: false, reason: 'public key must be Ed25519' };
    const ok = crypto.verify(null, Buffer.from(canonical(payload), 'utf8'), key, signature);
    if (!ok) return { valid: false, reason: 'invalid or unreadable license' };
  } catch (e) {
    return { valid: false, reason: 'invalid or unreadable license' };
  }

  if (payload.v !== SUPPORTED_VERSION) return { valid: false, reason: 'unsupported license version', payload };

  const plan = canonicalPlan(payload.plan);
  if (mode !== 'opensource' && plan !== mode) {
    return { valid: false, reason: `license is for plan '${payload.plan}', app is '${mode}'`, payload };
  }

  let inGrace = false;
  if ((mode === 'subscription' || mode === 'gated') && payload.expires_at) {
    const expires = parseTime(payload.expires_at);
    if (now > expires) {
      if (now <= expires + GRACE_MS) inGrace = true;
      else return { valid: false, reason: 'license expired', payload };
    }
  }

  if (mode === 'gated') {
    const features = new Set(payload.features || []);
    const missing = featuresNeeded.filter(f => !features.has(f));
    if (missing.length) return { valid: false, reason: 'feature not licensed: ' + missing.join(', '), payload };
  }

  return { valid: true, reason: inGrace ? 'in grace period' : 'valid', payload, inGrace };
}

// Verify a signed reply from POST /v1/check (SPEC.md section 5).
// refreshOnlineStatus() fetches and caches replies for you. Call this again with the cached text
// when the server is unreachable. Once valid_until passes, the reply is no longer trusted.
// issuerUrl: the license's issuer_url. When both it and the reply have one, they must match.
// Never throws for bad input. Returns { active, status, reason, validUntil }.
const CLOCK_TOLERANCE_MS = 5 * 60 * 1000;
// True if the clock is earlier than the newest time this app has seen (SPEC.md section 8).
function clockMovedBack(now, lastSeen) {
  return lastSeen !== undefined && lastSeen !== null && now < lastSeen - CLOCK_TOLERANCE_MS;
}

/** issuer_url must be https. http is accepted only for localhost, for local tests. */
function validIssuerUrl(url) {
  if (typeof url !== 'string' || url.length > 2048) return false;
  let u;
  try { u = new URL(url); } catch (e) { return false; }
  if (u.protocol === 'https:') return Boolean(u.hostname);
  return u.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(u.hostname);
}

const normUrl = (url) => (typeof url === 'string' ? url.replace(/\/+$/, '') : url);

/** True unless both sides name an issuer and they differ. Licenses and replies from before
 *  issuer_url existed have none, and still match. */
function sameIssuer(licenseIssuer, replyIssuer) {
  if (!licenseIssuer || !replyIssuer) return true;
  return normUrl(licenseIssuer) === normUrl(replyIssuer);
}

function checkOnlineReply(text, keys, licenseId, { now = Date.now(), lastSeen = null, issuerUrl = null } = {}) {
  if (clockMovedBack(now, lastSeen)) return { active: false, status: 'invalid', reason: 'system clock moved backwards', fresh: false };
  let payload;
  try {
    const doc = JSON.parse(text);
    payload = doc.payload;
    const key = crypto.createPublicKey(pickKey(keys, doc.kid));
    const ok = crypto.verify(null, Buffer.from(canonical(payload), 'utf8'), key, Buffer.from(doc.signature, 'base64url'));
    if (!ok) return { active: false, status: 'invalid', reason: 'invalid or unreadable reply' };
  } catch (e) {
    return { active: false, status: 'invalid', reason: 'invalid or unreadable reply' };
  }
  if (payload.v !== SUPPORTED_VERSION) return { active: false, status: 'invalid', reason: 'unsupported reply version' };
  if (payload.license_id !== licenseId) return { active: false, status: 'invalid', reason: 'reply is for a different license' };
  if (!sameIssuer(issuerUrl, payload.issuer_url)) return { active: false, status: 'invalid', reason: 'reply is from a different issuer' };

  const status = payload.status || 'unknown';
  const validUntil = payload.valid_until || '';
  if (Number.isNaN(parseTime(validUntil))) return { active: false, status: 'invalid', reason: 'invalid valid_until' };
  if (now > parseTime(validUntil)) return { active: false, status, reason: 'cached reply is too old, check again', validUntil, fresh: false };

  const fresh = true;
  if (status === 'active') return { active: true, status, reason: 'active', validUntil, fresh };
  if (status === 'limit_reached') return { active: false, status, reason: 'seat limit reached for this license', validUntil, fresh };
  if (status === 'revoked') return { active: false, status, reason: 'license revoked', validUntil, fresh };
  return { active: false, status: 'unknown', reason: 'license not recognised by the server', validUntil, fresh };
}

// One decision for the app: should paid features be on right now? (see the Python evaluate())
function evaluate(text, keys, mode, licenseId, { replyText = null, featuresNeeded = [], now = Date.now(), lastSeen = null } = {}) {
  if (clockMovedBack(now, lastSeen)) return { valid: false, reason: 'system clock moved backwards', payload: null, inGrace: false };
  const local = verifyLicense(text, keys, mode, { featuresNeeded, now });
  if (!local.valid || replyText === null) return local;
  const online = checkOnlineReply(replyText, keys, licenseId, { now, issuerUrl: local.payload.issuer_url || null });
  if (online.fresh && !online.active) return { valid: false, reason: online.reason, payload: local.payload, inGrace: local.inGrace };
  return local;
}

// ---- Signed key list (SPEC.md section 2a) ----

/** Verify a signed key list with the baked-in root PEM. Returns {kid: PEM} of trusted signing keys.
 *  Throws if the list is malformed, has the wrong signer, or fails the signature. */
function verifyKeyList(text, rootPem) {
  let env;
  try { env = JSON.parse(text); } catch (e) { throw new Error('malformed key list'); }
  if (!env || env.kid !== 'root' || !env.payload || env.payload.v !== 1) throw new Error('key list not signed by root');
  const key = crypto.createPublicKey(rootPem);
  const ok = crypto.verify(null, Buffer.from(canonical(env.payload), 'utf8'), key, Buffer.from(env.signature, 'base64url'));
  if (!ok) throw new Error('bad key list signature');
  const revoked = new Set(env.payload.revoked || []);
  const trusted = {};
  for (const [kid, pem] of Object.entries(env.payload.keys || {})) {
    if (!revoked.has(kid)) trusted[kid] = pem;
  }
  return trusted;
}

// ---- License cache file (.env: <APP_NAME>_LICENSE_CACHE) ----
// One JSON file per install holds everything fetched from the licensing server:
//   {"v": 1, license_id, issuer_url, install_hash, install_token,
//    reply: <signed /v1/check reply, as text>, checked_at, last_seen, keylist: <signed key list, as text>}
// It is signed data, not encrypted data. Nothing in it is trusted without its signature.
// A missing or damaged cache is treated as empty.
const CACHE_VERSION = 1;

function readCache(file) {
  const fs = require('fs');
  if (!file) return {};
  let text, doc;
  try { text = fs.readFileSync(file, 'utf8'); doc = JSON.parse(text); } catch (e) { return {}; }
  if (!doc || typeof doc !== 'object' || Array.isArray(doc)) return {};
  // An older key-list-only cache file holds a bare signed key list.
  if ('payload' in doc && 'signature' in doc) return { keylist: text, _legacyKeylist: true };
  return doc;
}

function writeCache(file, state) {
  const fs = require('fs');
  const path = require('path');
  fs.mkdirSync(path.dirname(path.resolve(file)), { recursive: true });
  const clean = Object.fromEntries(Object.entries(state).filter(([k]) => !k.startsWith('_')));
  fs.writeFileSync(file + '.tmp', JSON.stringify(clean, null, 2) + '\n');
  fs.renameSync(file + '.tmp', file);
}

/** Trusted {kid: PEM}. Fetches {endpoint}/v1/keys, verifies it, caches it in the license cache file
 *  (its "keylist" field), and falls back to the cache when offline. A fetched list older than the
 *  cached one is ignored (no rollback). An older key-list-only cache file is still read and kept as is.
 *  Async. Throws if no valid list is available. Uses the global fetch (Node 18+) and fs. */
async function loadTrustedKeys(rootPem, { cachePath, endpoint, timeoutMs = 5000 } = {}) {
  const fs = require('fs');
  const state = readCache(cachePath);
  const cached = state.keylist || null;
  if (endpoint) {
    try {
      const res = await fetch(endpoint.replace(/\/$/, '') + '/v1/keys', { signal: AbortSignal.timeout(timeoutMs) });
      if (res.ok) {
        const fetched = await res.text();
        verifyKeyList(fetched, rootPem);
        const issued = (t) => JSON.parse(t).payload.issued_at || '';
        if (!cached || issued(fetched) >= issued(cached)) {
          if (cachePath) {
            if (state._legacyKeylist) fs.writeFileSync(cachePath, fetched);
            else writeCache(cachePath, { ...state, v: CACHE_VERSION, keylist: fetched });
          }
          return verifyKeyList(fetched, rootPem);
        }
      }
    } catch (e) { /* offline or bad reply: use the cache */ }
  }
  if (cached) return verifyKeyList(cached, rootPem);
  throw new Error('no trusted key list: the server is unreachable and nothing is cached');
}

function verifiedPayload(text, keys) {
  try {
    const doc = JSON.parse(text);
    const key = crypto.createPublicKey(pickKey(keys, doc.kid));
    const ok = crypto.verify(null, Buffer.from(canonical(doc.payload), 'utf8'), key, Buffer.from(doc.signature, 'base64url'));
    return ok && doc.payload && typeof doc.payload === 'object' ? doc.payload : null;
  } catch (e) { return null; }
}

const fmtTime = (ms) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, 'Z');
const timeOrNull = (text) => { const t = text ? Date.parse(text) : NaN; return Number.isNaN(t) ? null : t; };

/** Run the daily online check (SPEC.md section 5) and keep the license cache up to date.
 *  The server is the license's signed issuer_url; licenses without one use `endpoint` (the app's
 *  configured URL). With neither, nothing is sent. Sends at most once per minIntervalMs.
 *  Keeps install_hash, install_token, the last valid signed reply and lastSeen in the cache.
 *  A cache made for another license or another server is started fresh (the key list is kept).
 *  Never throws for network errors. Returns { replyText, lastSeen, issuerUrl, contacted, reason }. Then:
 *    evaluate(licenseText, keys, mode, licenseId, { replyText, lastSeen }) */
async function refreshOnlineStatus(licenseText, keys, { cachePath, endpoint = null, now = Date.now(),
  timeoutMs = 5000, minIntervalMs = 24 * 3600 * 1000 } = {}) {
  const payload = verifiedPayload(licenseText, keys);
  if (!payload) return { replyText: null, lastSeen: null, issuerUrl: '', contacted: false, reason: 'license is invalid, nothing sent' };
  const licenseId = payload.license_id;
  const issuer = payload.issuer_url;
  const server = normUrl(validIssuerUrl(issuer) ? issuer : endpoint) || '';

  let state = readCache(cachePath);
  if (state.license_id !== licenseId || (state.issuer_url || '') !== server) {
    state = state.keylist ? { keylist: state.keylist } : {};
  }
  delete state._legacyKeylist;
  Object.assign(state, { v: CACHE_VERSION, license_id: licenseId, issuer_url: server });
  if (!state.install_hash) state.install_hash = crypto.randomBytes(18).toString('base64url');

  const lastSeen = timeOrNull(state.last_seen);
  const newest = lastSeen !== null ? Math.max(now, lastSeen) : now;
  const checkedAt = timeOrNull(state.checked_at);
  let contacted = false;
  let reason = 'using cached reply';

  if (!server) {
    reason = 'no server configured, offline only';
  } else if (checkedAt !== null && checkedAt <= now && now < checkedAt + minIntervalMs) {
    reason = 'checked recently, using cached reply';
  } else {
    const body = { license_id: licenseId, install_hash: state.install_hash };
    if (state.install_token) body.install_token = state.install_token;
    try {
      const res = await fetch(server + '/v1/check', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
        signal: AbortSignal.timeout(timeoutMs),
      });
      if (!res.ok) {
        reason = `server answered HTTP ${res.status}, using cached reply`;
      } else {
        const text = await res.text();
        const result = checkOnlineReply(text, keys, licenseId, { now, issuerUrl: issuer || null });
        if (result.status === 'invalid') {
          reason = 'server reply rejected: ' + result.reason;
        } else {
          contacted = true;
          reason = result.reason;
          state.reply = text;
          state.checked_at = fmtTime(now);
          const token = JSON.parse(text).payload.install_token;
          if (token) state.install_token = token;
        }
      }
    } catch (e) {
      reason = 'server unreachable, using cached reply';
    }
  }

  state.last_seen = fmtTime(newest);
  if (cachePath) {
    try { writeCache(cachePath, state); } catch (e) { reason += ' (cache not writable)'; }
  }
  return { replyText: state.reply || null, lastSeen: newest, issuerUrl: server, contacted, reason };
}

// ---- Locating the license file (.env: <APP_NAME>_LICENSE_FILE) ----

function envStem(appName) {
  let stem = String(appName).toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'APP';
  if (/^[0-9]/.test(stem)) stem = 'APP_' + stem;
  return stem;
}

/** Name of the .env variable that holds the license file's location, e.g. 'QuellDAP' -> 'QUELLDAP_LICENSE_FILE'. */
function licenseFileEnvVar(appName) {
  return envStem(appName) + '_LICENSE_FILE';
}

/** Name of the .env variable that holds the license cache file's location, e.g. 'QuellDAP' -> 'QUELLDAP_LICENSE_CACHE'. */
function licenseCacheEnvVar(appName) {
  return envStem(appName) + '_LICENSE_CACHE';
}

/** Used when <APP>_LICENSE_FILE is not set: license.json in the current working directory. */
const DEFAULT_LICENSE_FILE = 'license.json';

/** Read KEY=VALUE lines from a .env file. Missing file: {}. */
function readDotenv(file) {
  const fs = require('fs');
  let text;
  try { text = fs.readFileSync(file, 'utf8'); } catch (e) { return {}; }
  const values = {};
  for (let line of text.split(/\r?\n/)) {
    line = line.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    let key = line.slice(0, line.indexOf('=')).trim();
    if (key.startsWith('export ')) key = key.slice(7).trim();
    let value = line.slice(line.indexOf('=') + 1).trim();
    if (value.length >= 2 && value[0] === value[value.length - 1] && (value[0] === '"' || value[0] === "'")) value = value.slice(1, -1);
    values[key] = value;
  }
  return values;
}

/** Absolute path of the license file. <APP>_LICENSE_FILE holds the full path; it is read from the
 *  environment first, then from <projectRoot>/.env. A relative value resolves against projectRoot.
 *  When the variable is unset: license.json in the current working directory.
 *  The file may not exist: treat that as no license. */
function findLicenseFile(appName, projectRoot = '.') {
  const path = require('path');
  const value = setting(licenseFileEnvVar(appName), projectRoot);
  return value ? path.resolve(projectRoot, value) : path.resolve(process.cwd(), DEFAULT_LICENSE_FILE);
}

/** A variable from the environment, then from <projectRoot>/.env. Empty counts as unset. */
function setting(name, projectRoot) {
  const path = require('path');
  return process.env[name] || readDotenv(path.join(projectRoot, '.env'))[name] || null;
}

/** The cache file used when <APP>_LICENSE_CACHE is unset: next to the license file, named after it.
 *  license.json -> license.cache.json, LIC-1.license.json -> LIC-1.license.cache.json. */
function defaultCacheFile(licenseFile) {
  const path = require('path');
  const full = path.resolve(licenseFile);
  const name = path.basename(full);
  const stem = name.toLowerCase().endsWith('.json') ? name.slice(0, -5) : name;
  return path.join(path.dirname(full), stem + '.cache.json');
}

/** Absolute path of the license cache file. <APP>_LICENSE_CACHE holds the full path, read from the
 *  environment first, then from <projectRoot>/.env. A relative value resolves against projectRoot.
 *  When unset: <license file name>.cache.json next to the license file. The file may not exist yet. */
function findLicenseCache(appName, projectRoot = '.') {
  const path = require('path');
  const value = setting(licenseCacheEnvVar(appName), projectRoot);
  return value ? path.resolve(projectRoot, value) : defaultCacheFile(findLicenseFile(appName, projectRoot));
}

module.exports = { verifyLicense, checkOnlineReply, evaluate, canonical, verifyKeyList, loadTrustedKeys,
  validIssuerUrl, sameIssuer, refreshOnlineStatus,
  licenseFileEnvVar, licenseCacheEnvVar, DEFAULT_LICENSE_FILE, readDotenv, findLicenseFile,
  defaultCacheFile, findLicenseCache };
