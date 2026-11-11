# Server-side Licensing Gate as Rack middleware. Works with Rails, Sinatra, Hanami or plain Rack.
# The server holds the installed license file. Requests to a gated path get HTTP 403 unless the
# license enables that path's feature. GET /license/plan returns the plan JSON, so a frontend can
# show or hide UI from the server's answer.
#
# Rails:   config.middleware.use LicenseGateMiddleware, gates: { '/reports/pdf' => 'export_pdf' }, ...
# Sinatra: use LicenseGateMiddleware, gates: { ... }, license_file: ..., public_key: ..., all_features: [...]
require 'json'
require_relative 'license_checks'

class LicenseGateMiddleware
  # gates: { path prefix => feature ID }. Paths not listed are free and pass straight through.
  def initialize(app, gates:, license_file:, public_key:, all_features:)
    @app = app
    @gates = gates
    @license_file = license_file
    @public_key = public_key
    @all_features = all_features
  end

  def call(env)
    path = env['PATH_INFO']
    return json(200, current_plan) if path == '/license/plan' && env['REQUEST_METHOD'] == 'GET'

    _prefix, feature = @gates.find { |prefix, _| path == prefix || path.start_with?("#{prefix}/") }
    return @app.call(env) unless feature

    plan = current_plan
    entry = plan['features'].find { |f| f['name'] == feature }
    return @app.call(env) if entry && entry['enabled']

    reason = plan['valid'] ? 'the license does not include this feature' : plan['reason']
    json(403, { 'error' => 'feature_not_licensed', 'feature' => feature, 'reason' => reason })
  end

  private

  # Read and verify on every request, so a replaced license file or an expiry takes effect without a restart.
  def current_plan
    LicenseChecks.license_plan(File.read(@license_file), @public_key, @all_features)
  end

  def json(status, body)
    [status, { 'content-type' => 'application/json' }, [JSON.generate(body)]]
  end
end
