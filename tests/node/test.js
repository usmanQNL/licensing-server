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
