"""Licensing Gate: is one feature enabled on the installed license? Prints true or false.

Run:  python gate.py <feature> [license.json] [public.pem]
Exit code is 0 for true, 1 for false, so shell scripts can use it too.
With no file arguments it uses the demo files in ../demo/.
"""
import os
import sys

from plan import DEMO, _read, license_plan


def is_feature_enabled(text, keys, feature, now=None):
    """True only if the license verifies (signature, version, expiry with grace) and either
    the plan is subscription (all paid features) or the feature is in the license's list."""
    return license_plan(text, keys, [feature], now)["features"][0]["enabled"]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python gate.py <feature> [license.json] [public.pem]")
    args = sys.argv[2:] + [None] * 2
    license_path = args[0] or os.path.join(DEMO, "license-gated.json")
    key_path = args[1] or os.path.join(DEMO, "demo-public.pem")
    ok = is_feature_enabled(_read(license_path), _read(key_path), sys.argv[1])
    print("true" if ok else "false")
    sys.exit(0 if ok else 1)
