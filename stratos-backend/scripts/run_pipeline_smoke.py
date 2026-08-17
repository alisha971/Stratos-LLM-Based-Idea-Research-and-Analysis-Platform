"""End-to-end pipeline smoke test (B8.1 / fast-ship task 3.4).

Drives start-session -> clarification -> consent -> PDF against a running
backend, then asserts the exported PDF is real. Prints PASS/FAIL and exits 0/1.

Usage:
    python scripts/run_pipeline_smoke.py
    BASE_URL=https://api.yourdomain.com AUTH_TOKEN=<jwt> python scripts/run_pipeline_smoke.py

Requires DEV_AUTH_BYPASS=true locally (uses the `dev` token by default).
"""

from __future__ import annotations

import os
import sys
import time

import httpx

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "dev")
IDEA = "AI meal planner for diabetics"
CLARIFICATION_ANSWER = "Target the US market, B2C, subscription pricing."
POLL_INTERVAL = 3
CONSENT_TIMEOUT = 180
EXPORT_TIMEOUT = 900  # 15 min

HEADERS = {"Authorization": f"Bearer {AUTH_TOKEN}"}


def _fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def main() -> None:
    start = time.time()
    with httpx.Client(base_url=BASE_URL, headers=HEADERS, timeout=30) as client:
        # 1. Start session
        resp = client.post("/orchestrate/start-session", json={"idea_description": IDEA})
        if resp.status_code != 200:
            _fail(f"start-session {resp.status_code}: {resp.text}")
        data = resp.json()
        session_id = data["session_id"]
        report_id = data["report_id"]
        print(f"session_id={session_id} report_id={report_id}")

        # 2. Poll to AWAITING_CONSENT, answering one clarification if needed.
        answered = False
        deadline = time.time() + CONSENT_TIMEOUT
        status = None
        while time.time() < deadline:
            status = client.get(f"/orchestrate/status/{session_id}").json()["status"]
            if status == "AWAITING_CONSENT":
                break
            if status == "CLARIFYING" and not answered:
                client.post(
                    "/orchestrate/clarification/chat",
                    json={"session_id": session_id, "message": CLARIFICATION_ANSWER},
                )
                answered = True
            time.sleep(POLL_INTERVAL)
        else:
            _fail(f"never reached AWAITING_CONSENT (last status={status})")

        # 3. Accept consent
        resp = client.post(
            "/orchestrate/clarification/accept-consent",
            json={"session_id": session_id},
        )
        if resp.status_code != 200:
            _fail(f"accept-consent {resp.status_code}: {resp.text}")

        # 4. Poll to EXPORTED
        deadline = time.time() + EXPORT_TIMEOUT
        report_status = None
        while time.time() < deadline:
            report_status = client.get(
                f"/orchestrate/status/{session_id}"
            ).json()["report_status"]
            if report_status == "EXPORTED":
                break
            if report_status and report_status.endswith("_FAILED"):
                _fail(f"pipeline failed with report_status={report_status}")
            time.sleep(POLL_INTERVAL)
        else:
            _fail(f"never reached EXPORTED (last report_status={report_status})")

        # 5. Download the PDF and check magic bytes.
        resp = client.get(f"/exports/{report_id}/file", follow_redirects=True)
        if resp.status_code != 200:
            _fail(f"export file {resp.status_code}: {resp.text}")
        if not resp.content.startswith(b"%PDF"):
            _fail("export file is not a valid PDF (missing %PDF header)")

    elapsed = round(time.time() - start, 1)
    print(f"PASS: full pipeline produced a PDF in {elapsed}s")
    sys.exit(0)


if __name__ == "__main__":
    main()
