// Example: gate a paid feature (online_update) on a Gated license.
// Run:  node example_gated.js path/to/gated-license.json path/to/public.pem
//   or: node example_gated.js --app QuellDAP path/to/public.pem   (finds the license through QUELLDAP_LICENSE_FILE in the environment or ./.env)
'use strict';
const fs = require('fs');
const { verifyLicense, findLicenseFile } = require('./licensing');

const args = process.argv.slice(2);
// --app NAME: the app's .env holds the license location, <APP>_LICENSE_FILE=relative/path/name.license.json
const [licensePath, publicKeyPath] = args[0] === '--app' ? [findLicenseFile(args[1], '.'), args[2]] : args;
const text = fs.readFileSync(licensePath, 'utf8');
const publicKey = fs.readFileSync(publicKeyPath, 'utf8');

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
