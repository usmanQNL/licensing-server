// Server-side Licensing Gate for an Express app. This is the backend for the React and vanilla JS
// samples: the browser can hide a button, but only the server can refuse the work.
//
// The server holds the installed license file. A route that needs a paid feature adds
// requireFeature('...') and answers HTTP 403 when the license doesn't include it.
// GET /license/plan returns the plan JSON, so the frontend can show or hide UI from it.
//
// Run:  cd samples/node && npm install && npm start      (Node 20+)
// Settings (environment variables, defaults are the demo files):
//   LICENSE_FILE, LICENSE_PUBLIC_KEY, LICENSE_FEATURES, PORT
import express from 'express';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
// The Web Crypto checks also run on Node 20+. verifiers/node/licensing.js works too.
import { licensePlan } from '../vanilla-js/license-checks.js';

const demo = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'demo');
const LICENSE_FILE = process.env.LICENSE_FILE || path.join(demo, 'license-gated.json');
const PUBLIC_KEY = fs.readFileSync(process.env.LICENSE_PUBLIC_KEY || path.join(demo, 'demo-public.pem'), 'utf8');
const ALL_FEATURES = JSON.parse(fs.readFileSync(process.env.LICENSE_FEATURES || path.join(demo, 'features.json'), 'utf8'));

// Read and verify on every call, so a replaced license file or an expiry takes effect without a restart.
async function currentPlan() {
  return licensePlan(fs.readFileSync(LICENSE_FILE, 'utf8'), PUBLIC_KEY, ALL_FEATURES);
}

/** Express middleware: HTTP 403 unless the installed license enables `feature`. */
export function requireFeature(feature) {
  return async (req, res, next) => {
    try {
      const plan = await currentPlan();
      const entry = plan.features.find((f) => f.name === feature);
      if (entry && entry.enabled) return next();
      const reason = plan.valid ? 'the license does not include this feature' : plan.reason;
      res.status(403).json({ error: 'feature_not_licensed', feature, reason });
    } catch (err) {
      next(err); // e.g. the license file is missing: fail closed
    }
  };
}

const app = express();

app.get('/license/plan', async (req, res, next) => {
  try { res.json(await currentPlan()); } catch (err) { next(err); }
});

app.get('/reports/pdf', requireFeature('export_pdf'), (req, res) => {
  res.json({ ok: true, message: 'PDF export ran' });
});

app.get('/auth/sso', requireFeature('sso'), (req, res) => {
  res.json({ ok: true, message: 'SSO is available' });
});

app.get('/health', (req, res) => res.json({ ok: true })); // free routes need no gate

const port = Number(process.env.PORT || 8000);
app.listen(port, () => console.log(`listening on http://localhost:${port}`));
