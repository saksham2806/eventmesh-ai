#!/usr/bin/env python3
"""EventMesh AI local PayPal readiness checker.

Offline by default: reads local configuration and source, never prints secret values,
never calls PayPal, never changes the database. Optional --check-local-api calls
only http://127.0.0.1:8000/openapi.json.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError

EXPECTED_ROUTE_FILES = {
    "paypal_sandbox.py": ["/paypal/sandbox/check"],
    "checkout_api.py": ["/checkout/reservations/{reservation_id}/paypal-order"],
    "paypal_capture.py": ["/checkout/reservations/{reservation_id}/capture", "/checkout/reservations/{reservation_id}/reconcile"],
    "paypal_webhooks.py": ["/webhooks/paypal"],
    "refund_api.py": ["/refunds/eligibility/{reservation_id}", "/refunds/proposals"],
    "refund_reconciliation.py": ["/refunds/proposals/{proposal_id}/execution-preview", "/refunds/proposals/{proposal_id}/reconcile"],
}


def read_env(path: Path) -> dict[str, str]:
    """Parse simple .env values without exposing them in output."""
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def report(status: str, label: str) -> None:
    print(f"[{status:7}] {label}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="EventMesh project root (contains backend and frontend)")
    parser.add_argument("--check-local-api", action="store_true", help="GET the local FastAPI OpenAPI document only; no PayPal calls")
    args = parser.parse_args()
    root = args.root.resolve()
    backend = root / "backend"
    frontend = root / "frontend"
    if not backend.is_dir() or not frontend.is_dir():
        print("ERROR: Run from D:\\eventmesh-ai or pass --root D:\\eventmesh-ai")
        return 2

    print("EVENTMESH PAYPAL READINESS - SAFE LOCAL PREFLIGHT")
    print("Checks source/config only. No credentials printed; no money or PayPal API calls.\n")
    benv_path = backend / ".env"
    fenv_path = frontend / ".env.local"
    benv, fenv = read_env(benv_path), read_env(fenv_path)
    report("OK" if benv_path.exists() else "MISSING", "Backend .env exists")
    report("OK" if fenv_path.exists() else "MISSING", "Frontend .env.local exists")

    org_b = benv.get("EVENTMESH_ORGANIZER_KEY", "")
    org_f = fenv.get("EVENTMESH_ORGANIZER_KEY", "")
    org_valid = bool(org_b and org_f and org_b == org_f and "replace-with" not in org_b.lower())
    report("OK" if org_valid else "REVIEW", "Backend/frontend organizer keys match and are non-placeholder")
    if "NEXT_PUBLIC_EVENTMESH_ORGANIZER_KEY" in fenv:
        report("WARNING", "Organizer secret has an unsafe NEXT_PUBLIC_ variable name")

    pay_vars = ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_WEBHOOK_ID")
    for var in pay_vars:
        report("PRESENT" if benv.get(var) else "MISSING", f"Backend {var} configured (value never displayed)")
    configured = bool(benv.get("PAYPAL_CLIENT_ID") and benv.get("PAYPAL_CLIENT_SECRET"))
    report("READY" if configured else "PREVIEW", "Sandbox credentials available for authorized provider-side verification")

    missing_routes: list[str] = []
    for filename, paths in EXPECTED_ROUTE_FILES.items():
        path = backend / filename
        if not path.exists():
            report("MISSING", f"backend/{filename}")
            missing_routes.extend(paths)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for route in paths:
            if route not in text:
                missing_routes.append(route)
                report("REVIEW", f"Route missing in {filename}: {route}")
            else:
                report("OK", f"Source includes route: {route}")

    bridge = frontend / "src" / "app" / "api" / "bridge" / "[...path]" / "route.ts"
    if bridge.exists():
        bt = bridge.read_text(encoding="utf-8", errors="replace")
        local_guard = 'NODE_ENV === "production"' in bt or "NODE_ENV === 'production'" in bt
        report("BLOCKED" if local_guard else "REVIEW", "Frontend bridge intentionally blocks production (requires auth solution)")
        if not re.search(r"checkout.*paypal-order|paypal-order", bt):
            report("REVIEW", "Browser API bridge has no PayPal order route (preview-only UI likely)")
    else:
        report("MISSING", "Frontend API bridge source")

    if args.check_local_api:
        print("\nLOCAL FASTAPI OPENAPI CHECK (read-only)")
        try:
            with urlopen("http://127.0.0.1:8000/openapi.json", timeout=4) as response:
                document = json.load(response)
            paths = document.get("paths", {})
            report("OK", f"Local FastAPI OpenAPI accessible ({len(paths)} paths)")
            for path in ("/paypal/sandbox/check", "/checkout/reservations/{reservation_id}/paypal-order", "/checkout/reservations/{reservation_id}/capture", "/webhooks/paypal"):
                report("OK" if path in paths else "MISSING", f"Registered API path: {path}")
        except (URLError, TimeoutError, ValueError, OSError) as exc:
            report("OFFLINE", f"Local FastAPI not reachable: {type(exc).__name__}")

    print("\nNEXT ACTION")
    if not configured:
        print("- PayPal is preview-only. A qualified, authorized account owner must supply Sandbox credentials if provider testing is needed.")
    else:
        print("- Credentials are present but connection is NOT yet verified. Test with the app's existing organizer-protected sandbox check, under authorized supervision.")
    print("- Do NOT expose FastAPI or disable the production bridge guard for deployment without authentication and event-ownership checks.")
    print("- No payment, refund, account access, or database changes were performed by this script.")
    return 0 if not missing_routes else 1

if __name__ == "__main__":
    sys.exit(main())