// Licensing Plan and Licensing Gate for the browser (and Node 20+), using Web Crypto Ed25519.
// Same rules as verifiers/node/licensing.js (SPEC.md sections 1 to 4), ported to crypto.subtle
// because the Node verifier needs Node's own crypto module.
//
// Browser support for Ed25519 in Web Crypto: Chrome 137+, Edge 137+, Firefox 129+, Safari 17+.
//
// WARNING: code in a browser can be edited by the user in devtools. Use these checks to show or
// hide UI. Anything that must really be protected (downloads, API calls) has to be checked on a server.

const SUPPORTED_VERSION = 1;
const GRACE_MS = 14 * 24 * 60 * 60 * 1000;
const PLANS = ['opensource', 'subscription', 'gated', 'full'];

// Canonical JSON: keys sorted at every level, no whitespace (SPEC.md section 1, "Signing").
function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object') {
    return '{' + Object.keys(value).sort().map((k) => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
  }
  return JSON.stringify(value);
}

function b64ToBytes(b64) {
  const std = b64.replace(/-/g, '+').replace(/_/g, '/');
  const bin = atob(std + '='.repeat((4 - (std.length % 4)) % 4));
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

function pemToSpki(pem) {
  return b64ToBytes(pem.replace(/-----[^-]+-----/g, '').replace(/\s+/g, ''));
}

// keys: one PEM string, or { kid: PEM } for key rotation.
function pickKey(keys, kid) {
  if (typeof keys === 'string') return keys;
  if (kid === undefined || !(kid in keys)) throw new Error('no trusted key for kid ' + kid);
  return keys[kid];
}

async function verifySignature(doc, keys) {
  const key = await crypto.subtle.importKey('spki', pemToSpki(pickKey(keys, doc.kid)), { name: 'Ed25519' }, false, ['verify']);
  const data = new TextEncoder().encode(canonical(doc.payload));
  return crypto.subtle.verify({ name: 'Ed25519' }, key, b64ToBytes(doc.signature), data);
}

/**
 * Licensing Plan. Resolves to a plain object (JSON-ready). Fields the license does not carry are null.
 * Never rejects for a bad license: it returns valid=false with every feature disabled.
 * @param {string} text         the license file contents
 * @param {string|object} keys  public key PEM, or { kid: PEM }
 * @param {string[]} allFeatures every feature your app has (from licensing/licensing.md)
 */
export async function licensePlan(text, keys, allFeatures = [], now = Date.now()) {
  let payload = {};
  let valid = false;
  let reason = 'invalid or unreadable license';
  let status = 'invalid';
  try {
    const doc = JSON.parse(text);
    if (await verifySignature(doc, keys)) {
      payload = doc.payload;
      if (payload.v !== SUPPORTED_VERSION) {
        reason = 'unsupported license version';
        payload = {};
      } else if (!PLANS.includes(payload.plan)) {
        reason = 'unknown plan';
        payload = {};
      } else {
        valid = true;
        reason = 'valid';
        status = 'active';
        // Expiry applies to subscription and gated licenses (SPEC.md section 4).
        const expiring = ['subscription', 'full', 'gated'].includes(payload.plan);
        if (expiring && payload.expires_at) {
          const expires = Date.parse(payload.expires_at);
          if (now > expires + GRACE_MS) {
            valid = false; reason = 'license expired'; status = 'expired';
          } else if (now > expires) {
            reason = 'in grace period'; status = 'grace';
          }
        }
      }
    }
  } catch (e) {
    payload = {};
  }

  const has = Object.keys(payload).length > 0;
  const plan = payload.plan === 'full' ? 'subscription' : payload.plan;
  const licensed = new Set(payload.features || []);
  const enabled = (name) => valid && (plan === 'subscription' || licensed.has(name));
  const names = [...allFeatures, ...[...licensed].filter((f) => !allFeatures.includes(f)).sort()];

  return {
    valid,
    status,
    reason,
    license_id: payload.license_id ?? null,
    customer: payload.customer ?? null,
    name: has ? plan : null,
    start: payload.issued_at ?? null,
    expires: payload.expires_at ?? null,
    perpetual: has && !('expires_at' in payload),
    max_installs: has ? payload.max_installs ?? 1 : null,
    features: names.map((name) => ({ name, enabled: enabled(name) })),
  };
}

/** Licensing Gate. Resolves to true or false. */
export async function isFeatureEnabled(text, keys, feature, now = Date.now()) {
  const plan = await licensePlan(text, keys, [feature], now);
  return plan.features[0].enabled;
}
