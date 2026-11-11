# Licensing Plan: print the installed license plan as JSON.
# Run:  ruby plan.rb [license.json] [public.pem] [features.json]
# With no arguments it uses the demo files in ../demo/.
require_relative 'license_checks'

demo = File.join(__dir__, '..', 'demo')
license_path = ARGV[0] || File.join(demo, 'license-gated.json')
key_path = ARGV[1] || File.join(demo, 'demo-public.pem')
features_path = ARGV[2] || File.join(demo, 'features.json')

plan = LicenseChecks.license_plan(File.read(license_path), File.read(key_path), JSON.parse(File.read(features_path)))
puts JSON.pretty_generate(plan)
