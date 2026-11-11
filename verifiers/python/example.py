"""Example: check a license file in a Python app.

Run:  python example.py path/to/LIC-....license.json path/to/public.pem
  or: python example.py --app QuellDAP path/to/public.pem
      (finds the license through QUELLDAP_LICENSE_FILE in the environment or ./.env)
"""
import sys
from licensing import find_license_file, verify_license

if sys.argv[1] == "--app":
    # The app's .env holds the license location: <APP>_LICENSE_FILE=/full/path/license.json
    license_path, public_key_path = find_license_file(sys.argv[2], project_root="."), sys.argv[3]
else:
    license_path, public_key_path = sys.argv[1], sys.argv[2]
text = open(license_path, encoding="utf-8").read()
public_key = open(public_key_path, encoding="utf-8").read()

# mode: "opensource" | "subscription" | "gated"  (must match the license's plan)
result = verify_license(text, public_key, mode="subscription")

if result.valid_for_paid_features:
    print("Licensed:", result.payload["customer"], "-", result.reason)
    if result.in_grace:
        print("Warning: license expired, running in the grace period.")
else:
    print("Paid features are off:", result.reason)

# Gated: a gated license has plan "gated" and a features list.
# Use mode="gated" with the gated license, and check each feature before using it:
#   verify_license(text, public_key, mode="gated", features_needed=["sso"])
