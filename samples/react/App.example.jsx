// Example use of LicenseChecks.jsx. Load the license text however your app stores it.
import { LicenseProvider, LicensePlan, FeatureGate, useFeature } from './LicenseChecks.jsx';

const PUBLIC_KEY = `-----BEGIN PUBLIC KEY-----
...your license-public.pem...
-----END PUBLIC KEY-----`;
const ALL_FEATURES = ['sso', 'hourly_sync', 'online_update', 'export_pdf']; // from licensing/licensing.md

function ExportButton() {
  const canExport = useFeature('export_pdf'); // true or false
  return <button disabled={!canExport}>Export PDF</button>;
}

export default function App({ licenseText }) {
  return (
    <LicenseProvider licenseText={licenseText} publicKey={PUBLIC_KEY} allFeatures={ALL_FEATURES}>
      <LicensePlan />
      <FeatureGate feature="sso" fallback={<p>SSO needs a license that includes it.</p>}>
        <button>Sign in with SSO</button>
      </FeatureGate>
      <ExportButton />
    </LicenseProvider>
  );
}

// Recommended for web apps: let the server check the license (samples/node/server_express.js and others).
// The server answers GET /license/plan and refuses gated routes with HTTP 403.
import { ServerLicenseProvider } from './LicenseChecks.jsx';

export function ServerCheckedApp() {
  return (
    <ServerLicenseProvider planUrl="/license/plan">
      <FeatureGate feature="export_pdf" fallback={<p>PDF export isn't in your plan.</p>}>
        <a href="/reports/pdf">Export PDF</a>
      </FeatureGate>
    </ServerLicenseProvider>
  );
}
