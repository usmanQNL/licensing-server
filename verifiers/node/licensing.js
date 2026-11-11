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
// Cache the reply text yourself and call this again with the cached text when the
// server is unreachable. Once valid_until passes, the reply is no longer trusted.
// Never throws for bad input. Returns { active, status, reason, validUntil }.
const CLOCK_TOLERANCE_MS = 5 * 60 * 1000;
// True if the clock is earlier than the newest time this app has seen (SPEC.md section 8).
function clockMovedBack(now, lastSeen) {
  return lastSeen !== undefined && lastSeen !== null && now < lastSeen - CLOCK_TOLERANCE_MS;
}

function checkOnlineReply(text, keys, licenseId, { now = Date.now(), lastSeen = null } = {}) {
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
  const online = checkOnlineReply(replyText, keys, licenseId, { now });
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

/** Trusted {kid: PEM}. Fetches {endpoint}/v1/keys, verifies it, caches it, and falls back to the
 *  cache when offline. A fetched list older than the cached one is ignored (no rollback).
 *  Async. Throws if no valid list is available. Uses the global fetch (Node 18+) and fs. */
async function loadTrustedKeys(rootPem, { cachePath, endpoint, timeoutMs = 5000 } = {}) {
  const fs = require('fs');
  const cached = cachePath && fs.existsSync(cachePath) ? fs.readFileSync(cachePath, 'utf8') : null;
  if (endpoint) {
    try {
      const res = await fetch(endpoint.replace(/\/$/, '') + '/v1/keys', { signal: AbortSignal.timeout(timeoutMs) });
      if (res.ok) {
        const fetched = await res.text();
        verifyKeyList(fetched, rootPem);
        const issued = (t) => JSON.parse(t).payload.issued_at || '';
        if (!cached || issued(fetched) >= issued(cached)) {
          if (cachePath) fs.writeFileSync(cachePath, fetched);
          return verifyKeyList(fetched, rootPem);
        }
      }
    } catch (e) { /* offline or bad reply: use the cache */ }
  }
  if (cached) return verifyKeyList(cached, rootPem);
  throw new Error('no trusted key list: the server is unreachable and nothing is cached');
}

// ---- Locating the license file (.env: <APP_NAME>_LICENSE_FILE) ----

/** Name of the .env variable that holds the license file's location, e.g. 'QuellDAP' -> 'QUELLDAP_LICENSE_FILE'. */
function licenseFileEnvVar(appName) {
  let stem = String(appName).toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'APP';
  if (/^[0-9]/.test(stem)) stem = 'APP_' + stem;
  return stem + '_LICENSE_FILE';
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
  const name = licenseFileEnvVar(appName);
  const value = process.env[name] || readDotenv(path.join(projectRoot, '.env'))[name];
  return value ? path.resolve(projectRoot, value) : path.resolve(process.cwd(), DEFAULT_LICENSE_FILE);
}

module.exports = { verifyLicense, checkOnlineReply, evaluate, canonical, verifyKeyList, loadTrustedKeys,
  licenseFileEnvVar, DEFAULT_LICENSE_FILE, readDotenv, findLicenseFile };
