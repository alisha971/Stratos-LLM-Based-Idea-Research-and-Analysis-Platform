"""End-to-end pipeline smoke test (B8.1 / fast-ship task 3.4).

Drives start-session -> clarification -> consent -> PDF against a running
backend, then asserts the exported PDF is real. Prints PASS/FAIL and exits 0/1.

Usage:
    python scripts/run_pipeline_smoke.py
    BASE_URL=https://api.yourdomain.com AUTH_TOKEN=<jwt> python scripts/run_pipeline_smoke.py

Requires DEV_AUTH_BYPASS=true locally (uses the `dev` token by default).
"""

from __future__ import annotations

import io
import os
import sys
import time

import httpx
from pypdf import PdfReader

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "dev")
IDEA = "AI meal planner for diabetics"
# The W1 clarification worker is deliberately multi-turn (MIN 3 / MAX 5
# substantive turns -- see clarification_worker.py), so one answer never
# reaches AWAITING_CONSENT. Feed a full set; the loop below sends the next
# one each time the model asks another question, and falls back to the last
# entry if the model somehow asks more than five. `out_of_turns` at turn 5
# guarantees the session concludes regardless of confidence.
CLARIFICATION_ANSWERS = [
    "Target the US market, B2C, subscription pricing.",
    "Main users are adults with type 2 diabetes managing their diet day to day.",
    "Generic meal plans ignore individual blood-sugar response and food preferences.",
    "The riskiest assumption is that users stay engaged after the first few weeks.",
    "No hard constraints beyond standard health-data privacy; a six-month timeline.",
    "That covers it -- go ahead and start the research.",
]
# Seconds to let the worker produce its next question before answering
# again -- one clarification turn is an LLM round-trip.
CLARIFICATION_TURN_WAIT = 8
POLL_INTERVAL = 3
CONSENT_TIMEOUT = 240
# Deliberately generous while the research stage is being profiled (see
# .claude/plans/research-latency-reduction.md) -- override with
# EXPORT_TIMEOUT=<seconds> to restore a tighter budget once that lands.
EXPORT_TIMEOUT = int(os.getenv("EXPORT_TIMEOUT", str(3 * 60 * 60)))  # 3h

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

        # 2. Poll to AWAITING_CONSENT, answering each clarification question
        # in turn until the worker concludes the conversation.
        answers = iter(CLARIFICATION_ANSWERS)
        deadline = time.time() + CONSENT_TIMEOUT
        status = None
        while time.time() < deadline:
            status = client.get(f"/orchestrate/status/{session_id}").json()["status"]
            if status == "AWAITING_CONSENT":
                break
            if status == "CLARIFYING":
                message = next(answers, CLARIFICATION_ANSWERS[-1])
                client.post(
                    "/orchestrate/clarification/chat",
                    json={"session_id": session_id, "message": message},
                )
                time.sleep(CLARIFICATION_TURN_WAIT)
                continue
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

        # 4. Poll to EXPORTED, logging every stage transition with the
        # wall-clock elapsed since consent -- so a slow run shows *which*
        # stage is slow instead of just failing at the end.
        deadline = time.time() + EXPORT_TIMEOUT
        pipeline_start = time.time()
        report_status = None
        last_status = None
        while time.time() < deadline:
            report_status = client.get(
                f"/orchestrate/status/{session_id}"
            ).json()["report_status"]
            if report_status != last_status:
                print(
                    f"  [{round(time.time() - pipeline_start):>5}s] "
                    f"report_status={report_status}"
                )
                last_status = report_status
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

        # 6. Gap-closing plan Stage 5a/6: the PDF must actually contain the
        # verdict and a real sources bibliography, not just be well-formed.
        # export_worker.run_export EXPORTED does not itself guarantee
        # run_verdict succeeded (verdict_failed is non-fatal, Stage 4d) --
        # so a missing verdict here is reported as its own distinct
        # failure, not folded into a generic "PDF content wrong" message.
        pdf_text = "\n".join(
            page.extract_text() for page in PdfReader(io.BytesIO(resp.content)).pages
        )
        if "The Verdict" not in pdf_text:
            _fail(
                "PDF has no 'The Verdict' section -- either run_verdict "
                "failed for this run (check for a verdict_failed event) "
                "or _render_pdf regressed"
            )
        if "Sources" not in pdf_text:
            _fail("PDF has no 'Sources' bibliography section")

    elapsed = round(time.time() - start, 1)
    print(f"PASS: full pipeline produced a PDF with a verdict and sources in {elapsed}s")
    sys.exit(0)


if __name__ == "__main__":
    main()
