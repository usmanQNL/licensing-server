# Licensing Plan and Licensing Gate for Ruby. There is no Ruby verifier in verifiers/ yet, so this
# file has a small one: the same rules as verifiers/python/licensing.py (SPEC.md sections 1 to 4).
# Uses only the standard library (openssl, json, time). Needs Ruby 3.0+ with OpenSSL 3 for Ed25519.
# It passes the shared cases in verifiers/cases.json (see test_cases.rb).
require 'base64'
require 'json'
require 'openssl'
require 'time'

module LicenseChecks
  SUPPORTED_VERSION = 1
  GRACE_SECONDS = 14 * 24 * 60 * 60
  PLANS = %w[opensource subscription gated full].freeze

  module_function

  # Canonical JSON: keys sorted at every level, no whitespace, UTF-8.
  def canonical(value)
    case value
    when Hash then '{' + value.keys.sort.map { |k| JSON.generate(k) + ':' + canonical(value[k]) }.join(',') + '}'
    when Array then '[' + value.map { |v| canonical(v) }.join(',') + ']'
    else JSON.generate(value)
    end
  end

  # keys: one PEM string, or { kid => PEM } for key rotation.
  def pick_key(keys, kid)
    return keys if keys.is_a?(String)
    raise ArgumentError, "no trusted key for kid #{kid.inspect}" unless kid && keys.key?(kid)
    keys[kid]
  end

  def signature_ok?(doc, keys)
    key = OpenSSL::PKey.read(pick_key(keys, doc['kid']))
    sig = Base64.urlsafe_decode64(doc['signature'] + '=' * ((4 - doc['signature'].length % 4) % 4))
    key.verify(nil, sig, canonical(doc['payload']))
  rescue StandardError
    false
  end

  # Licensing Plan. Returns a Hash (call .to_json). Fields the license does not carry are nil.
  # Never raises for a bad license: it returns valid=false with every feature disabled.
  def license_plan(text, keys, all_features = [], now: Time.now.utc)
    payload = {}
    valid = false
    reason = 'invalid or unreadable license'
    status = 'invalid'
    begin
      doc = JSON.parse(text)
      if doc.is_a?(Hash) && doc['payload'].is_a?(Hash) && signature_ok?(doc, keys)
        payload = doc['payload']
        if payload['v'] != SUPPORTED_VERSION
          reason = 'unsupported license version'
          payload = {}
        elsif !PLANS.include?(payload['plan'])
          reason = 'unknown plan'
          payload = {}
        else
          valid = true
          reason = 'valid'
          status = 'active'
          if %w[subscription full gated].include?(payload['plan']) && payload['expires_at']
            expires = Time.iso8601(payload['expires_at'])
            if now > expires + GRACE_SECONDS
              valid = false
              reason = 'license expired'
              status = 'expired'
            elsif now > expires
              reason = 'in grace period'
              status = 'grace'
            end
          end
        end
      end
    rescue JSON::ParserError, ArgumentError, TypeError
      payload = {}
    end

    has = !payload.empty?
    plan = payload['plan'] == 'full' ? 'subscription' : payload['plan']
    licensed = Array(payload['features'])
    names = all_features + (licensed - all_features).sort
    {
      'valid' => valid,
      'status' => status,
      'reason' => reason,
      'license_id' => payload['license_id'],
      'customer' => payload['customer'],
      'name' => has ? plan : nil,
      'start' => payload['issued_at'],
      'expires' => payload['expires_at'],
      'perpetual' => has && !payload.key?('expires_at'),
      'max_installs' => has ? payload.fetch('max_installs', 1) : nil,
      'features' => names.map { |n| { 'name' => n, 'enabled' => valid && (plan == 'subscription' || licensed.include?(n)) } }
    }
  end

  # Licensing Gate. Returns true or false.
  def feature_enabled?(text, keys, feature, now: Time.now.utc)
    license_plan(text, keys, [feature], now: now)['features'][0]['enabled']
  end
end
