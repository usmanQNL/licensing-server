# Licensing Gate: is one feature enabled on the installed license? Prints true or false.
# Run:  ruby gate.rb <feature> [license.json] [public.pem]
# Exit code is 0 for true, 1 for false.
require_relative 'license_checks'

abort 'usage: ruby gate.rb <feature> [license.json] [public.pem]' if ARGV.empty?
demo = File.join(__dir__, '..', 'demo')
license_path = ARGV[1] || File.join(demo, 'license-gated.json')
key_path = ARGV[2] || File.join(demo, 'demo-public.pem')

enabled = LicenseChecks.feature_enabled?(File.read(license_path), File.read(key_path), ARGV[0])
puts enabled
exit(enabled ? 0 : 1)
