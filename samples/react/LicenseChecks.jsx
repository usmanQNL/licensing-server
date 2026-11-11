// React components for the Licensing Plan and Licensing Gate.
// They reuse the Web Crypto checks in ../vanilla-js/license-checks.js. Copy that file next to
// this one in your app and change the import path.
//
// WARNING: anything in the browser can be changed in devtools. Use <FeatureGate> to show or hide
// UI. Protect real work (downloads, paid API calls) with a check on your server. <ServerLicenseProvider>
// reads the plan from one of the server samples instead of checking the license in the browser.
import { createContext, useContext, useEffect, useState } from 'react';
import { licensePlan } from '../vanilla-js/license-checks.js';

const LicenseContext = createContext(null);

/** Hook: verifies the license once and returns the plan object, or null while loading. */
export function useLicensePlan(licenseText, publicKey, allFeatures) {
  const [plan, setPlan] = useState(null);
  const featuresKey = JSON.stringify(allFeatures);
  useEffect(() => {
    let cancelled = false;
    licensePlan(licenseText, publicKey, allFeatures).then((p) => { if (!cancelled) setPlan(p); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [licenseText, publicKey, featuresKey]);
  return plan;
}

/** Verifies the license once and shares the plan with every <FeatureGate> and <LicensePlan> below it. */
export function LicenseProvider({ licenseText, publicKey, allFeatures, children }) {
  const plan = useLicensePlan(licenseText, publicKey, allFeatures);
  return <LicenseContext.Provider value={plan}>{children}</LicenseContext.Provider>;
}

/** Hook: fetches the plan from your server's GET /license/plan (see samples/node, python, ruby, rust servers). */
export function useServerLicensePlan(planUrl = '/license/plan') {
  const [plan, setPlan] = useState(null);
  useEffect(() => {
    let cancelled = false;
    fetch(planUrl, { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status))))
      .catch(() => ({ valid: false, status: 'invalid', reason: 'license server unreachable', features: [] }))
      .then((p) => { if (!cancelled) setPlan(p); });
    return () => { cancelled = true; };
  }, [planUrl]);
  return plan;
}

/** Same as <LicenseProvider>, but the server checks the license and the browser only reads the result.
 *  Recommended for web apps: the server also refuses gated API calls with HTTP 403, so editing this in
 *  devtools only shows a button that still doesn't work. */
export function ServerLicenseProvider({ planUrl = '/license/plan', children }) {
  const plan = useServerLicensePlan(planUrl);
  return <LicenseContext.Provider value={plan}>{children}</LicenseContext.Provider>;
}

/** Licensing Gate as a hook: true or false. False while the license is still being checked. */
export function useFeature(feature) {
  const plan = useContext(LicenseContext);
  if (!plan) return false;
  const entry = plan.features.find((f) => f.name === feature);
  // A feature missing from the app's list is still on for a valid subscription.
  return entry ? entry.enabled : plan.valid && plan.name === 'subscription';
}

/** Licensing Gate as a component: renders children only if the feature is enabled. */
export function FeatureGate({ feature, fallback = null, children }) {
  return useFeature(feature) ? children : fallback;
}

/** Licensing Plan as a component: shows the plan JSON. */
export function LicensePlan() {
  const plan = useContext(LicenseContext);
  if (!plan) return <p>Checking license…</p>;
  return <pre>{JSON.stringify(plan, null, 2)}</pre>;
}
