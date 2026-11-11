# Example Rack app with the server-side gate.
# Run:  cd samples/ruby && gem install rack rackup webrick && rackup -p 8000
# Settings (environment variables, defaults are the demo files): APP_NAME (default Demo) and
# <APP_NAME>_LICENSE_FILE (the license's full path, from the environment or ./.env; unset: ./license.json, then the demo license),
# LICENSE_PUBLIC_KEY, LICENSE_FEATURES. For example APP_NAME=QuellDAP reads QUELLDAP_LICENSE_FILE from .env.
require_relative 'license_gate_middleware'

demo = File.join(__dir__, '..', 'demo')

# The project's .env holds the license's full path as <APP_NAME>_LICENSE_FILE. A real environment variable wins.
# Unset: license.json in the working directory, or the demo license if there is none.
license_var = ENV.fetch('APP_NAME', 'Demo').upcase.gsub(/[^A-Z0-9]+/, '_').gsub(/\A_+|_+\z/, '')
license_var = "APP_#{license_var}" if license_var.match?(/\A[0-9]/)
license_var += '_LICENSE_FILE'
dotenv = File.exist?('.env') ? File.readlines('.env', chomp: true) : []
from_dotenv = dotenv.map(&:strip).reject { |l| l.empty? || l.start_with?('#') || !l.include?('=') }
                    .map { |l| l.sub(/\Aexport\s+/, '').split('=', 2).map(&:strip) }
                    .to_h.transform_values { |v| v.sub(/\A(["'])(.*)\1\z/, '\\2') }
license_value = ENV[license_var] || from_dotenv[license_var]
license_file = if license_value then File.expand_path(license_value)
               elsif File.exist?('license.json') then File.expand_path('license.json')
               else File.join(demo, 'license-gated.json')
               end
use LicenseGateMiddleware,
    gates: { '/reports/pdf' => 'export_pdf', '/auth/sso' => 'sso' },
    license_file: license_file,
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
