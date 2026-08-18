#!/usr/bin/env python3
"""
Ironwood Insurance — Live Pipeline Refresher

Pulls current "Quoted" pipeline data straight from AgencyZoom's own public
API (https://app.agencyzoom.com/openapi/) and rewrites the DATA block inside
dashboard.html so it reflects live numbers on every scheduled run.

This talks to AgencyZoom directly — it does not use or depend on any
third-party skill/tool. Auth is via AgencyZoom's documented
POST /v1/api/auth/login endpoint (username + password -> JWT).

Required environment variables (set as GitHub Actions secrets):
    AZ_USERNAME   - AgencyZoom login email
    AZ_PASSWORD   - AgencyZoom login password

Usage:
    python3 refresh_pipeline.py path/to/dashboard.html
"""

import os
import re
import sys
import json
import time
import requests

API_BASE = "https://api.agencyzoom.com"

# --- These describe *your* agency's pipelines/stages named "Quoted".      ---
# --- Update this list if your pipeline/stage IDs change in AgencyZoom.   ---
# --- (Workflow = pipeline, WorkflowStage = stage, in AgencyZoom's API.)  ---
QUOTED_STAGES = [
    {"workflowId": 16851, "workflowStageId": "54166", "name": "1 Pipeline"},
    {"workflowId": 68506, "workflowStageId": "292558", "name": "2 Quotes Not Closed"},
    {"workflowId": 68507, "workflowStageId": "292567", "name": "3 Leads Not Quoted/Aged"},
    {"workflowId": 4539, "workflowStageId": "13617", "name": "Pipeline"},
]


def login(username, password):
    r = requests.post(
        f"{API_BASE}/v1/api/auth/login",
        json={"username": username, "password": password},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if not data.get("ownerAgent"):
        print(
            "WARNING: this login is not an agency-owner account. "
            "Pipeline data may be incomplete if any leads are only "
            "visible to other users.",
            file=sys.stderr,
        )
    return data["jwt"]


def fetch_stage_leads(jwt, workflow_id, workflow_stage_id):
    headers = {"Authorization": f"Bearer {jwt}"}
    leads, page = [], 0
    while True:
        r = requests.post(
            f"{API_BASE}/v1/api/leads/list",
            headers=headers,
            json={
                "workflowId": workflow_id,
                "workflowStageId": str(workflow_stage_id),
                "pageSize": 100,
                "page": page,
            },
            timeout=30,
        )
        r.raise_for_status()
        body = r.json()
        results = body.get("leads") or []
        if not results:
            break
        leads.extend(results)
        if len(results) < 100:
            break
        page += 1
        time.sleep(0.3)  # stay well under AgencyZoom's 120 calls/min limit
    return leads


def fetch_quote_premium(jwt, lead_id):
    headers = {"Authorization": f"Bearer {jwt}"}
    r = requests.get(
        f"{API_BASE}/v1/api/leads/{lead_id}/quotes", headers=headers, timeout=30
    )
    if r.status_code != 200:
        return 0, []
    quotes = r.json() or []
    total = sum(q.get("premium") or 0 for q in quotes)
    return total, quotes


def build_pipeline_data(jwt):
    all_leads = []
    for stage in QUOTED_STAGES:
        leads = fetch_stage_leads(jwt, stage["workflowId"], stage["workflowStageId"])
        for l in leads:
            l["_pipelineName"] = stage["name"]
        all_leads.extend(leads)
        time.sleep(0.5)

    by_producer = {}
    quoted_summary = {}
    open_counts = {}

    for lead in all_leads:
        assigned = lead.get("assignToFirstname", "") + " " + lead.get(
            "assignToLastname", ""
        )
        assigned = assigned.strip() or "Unassigned"
        open_counts[assigned] = open_counts.get(assigned, 0) + 1

        total_premium, _quotes = fetch_quote_premium(jwt, lead["id"])
        time.sleep(0.15)

        entry = {
            "name": (lead.get("firstname", "") + " " + lead.get("lastname", "")).strip()
            or lead.get("contactFirstName", "Unknown"),
            "source": lead.get("leadSourceName"),
            "pipeline": lead.get("_pipelineName"),
            "created": lead.get("createDate"),
            "lastActivity": lead.get("lastActivityDate"),
            "xDate": lead.get("xDate"),
            "url": f"https://app.agencyzoom.com/lead/index?id={lead['id']}",
            "id": lead["id"],
            "quotePremium": total_premium if total_premium > 0 else None,
        }
        by_producer.setdefault(assigned, []).append(entry)

        if total_premium > 0:
            s = quoted_summary.setdefault(
                assigned, {"totalQuoted": 0, "count": 0, "highest": None}
            )
            s["totalQuoted"] += total_premium
            s["count"] += 1
            if s["highest"] is None or total_premium > s["highest"]["premium"]:
                s["highest"] = {"name": entry["name"], "premium": total_premium, "id": lead["id"]}

    for producer, leads in by_producer.items():
        leads.sort(key=lambda x: x.get("lastActivity") or "", reverse=True)

    return by_producer, quoted_summary, open_counts


def update_dashboard(html_path, by_producer, quoted_summary, open_counts):
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    m = re.search(r"const DATA = (\{.*?\});\nconst LEADS", html, re.S)
    if not m:
        raise RuntimeError("Could not find DATA block in dashboard HTML")
    data = json.loads(m.group(1))

    data["producerPipelineLeads"] = by_producer
    data["producerQuotedPremium"] = quoted_summary
    data["producerOpenPipelineCount"] = open_counts
    data["producerOpenPipelineMeta"] = {
        "source": "Live pull from AgencyZoom's public API via scheduled GitHub Action",
        "note": f"Last refreshed {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}.",
    }

    new_data_str = json.dumps(data, ensure_ascii=False)
    new_html = html[: m.start(1)] + new_data_str + html[m.end(1) :]

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(new_html)

    total_leads = sum(len(v) for v in by_producer.values())
    total_with_premium = sum(len(v) for v in quoted_summary.values())
    print(f"Updated {html_path}: {total_leads} pipeline leads, "
          f"{sum(s['count'] for s in quoted_summary.values())} with logged premium.")


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 refresh_pipeline.py path/to/dashboard.html", file=sys.stderr)
        sys.exit(1)

    html_path = sys.argv[1]
    username = os.environ.get("AZ_USERNAME")
    password = os.environ.get("AZ_PASSWORD")
    if not username or not password:
        print("ERROR: AZ_USERNAME and AZ_PASSWORD must be set as environment variables.",
              file=sys.stderr)
        sys.exit(1)

    jwt = login(username, password)
    by_producer, quoted_summary, open_counts = build_pipeline_data(jwt)
    update_dashboard(html_path, by_producer, quoted_summary, open_counts)


if __name__ == "__main__":
    main()
