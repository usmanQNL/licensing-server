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
