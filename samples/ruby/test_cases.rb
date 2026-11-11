# Runs the shared fixtures in verifiers/cases.json against license_checks.rb.
# Run:  ruby test_cases.rb
require_relative 'license_checks'

data = JSON.parse(File.read(File.join(__dir__, '..', '..', 'verifiers', 'cases.json')))
now = Time.iso8601(data['now'])
failures = 0
data['cases'].each do |c|
  mode = c['mode'] == 'full' ? 'subscription' : c['mode']
  needed = c['features_needed'] || []
  plan = LicenseChecks.license_plan(c['license'], data['public_key_pem'], needed, now: now)
  got = plan['valid'] && (mode == 'opensource' || plan['name'] == mode) && plan['features'].first(needed.size).all? { |f| f['enabled'] }
  next if got == c['expect']
  failures += 1
  puts "FAIL #{c['name']}: got #{got}, expected #{c['expect']} (#{plan['reason']})"
end
puts "#{data['cases'].size - failures}/#{data['cases'].size} cases passed"
exit(failures.zero? ? 0 : 1)
