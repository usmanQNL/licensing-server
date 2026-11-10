// Example: gate a paid feature (online_update) on a Gated license.
// Run:  node example_gated.js path/to/gated-license.json path/to/public.pem
'use strict';
const fs = require('fs');
const { verifyLicense } = require('./licensing');

const text = fs.readFileSync(process.argv[2], 'utf8');
const publicKey = fs.readFileSync(process.argv[3], 'utf8');

function onlineUpdateAllowed() {
  const result = verifyLicense(text, publicKey, 'gated', { featuresNeeded: ['online_update'] });
  if (!result.valid) console.log('Online update is locked:', result.reason);
  return result.valid;
}

if (onlineUpdateAllowed()) {
  console.log('Checking for updates...'); // run the paid feature here
} else {
  console.log('Skipping online update. Everything else still works.');
}
