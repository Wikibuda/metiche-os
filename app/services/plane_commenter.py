from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.core.config import settings
from app.integrations.plane import comment_on_issue


def plane_issue_url(issue_id: str) -> str | None:
    base = str(getattr(settings, "plane_issues_base_url", "") or "").strip()
    if not base:
        return None
    return f"{base.rstrip('/')}/{issue_id}"


def post_swarm_result_to_plane(issue_id: str, swarm_result: dict[str, Any]) -> bool:
    issue = str(issue_id or "").strip()
    if not issue:
        return False

    html = _format_swarm_comment_html(issue_id=issue, swarm_result=swarm_result)
    resp = comment_on_issue(issue, html)
    return bool(resp and resp.ok)


def _format_swarm_comment_html(*, issue_id: str, swarm_result: dict[str, Any]) -> str:
    decision = str(swarm_result.get("decision") or "").strip() or "unknown"
    accepted_votes = int(swarm_result.get("accepted_votes") or 0)
    rejected_votes = int(swarm_result.get("rejected_votes") or 0)
    cycles_executed = int(swarm_result.get("cycles_executed") or 0)
    stop_reason = str(swarm_result.get("stop_reason") or "").strip()
    swarm_id = str(swarm_result.get("swarm_id") or "").strip()
    swarm_name = str(swarm_result.get("swarm_name") or "").strip()
    objective = str(swarm_result.get("objective") or "").strip()
    cycle_outcome = str(swarm_result.get("cycle_outcome") or "").strip()

    dispatch_summary = str(swarm_result.get("dispatch_summary") or "").strip()
    dispatch_results = swarm_result.get("dispatch_results")
    dispatch_policy = swarm_result.get("dispatch_policy")

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    url = plane_issue_url(issue_id)

    header = f"<h2>⚙️ Enjambre ejecutado — {timestamp}</h2>"
    if swarm_name:
        header += f"<p><strong>{_escape(swarm_name)}</strong></p>"

    parts: list[str] = [header]
    parts.append("<h3>📋 Resultado</h3>")
    parts.append(
        "<p>"
        f"Decisión: <strong>{_escape(decision)}</strong> "
        f"({accepted_votes} accept, {rejected_votes} reject)"
        "</p>"
    )
    if swarm_id:
        parts.append(f"<p>Swarm ID: <code>{_escape(swarm_id)}</code></p>")
    if cycles_executed:
        parts.append(f"<p>Ciclos: {cycles_executed}</p>")
    if stop_reason:
        parts.append(f"<p>Stop reason: <code>{_escape(stop_reason)}</code></p>")
    if url:
        parts.append(f"<p>Issue: <a href=\"{_escape(url)}\">{_escape(url)}</a></p>")

    if objective:
        parts.append("<h3>🎯 Objetivo</h3>")
        parts.append(f"<pre>{_escape(objective[:4000])}</pre>")

    parts.append("<h3>📊 Output</h3>")
    if cycle_outcome:
        parts.append(f"<pre>{_escape(cycle_outcome[:4000])}</pre>")
    if dispatch_summary:
        parts.append(f"<p>Dispatch: <code>{_escape(dispatch_summary)}</code></p>")

    evidence: dict[str, Any] = {}
    if isinstance(dispatch_policy, dict):
        evidence["dispatch_policy"] = dispatch_policy
    if isinstance(dispatch_results, dict):
        safe_results: dict[str, Any] = {}
        for agent_name, payload in dispatch_results.items():
            if not isinstance(payload, dict):
                continue
            safe_results[str(agent_name)] = {
                "success": bool(payload.get("success")),
                "channel": payload.get("channel"),
                "task_type": payload.get("task_type"),
                "retry_count": payload.get("retry_count"),
                "final_status": payload.get("final_status"),
                "error": payload.get("error"),
                "details": payload.get("details"),
            }
        evidence["dispatch_results"] = safe_results

    if evidence:
        parts.append("<h3>🧾 Evidencia</h3>")
        parts.append(f"<pre>{_escape(json.dumps(evidence, ensure_ascii=False, indent=2)[:12000])}</pre>")

    return "\n".join(parts)


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )

