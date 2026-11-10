// Example: check a license file in a Node.js app.
// Run:  node example.js path/to/LIC-....license.json path/to/public.pem
'use strict';
const fs = require('fs');
const { verifyLicense } = require('./licensing');

const [licensePath, publicKeyPath] = process.argv.slice(2);
const text = fs.readFileSync(licensePath, 'utf8');
const publicKey = fs.readFileSync(publicKeyPath, 'utf8');

// mode: 'opensource' | 'subscription' | 'gated' | 'full' (must match the license's plan)
const result = verifyLicense(text, publicKey, 'full');

if (result.valid) {
  console.log('Licensed:', result.payload.customer, '-', result.reason);
  if (result.inGrace) console.log('Warning: license expired, running in the grace period.');
} else {
  console.log('Paid features are off:', result.reason);
}

// Gated: a gated license has plan 'gated' and a features list.
// Use mode 'gated' with the gated license, and check each feature before using it:
//   verifyLicense(text, publicKey, 'gated', { featuresNeeded: ['sso'] })
