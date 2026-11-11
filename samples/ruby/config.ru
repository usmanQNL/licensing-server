# Example Rack app with the server-side gate.
# Run:  cd samples/ruby && gem install rack rackup webrick && rackup -p 8000
# Settings (environment variables, defaults are the demo files): LICENSE_FILE, LICENSE_PUBLIC_KEY, LICENSE_FEATURES
require_relative 'license_gate_middleware'

demo = File.join(__dir__, '..', 'demo')
use LicenseGateMiddleware,
    gates: { '/reports/pdf' => 'export_pdf', '/auth/sso' => 'sso' },
    license_file: ENV.fetch('LICENSE_FILE', File.join(demo, 'license-gated.json')),
    public_key: File.read(ENV.fetch('LICENSE_PUBLIC_KEY', File.join(demo, 'demo-public.pem'))),
    all_features: JSON.parse(File.read(ENV.fetch('LICENSE_FEATURES', File.join(demo, 'features.json'))))

routes = {
  '/reports/pdf' => { 'ok' => true, 'message' => 'PDF export ran' },
  '/auth/sso' => { 'ok' => true, 'message' => 'SSO is available' },
  '/health' => { 'ok' => true }
}
run lambda { |env|
  body = routes[env['PATH_INFO']]
  body ? [200, { 'content-type' => 'application/json' }, [JSON.generate(body)]] : [404, {}, ['not found']]
}
