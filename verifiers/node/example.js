// Example: check a license file in a Node.js app.
// Run:  node example.js path/to/LIC-....license.json path/to/public.pem
//   or: node example.js --app QuellDAP path/to/public.pem   (finds the license through QUELLDAP_LICENSE_FILE in the environment or ./.env)
'use strict';
const fs = require('fs');
const { verifyLicense, findLicenseFile } = require('./licensing');

const args = process.argv.slice(2);
// --app NAME: the app's .env holds the license location, <APP>_LICENSE_FILE=relative/path/name.license.json
const [licensePath, publicKeyPath] = args[0] === '--app' ? [findLicenseFile(args[1], '.'), args[2]] : args;
const text = fs.readFileSync(licensePath, 'utf8');
const publicKey = fs.readFileSync(publicKeyPath, 'utf8');

// mode: 'opensource' | 'subscription' | 'gated' (must match the license's plan)
const result = verifyLicense(text, publicKey, 'subscription');

if (result.valid) {
  console.log('Licensed:', result.payload.customer, '-', result.reason);
  if (result.inGrace) console.log('Warning: license expired, running in the grace period.');
} else {
  console.log('Paid features are off:', result.reason);
}

// Gated: a gated license has plan 'gated' and a features list.
// Use mode 'gated' with the gated license, and check each feature before using it:
//   verifyLicense(text, publicKey, 'gated', { featuresNeeded: ['sso'] })
