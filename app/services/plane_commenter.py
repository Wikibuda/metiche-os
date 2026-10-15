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
    compiled_output = str(swarm_result.get("compiled_output") or "").strip()

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

    # Mostrar archivos generados si existen
    output_file = _extract_output_file(swarm_result)
    if output_file:
        filename = output_file.split('/')[-1] if '/' in output_file else output_file
        swarm_url = f"https://dashboard.masamadremonterrey.com/reportes-swarm/{filename}"
        parts.append("<h3>📁 Archivo generado</h3>")
        parts.append(f"<p><a href=\"{_escape(swarm_url)}\" style=\"color:#e94560;\">🔗 {_escape(swarm_url)}</a></p>")
        parts.append(f"<p>Ruta: <code>{_escape(output_file)}</code></p>")

    parts.append("<h3>📊 Output del enjambre</h3>")
    # Usar compiled_output si existe y tiene datos reales
    output_text = ""
    if compiled_output and len(compiled_output) > 20:
        output_text = compiled_output
    elif cycle_outcome and "AGENT OUTPUT" in cycle_outcome:
        # Extraer solo la parte de AGENT OUTPUT
        idx = cycle_outcome.find("AGENT OUTPUT")
        output_text = cycle_outcome[idx + 16:].strip()[:8000]
    elif cycle_outcome:
        output_text = cycle_outcome[:4000]
    
    if output_text:
        if "_section=" in output_text or " | " in output_text:
            html_output = _format_data_as_html(output_text)
            parts.append(html_output)
        elif any(w in output_text for w in ["##", "**", "- ", "1. ", "📊", "✅"]):
            # Contenido markdown/analisis → convertir a HTML ejecutivo
            parts.append(_format_analysis_as_html(_normalize_output(output_text)))
        else:
            parts.append(f"<pre>{_escape(str(output_text)[:8000])}</pre>")
    else:
        parts.append("<p><em>Sin output</em></p>")
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


def _format_data_as_html(output: str) -> str:
    """Convierte output de datos (section/campo=valor) en HTML tabular legible."""
    import re
    parts = ['<div style="font-family:monospace;font-size:13px;">']
    current_section = None
    rows = []
    
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Detectar sección
        section_match = re.match(r'[•·]\s*_section=(.+)', line)
        if section_match:
            if rows:
                parts.append(_render_table(rows))
                rows = []
            current_section = section_match.group(1).strip()
            parts.append(f'<h4 style="margin:12px 0 4px;color:#e94560;">📊 {_escape(current_section)}</h4>')
            continue
        # Detectar fila de datos: • key=value | key2=value2
        row_match = re.match(r'[•·]\s*(.+)', line)
        if row_match:
            fields = {}
            for pair in row_match.group(1).split("|"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    fields[k.strip()] = v.strip()
            if fields:
                rows.append(fields)
    
    if rows:
        parts.append(_render_table(rows))
    
    parts.append('</div>')
    return "\n".join(parts)


def _render_table(rows: list) -> str:
    """Renderiza una lista de dicts como tabla HTML."""
    if not rows:
        return ""
    cols = list(rows[0].keys())
    html = '<table style="border-collapse:collapse;width:100%;margin:4px 0 12px;font-size:12px;">'
    html += '<thead><tr style="background:#16213e;">'
    for c in cols:
        html += f'<th style="padding:4px 8px;text-align:left;color:#e94560;border-bottom:1px solid #333;">{_escape(c)}</th>'
    html += '</tr></thead><tbody>'
    for i, row in enumerate(rows):
        bg = "#1a1a2e" if i % 2 == 0 else "#16213e"
        html += f'<tr style="background:{bg};">'
        for c in cols:
            val = row.get(c, "")
            html += f'<td style="padding:4px 8px;border-bottom:1px solid #222;">{_escape(str(val)[:200])}</td>'
        html += '</tr>'
    html += '</tbody></table>'
    return html


def _format_analysis_as_html(output: str) -> str:
    """Convierte analisis markdown a HTML ejecutivo."""
    import re
    lines = output.split("\n")
    html = ['<div style="font-family:system-ui;line-height:1.6;color:#e0e0e0;">']
    in_code = False
    in_table = False
    table_rows = []
    
    for line in lines:
        stripped = line.strip()
        
        if stripped.startswith("```"):
            if in_code:
                html.append('</pre>')
                in_code = False
            else:
                html.append('<pre style="background:#0d1117;padding:8px;border-radius:4px;overflow-x:auto;font-size:12px;">')
                in_code = True
            continue
        
        if in_code:
            html.append(_escape(line) + '<br>')
            continue
        
        if not stripped:
            if table_rows:
                html.append(_render_table(table_rows))
                table_rows = []
                in_table = False
            continue
        
        if stripped.startswith('### '):
            html.append(f'<h4 style="color:#e94560;margin:12px 0 4px;">{_escape(stripped[4:])}</h4>')
            continue
        if stripped.startswith('## '):
            html.append(f'<h3 style="color:#e94560;margin:16px 0 6px;">{_escape(stripped[3:])}</h3>')
            continue
        if stripped.startswith('# '):
            html.append(f'<h2 style="color:#e94560;margin:16px 0 6px;">{_escape(stripped[2:])}</h2>')
            continue
        
        if stripped == '---':
            html.append('<hr style="border-color:#333;margin:12px 0;">')
            continue
        
        if re.match(r'^[-*]\s', stripped):
            content = _format_inline(stripped[2:])
            html.append(f'<li style="margin:2px 0;">{content}</li>')
            continue
        
        m = re.match(r'^(\d+)\.\s(.+)', stripped)
        if m:
            content = _format_inline(m.group(2))
            html.append(f'<li style="margin:2px 0;">{content}</li>')
            continue
        
        if stripped.startswith('- [x]') or stripped.startswith('- [X]'):
            html.append(f'<div style="margin:2px 0;">✅ {_format_inline(stripped[5:])}</div>')
            continue
        if stripped.startswith('- [ ]'):
            html.append(f'<div style="margin:2px 0;">⬜ {_format_inline(stripped[5:])}</div>')
            continue
        
        if '|' in stripped and stripped.count('|') >= 2:
            if not in_table:
                in_table = True
                table_rows = []
            cells = [c.strip() for c in stripped.split('|') if c.strip()]
            if not all(c.replace('-','').replace(':','') == '' for c in cells):
                table_rows.append({f'col{i}': c for i, c in enumerate(cells)})
            continue
        
        content = _format_inline(stripped)
        html.append(f'<p style="margin:4px 0;">{content}</p>')
    
    if table_rows:
        html.append(_render_table(table_rows))
    if in_code:
        html.append('</pre>')
    html.append('</div>')
    return "\n".join(html)


def _format_inline(text: str) -> str:
    """Convierte inline markdown a HTML."""
    import re
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong style="color:#e94560;">\1</strong>', text)
    text = re.sub(r'`([^`]+)`', r'<code style="background:#16213e;padding:1px 4px;border-radius:3px;">\1</code>', text)
    return text

def _normalize_output(text: str) -> str:
    """Convierte \\n literales a saltos de línea reales y limpia escapes JSON."""
    import re
    # Reemplazar \\n y \\t literales
    text = text.replace('\\n', '\n').replace('\\t', '  ')
    # Limpiar escapes dobles de JSON
    text = text.replace('\\\\n', '\n').replace('\\\\t', '  ')
    # Quitar comillas escapadas
    text = text.replace('\\"', '"')
    return text

def _extract_output_file(swarm_result: dict) -> str | None:
    """Extrae la ruta del archivo generado desde el resultado del swarm."""
    import json
    # Buscar en dispatch_results
    dispatch = swarm_result.get("dispatch_results", {})
    if isinstance(dispatch, str):
        try: dispatch = json.loads(dispatch)
        except: pass
    if not isinstance(dispatch, dict):
        return None
    for agent, data in dispatch.items():
        if not isinstance(data, dict):
            continue
        details = data.get("details", {})
        if isinstance(details, str):
            try: details = json.loads(details)
            except: pass
        if not isinstance(details, dict):
            continue
        # output_file directo
        f = details.get("output_file")
        if f and isinstance(f, str) and f.strip():
            return f.strip()
        # archivo_generado en rows
        for row in details.get("rows", []):
            if isinstance(row, dict):
                af = row.get("archivo_generado")
                if af and isinstance(af, str) and af.strip():
                    return af.strip()
    # Buscar en evidencia JSON (string plano)
    evidence = swarm_result.get("evidence", "")
    if isinstance(evidence, str) and "archivo_generado" in evidence:
        import re
        m = re.search(r'"archivo_generado"\s*:\s*"([^"]+)"', evidence)
        if m: return m.group(1)
    return None
