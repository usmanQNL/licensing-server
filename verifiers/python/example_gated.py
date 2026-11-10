"""Example: gate a paid feature (online_update) on a Gated license.

Run:  python example_gated.py path/to/gated-license.json path/to/public.pem
"""
import sys
from licensing import verify_license

text = open(sys.argv[1], encoding="utf-8").read()
public_key = open(sys.argv[2], encoding="utf-8").read()


def online_update_allowed() -> bool:
    result = verify_license(text, public_key, mode="gated", features_needed=["online_update"])
    if not result.valid_for_paid_features:
        print("Online update is locked:", result.reason)
    return result.valid_for_paid_features


if online_update_allowed():
    print("Checking for updates...")  # run the paid feature here
else:
    print("Skipping online update. Everything else still works.")
