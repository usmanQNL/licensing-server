"""Example: gate a paid feature (online_update) on a Gated license.

Run:  python example_gated.py path/to/gated-license.json path/to/public.pem
  or: python example_gated.py --app QuellDAP path/to/public.pem
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


def online_update_allowed() -> bool:
    result = verify_license(text, public_key, mode="gated", features_needed=["online_update"])
    if not result.valid_for_paid_features:
        print("Online update is locked:", result.reason)
    return result.valid_for_paid_features


if online_update_allowed():
    print("Checking for updates...")  # run the paid feature here
else:
    print("Skipping online update. Everything else still works.")
