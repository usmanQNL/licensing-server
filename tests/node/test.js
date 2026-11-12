// Shared-fixture tests for the Node verifier. Run: node --test tests/node
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const { verifyLicense, checkOnlineReply } = require('../../verifiers/node/licensing');

const root = path.join(__dirname, '..', '..', 'verifiers');
const cases = JSON.parse(fs.readFileSync(path.join(root, 'cases.json'), 'utf8'));
const now = Date.parse(cases.now);

test('shared license cases', () => {
  for (const c of cases.cases) {
    const r = verifyLicense(c.license, cases.public_key_pem, c.mode, { featuresNeeded: c.features_needed || [], now });
    assert.strictEqual(r.valid, c.expect, c.name);
  }
});

test('online replies', () => {
  const data = JSON.parse(fs.readFileSync(path.join(root, 'online-replies.json'), 'utf8'));
  const pub = fs.readFileSync(path.join(root, 'online-public.pem'), 'utf8');
  const expected = { active: true, limit_reached: false };
  for (const [name, item] of Object.entries(data)) {
    const reply = JSON.parse(item.reply);
    const checkedAt = Date.parse(reply.payload.checked_at);
    const r = checkOnlineReply(item.reply, pub, item.license_id, { now: checkedAt + 3600 * 1000 });
    if (reply.payload.status in expected) assert.strictEqual(r.active, expected[reply.payload.status], name);
  }
});

test('license file location from <APP>_LICENSE_FILE', () => {
  const os = require('os');
  const { licenseFileEnvVar, DEFAULT_LICENSE_FILE, findLicenseFile } = require('../../verifiers/node/licensing');
  assert.strictEqual(licenseFileEnvVar('QuellDAP'), 'QUELLDAP_LICENSE_FILE');
  assert.strictEqual(licenseFileEnvVar('my app-2.0'), 'MY_APP_2_0_LICENSE_FILE');
  assert.strictEqual(licenseFileEnvVar('3d tool'), 'APP_3D_TOOL_LICENSE_FILE');
  assert.strictEqual(DEFAULT_LICENSE_FILE, 'license.json');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'lic-'));
  delete process.env.QUELLDAP_LICENSE_FILE;
  assert.strictEqual(findLicenseFile('QuellDAP', dir), path.join(process.cwd(), 'license.json')); // unset: ./license.json
  const full = path.join(dir, 'elsewhere', 'q.license.json');
  fs.writeFileSync(path.join(dir, '.env'), `QUELLDAP_LICENSE_FILE=${full}\n`);
  assert.strictEqual(findLicenseFile('QuellDAP', dir), full); // full path
  fs.writeFileSync(path.join(dir, '.env'), 'QUELLDAP_LICENSE_FILE="licensing/quelldap.license.json"\n');
  assert.strictEqual(findLicenseFile('QuellDAP', dir), path.join(dir, 'licensing', 'quelldap.license.json'));
  process.env.QUELLDAP_LICENSE_FILE = 'other.license.json';
  assert.strictEqual(findLicenseFile('QuellDAP', dir), path.join(dir, 'other.license.json'));
  delete process.env.QUELLDAP_LICENSE_FILE;
});

test('issuer cases: a reply must come from the license issuer_url', () => {
  for (const c of cases.issuer_cases) {
    const r = checkOnlineReply(c.reply, cases.public_key_pem, c.license_id, { now, issuerUrl: c.license_issuer_url });
    assert.strictEqual(r.active, c.expect_active, c.name);
  }
  const { evaluate } = require('../../verifiers/node/licensing');
  const lic = cases.cases.find(c => c.name === 'subscription_with_issuer_url').license;
  const reply = Object.fromEntries(cases.issuer_cases.map(c => [c.name, c.reply]));
  assert.ok(evaluate(lic, cases.public_key_pem, 'subscription', 'LIC-1', { replyText: reply.same_issuer, now }).valid);
  assert.ok(!evaluate(lic, cases.public_key_pem, 'subscription', 'LIC-1', { replyText: reply.same_issuer_revoked, now }).valid);
  assert.ok(evaluate(lic, cases.public_key_pem, 'subscription', 'LIC-1', { replyText: reply.different_issuer, now }).valid);
});

test('license cache location from <APP>_LICENSE_CACHE', () => {
  const os = require('os');
  const { licenseCacheEnvVar, defaultCacheFile, findLicenseCache, validIssuerUrl } = require('../../verifiers/node/licensing');
  assert.strictEqual(licenseCacheEnvVar('QuellDAP'), 'QUELLDAP_LICENSE_CACHE');
  assert.strictEqual(defaultCacheFile('/a/license.json'), path.resolve('/a/license.cache.json'));
  assert.strictEqual(defaultCacheFile('/a/LIC-1.license.json'), path.resolve('/a/LIC-1.license.cache.json'));
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'lic-'));
  delete process.env.QUELLDAP_LICENSE_FILE;
  delete process.env.QUELLDAP_LICENSE_CACHE;
  assert.strictEqual(findLicenseCache('QuellDAP', dir), path.join(process.cwd(), 'license.cache.json'));
  const lic = path.join(dir, 'licensing', 'q.license.json');
  fs.writeFileSync(path.join(dir, '.env'), `QUELLDAP_LICENSE_FILE=${lic}\n`);
  assert.strictEqual(findLicenseCache('QuellDAP', dir), path.join(dir, 'licensing', 'q.license.cache.json'));
  fs.writeFileSync(path.join(dir, '.env'), `QUELLDAP_LICENSE_FILE=${lic}\nQUELLDAP_LICENSE_CACHE=cache/lic.json\n`);
  assert.strictEqual(findLicenseCache('QuellDAP', dir), path.join(dir, 'cache', 'lic.json'));
  assert.ok(validIssuerUrl('https://licensing.example.com'));
  assert.ok(validIssuerUrl('http://localhost:8080'));
  assert.ok(!validIssuerUrl('http://licensing.example.com'));
  assert.ok(!validIssuerUrl(undefined));
});

test('refreshOnlineStatus: issuer_url, install token, cache and offline fallback', async () => {
  const crypto = require('crypto');
  const http = require('http');
  const os = require('os');
  const { canonical, refreshOnlineStatus, evaluate } = require('../../verifiers/node/licensing');
  const { privateKey, publicKey } = crypto.generateKeyPairSync('ed25519');
  const pub = publicKey.export({ type: 'spki', format: 'pem' });
  const sign = (payload) => ({ kid: 'k1', payload, signature: crypto.sign(null, Buffer.from(canonical(payload)), privateKey).toString('base64url') });
  let status = 'active';
  let replyIssuer = null;
  const tokens = {};
  const server = http.createServer((req, res) => {
    let body = '';
    req.on('data', (d) => { body += d; });
    req.on('end', () => {
      const b = JSON.parse(body);
      const payload = { v: 1, license_id: b.license_id, status, max_installs: 1,
        checked_at: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
        valid_until: new Date(Date.now() + 7 * 86400000).toISOString().replace(/\.\d{3}Z$/, 'Z'), issuer_url: replyIssuer };
      if (tokens[b.install_hash]) {
        if (b.install_token !== tokens[b.install_hash]) { res.statusCode = 403; return res.end('{}'); }
      } else {
        tokens[b.install_hash] = payload.install_token = crypto.randomBytes(8).toString('hex');
      }
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify(sign(payload)));
    });
  });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const url = `http://127.0.0.1:${server.address().port}`;
  replyIssuer = url;
  try {
    const lic = JSON.stringify(sign({ v: 1, license_id: 'LIC-N', customer: 'x', plan: 'subscription', features: [],
      max_installs: 1, issued_at: '2026-11-01T00:00:00Z', expires_at: '2099-01-01T00:00:00Z', issuer_url: url }));
    const cachePath = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'lic-')), 'sub', 'license.cache.json');
    const s = await refreshOnlineStatus(lic, pub, { cachePath, endpoint: 'https://unused.example.com' });
    assert.ok(s.contacted, s.reason);
    assert.strictEqual(s.issuerUrl, url);
    const state = JSON.parse(fs.readFileSync(cachePath, 'utf8'));
    assert.ok(state.install_hash && state.install_token && state.reply && state.last_seen);
    assert.strictEqual(state.issuer_url, url);
    assert.ok(evaluate(lic, pub, 'subscription', 'LIC-N', { replyText: s.replyText, lastSeen: s.lastSeen }).valid);

    const cached = await refreshOnlineStatus(lic, pub, { cachePath });
    assert.ok(!cached.contacted);
    status = 'revoked';
    const forced = await refreshOnlineStatus(lic, pub, { cachePath, minIntervalMs: 0 });
    assert.ok(forced.contacted, forced.reason); // the stored token was sent, so no 403
    assert.ok(!evaluate(lic, pub, 'subscription', 'LIC-N', { replyText: forced.replyText, lastSeen: forced.lastSeen }).valid);

    replyIssuer = 'https://other.example.com';
    const other = await refreshOnlineStatus(lic, pub, { cachePath: cachePath + '2' });
    assert.ok(!other.contacted && /different issuer/.test(other.reason));
  } finally {
    server.close();
  }
  // Server gone: the cached reply is used.
  const lic = JSON.stringify(sign({ v: 1, license_id: 'LIC-N', customer: 'x', plan: 'subscription', features: [],
    max_installs: 1, issued_at: '2026-11-01T00:00:00Z', expires_at: '2099-01-01T00:00:00Z', issuer_url: url }));
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'lic-'));
  const off = await refreshOnlineStatus(lic, pub, { cachePath: path.join(dir, 'c.json'), timeoutMs: 1000 });
  assert.ok(!off.contacted && /unreachable/.test(off.reason));
  assert.ok(evaluate(lic, pub, 'subscription', 'LIC-N', { replyText: off.replyText, lastSeen: off.lastSeen }).valid);
});
