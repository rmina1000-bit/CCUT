"""[Admin v0] 중앙 관리자 콘솔 서비스 계층 — read-mostly.

원칙 (설계서 SPEC/CONTRACT 기준):
- 전 KPI는 실 DB 집계. 하드코딩 금지.
- 관리자 행동은 admin_audit_log에 append-only 기록.
- insights 질의는 로컬 hub(qwen2.5, engine.hub._ollama_json)로만 —
  mock 반환 금지, hub 미응답 시 정직하게 에러 반환.
- billing 계열은 daily_service_metrics 실집계 — 데이터 없으면 "준비 중".
"""
import os
import sqlite3
import datetime

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")

OPERATOR_ID = "CCUT_PRO"  # auth.manager.user_manager 실계정과 동일 키


def _connect():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    return con


def ensure_schema():
    """startup 자동 생성 — CREATE IF NOT EXISTS만, 기존 데이터 불변."""
    con = _connect()
    con.execute(
        """CREATE TABLE IF NOT EXISTS admin_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            target_type TEXT,
            target_id TEXT,
            note TEXT,
            created_at TEXT NOT NULL
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS admin_saved_queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_text TEXT NOT NULL,
            result_summary TEXT,
            created_at TEXT NOT NULL
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS daily_service_metrics (
            date_key TEXT NOT NULL,
            metric_key TEXT NOT NULL,
            metric_value REAL,
            PRIMARY KEY (date_key, metric_key)
        )"""
    )
    # [War Room v1] 운영 작업큐 — 삭제 API 금지, 닫기=status 전이(closed_at)
    con.execute(
        """CREATE TABLE IF NOT EXISTS admin_work_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            priority TEXT NOT NULL,
            target_type TEXT,
            target_id TEXT,
            assigned_ai_role TEXT,
            next_action TEXT,
            due_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            closed_at TEXT
        )"""
    )
    con.commit()
    con.close()


def audit_append(action, target_type=None, target_id=None, note=None):
    """append-only — 수정/삭제 API를 만들지 않는다 (구조원칙 3)."""
    con = _connect()
    con.execute(
        "INSERT INTO admin_audit_log (action, target_type, target_id, note, created_at)"
        " VALUES (?,?,?,?,?)",
        (action, target_type, target_id, note,
         datetime.datetime.now().isoformat()),
    )
    con.commit()
    con.close()


def _service_counts(con) -> dict:
    """전 KPI 실 DB 집계 — 단일 진실원."""
    def _one(sql):
        try:
            return con.execute(sql).fetchone()[0]
        except Exception:
            return None
    return {
        "source_count": _one("SELECT COUNT(*) FROM sources"),
        "program_count": _one("SELECT COUNT(*) FROM programs"),
        "proposal_count": _one("SELECT COUNT(*) FROM proposals"),
        "vault_event_count": _one("SELECT COUNT(*) FROM vault_events"),
        "fragment_vault_count": _one("SELECT COUNT(*) FROM fragment_vault"),
        "export_success_count": _one(
            "SELECT COUNT(*) FROM export_results WHERE status='RENDER_SUCCESS'"),
        "person_count": _one("SELECT COUNT(*) FROM persons"),
    }


def overview() -> dict:
    con = _connect()
    kpis = _service_counts(con)
    recent_audit = [
        {"id": r[0], "action": r[1], "target_type": r[2], "target_id": r[3],
         "note": r[4], "created_at": r[5]}
        for r in con.execute(
            "SELECT id, action, target_type, target_id, note, created_at"
            " FROM admin_audit_log ORDER BY id DESC LIMIT 5")
    ]
    latest_shot = con.execute(
        "SELECT MAX(shot_date) FROM sources WHERE shot_date IS NOT NULL"
    ).fetchone()[0]
    con.close()
    return {
        "kpis": kpis,
        "latest_shot_date": latest_shot,
        "recent_audit": recent_audit,
        "generated_at": datetime.datetime.now().isoformat(),
    }


def _operator_stats(con) -> dict:
    stats = _service_counts(con)
    first = con.execute("SELECT MIN(created_at) FROM sources").fetchone()[0]
    last = con.execute("SELECT MAX(last_updated_at) FROM programs").fetchone()[0]
    stats["first_activity"] = str(first) if first else None
    stats["last_activity"] = str(last) if last else None
    return stats


def users_list() -> dict:
    """로컬 단일 사용자 환경 — 운영자 1인 + 실사용 통계."""
    from auth.manager import user_manager
    con = _connect()
    stats = _operator_stats(con)
    con.close()
    u = user_manager.current_user
    return {
        "users": [{
            "user_id": u.get("id", OPERATOR_ID),
            "display_name": u.get("name"),
            "role": u.get("role"),
            "plan": u.get("status"),
            **stats,
        }],
        "total": 1,
        "environment": "local_single_user",
    }


def user_detail(user_id: str) -> dict:
    from auth.manager import user_manager
    u = user_manager.current_user
    if user_id != u.get("id", OPERATOR_ID):
        return {"status": "ERROR", "message": "user not found (로컬 단일 사용자 환경)"}
    con = _connect()
    stats = _operator_stats(con)
    notes = [
        {"id": r[0], "note": r[1], "created_at": r[2]}
        for r in con.execute(
            "SELECT id, note, created_at FROM admin_audit_log"
            " WHERE action='user_note' AND target_type='user' AND target_id=?"
            " ORDER BY id DESC LIMIT 20", (user_id,))
    ]
    con.close()
    return {
        "status": "OK",
        "user_id": u.get("id"),
        "display_name": u.get("name"),
        "role": u.get("role"),
        "plan": u.get("status"),
        "stats": stats,
        "operator_notes": notes,
    }


def add_user_note(user_id: str, note: str) -> dict:
    audit_append("user_note", target_type="user", target_id=user_id, note=note)
    return {"status": "OK", "user_id": user_id, "note": note}


def revenue_summary() -> dict:
    """daily_service_metrics 실집계 — 데이터 없으면 '준비 중' 정직 반환 (0 하드코딩 금지)."""
    con = _connect()
    rows = con.execute(
        "SELECT metric_key, COUNT(*), SUM(metric_value) FROM daily_service_metrics"
        " WHERE metric_key LIKE 'revenue%' GROUP BY metric_key"
    ).fetchall()
    total_days = con.execute(
        "SELECT COUNT(DISTINCT date_key) FROM daily_service_metrics").fetchone()[0]
    con.close()
    if not rows:
        return {
            "status": "준비 중",
            "total": None,
            "message": "구독 데이터 준비 중 — billing_accounts/subscription_events 미도입 (로컬 단일 사용자 환경)",
            "metric_days_recorded": total_days,
        }
    return {
        "status": "OK",
        "metrics": [
            {"metric_key": k, "days": n, "total": s} for k, n, s in rows
        ],
        "metric_days_recorded": total_days,
    }


def insights_query(query: str) -> dict:
    """운영 질의 → 실 DB 집계 컨텍스트 + 로컬 hub 판단. mock 금지.

    로컬 AI 원칙(SPEC §3.1): 원장 집계를 컨텍스트로 압축해 hub에 전달,
    hub가 답을 만든다. hub 미응답 시 정직하게 에러 반환."""
    con = _connect()
    ctx = _service_counts(con)
    latest_shot = con.execute(
        "SELECT MAX(shot_date) FROM sources WHERE shot_date IS NOT NULL").fetchone()[0]
    recent_exports = con.execute(
        "SELECT COUNT(*) FROM export_results WHERE status='RENDER_SUCCESS'"
        " AND created_at >= datetime('now','-7 day')").fetchone()[0]
    con.close()
    ctx["latest_shot_date"] = latest_shot
    ctx["exports_last_7d"] = recent_exports

    ctx_lines = "\n".join(f"- {k}: {v}" for k, v in ctx.items())
    prompt = (
        "너는 CCUT 영상 아카이브 서비스의 운영 보조 AI다.\n"
        "아래는 방금 실 DB에서 집계한 운영 지표다. 이 수치만 근거로 답하라.\n"
        "지표에 없는 수치는 지어내지 말고 '지표에 없음'이라고 말하라.\n"
        f"[운영 지표]\n{ctx_lines}\n\n"
        f"[운영자 질문]\n{query}\n\n"
        'JSON만 출력. 형식: {"answer": "한국어 답변 (수치 근거 포함, 3문장 이내)"}'
    )
    try:
        from engine.hub import _ollama_json
        res = _ollama_json(prompt, timeout=60)
        answer = (res or {}).get("answer")
        if not answer:
            raise ValueError("empty answer")
    except Exception as e:
        audit_append("insights_query_failed", target_type="query", note=f"{query} | {e}")
        return {"error": "hub 응답 없음", "query": query, "detail": str(e)}

    # 질의·결과를 원장에 남긴다 (재사용 가능한 형태로 저장 — 데이터 원칙 §1.3)
    con = _connect()
    con.execute(
        "INSERT INTO admin_saved_queries (query_text, result_summary, created_at)"
        " VALUES (?,?,?)",
        (query, answer[:500], datetime.datetime.now().isoformat()),
    )
    con.commit()
    con.close()
    audit_append("insights_query", target_type="query", note=query)

    return {
        "query": query,
        "result": answer,
        "sources_referenced": len(ctx),
        "context_used": ctx,
    }


# ═══════════════════════════════════════════════════════════════════
#   [War Room v1] 상황실 — 글로벌 상태등·경보·작전 큐 (전부 실 DB 규칙 기반)
# ═══════════════════════════════════════════════════════════════════

def _situation_alerts(con) -> list:
    """v1 경보 규칙 — 계약서(CONTRACT_V1 §2) 그대로. 전부 실 DB 조회."""
    alerts = []

    def _try(sql, params=()):
        try:
            return con.execute(sql, params).fetchone()[0]
        except Exception:
            return None

    render_failed_7d = _try(
        "SELECT COUNT(*) FROM export_results WHERE status='RENDER_FAILED'"
        " AND created_at >= datetime('now','-7 day')")
    if render_failed_7d is not None and render_failed_7d >= 3:
        alerts.append({
            "severity": "P1", "title": "렌더 실패 반복",
            "reason": f"최근 7일 렌더 실패 {render_failed_7d}건",
            "target_type": "export", "target_id": None,
            "recommended_action": "최근 실패 export_results의 ffmpeg_stderr 확인",
        })

    source_lost = _try("SELECT COUNT(*) FROM fragment_vault WHERE source_alive = 0")
    if source_lost:
        alerts.append({
            "severity": "P1", "title": "원본 유실 조각 존재",
            "reason": f"fragment_vault source_alive=0 {source_lost}건",
            "target_type": "vault", "target_id": None,
            "recommended_action": "아카이브 원본 실존 여부와 vault 정합 점검",
        })

    sec_p0 = _try(
        "SELECT COUNT(*) FROM admin_security_events WHERE status='open' AND severity='P0'")
    sec_rest = _try(
        "SELECT COUNT(*) FROM admin_security_events WHERE status='open' AND severity!='P0'")
    if sec_p0:
        alerts.append({
            "severity": "P0", "title": "미처리 P0 보안 이벤트",
            "reason": f"open P0 {sec_p0}건", "target_type": "security", "target_id": None,
            "recommended_action": "보안 관제에서 즉시 triage",
        })
    if sec_rest:
        alerts.append({
            "severity": "P2", "title": "미처리 보안 이벤트",
            "reason": f"open {sec_rest}건", "target_type": "security", "target_id": None,
            "recommended_action": "보안 관제에서 상태 정리",
        })

    support_high = _try(
        "SELECT COUNT(*) FROM admin_support_cases WHERE status='open' AND severity='high'")
    if support_high:
        alerts.append({
            "severity": "P1", "title": "고심각 문의 대기",
            "reason": f"open high {support_high}건",
            "target_type": "support", "target_id": None,
            "recommended_action": "지원/문의에서 우선 응대",
        })

    return alerts


def situation() -> dict:
    """상황실 홈 — 30초 안에 전군 파악. 원장 없는 항목은 null/빈 배열(하드코딩 금지)."""
    con = _connect()
    kpis = _service_counts(con)
    kpis["storage_bytes"] = None        # 저장소 원장 미도입 — 정직 null
    kpis["api_cost_estimate"] = None    # 비용 원장 미도입 — 정직 null

    alerts = _situation_alerts(con)
    severities = {a["severity"] for a in alerts}
    if "P0" in severities:
        level, reason = "critical", "P0 경보 존재"
    elif "P1" in severities:
        level, reason = "watch", "P1 경보 존재"
    else:
        level, reason = "normal", None

    try:
        action_queue = [
            {"kind": r[0], "title": r[1], "priority": r[2], "target": r[3]}
            for r in con.execute(
                "SELECT kind, title, priority, target_id FROM admin_work_items"
                " WHERE status != 'closed' ORDER BY priority, id DESC LIMIT 10")
        ]
    except Exception:
        action_queue = []  # 작업큐 원장 도입 전 — 빈 배열 정직 반환

    recent_audit = [
        {"id": r[0], "action": r[1], "target_type": r[2], "target_id": r[3],
         "note": r[4], "created_at": r[5]}
        for r in con.execute(
            "SELECT id, action, target_type, target_id, note, created_at"
            " FROM admin_audit_log ORDER BY id DESC LIMIT 5")
    ]
    con.close()
    return {
        "status": "OK",
        "generated_at": datetime.datetime.now().isoformat(),
        "global_state": {"service_level": level, "reason": reason},
        "kpis": kpis,
        "alerts": alerts,
        "action_queue": action_queue,
        "recent_audit": recent_audit,
    }


# ═══════════════════════════════════════════════════════════════════
#   [War Room v1] 운영 작업큐 — admin_work_items 원장
# ═══════════════════════════════════════════════════════════════════

_WORK_STATUSES = ("open", "in_progress", "blocked", "closed")
_WORK_KINDS = ("support", "security", "billing", "ops", "review")
_PRIORITIES = ("P0", "P1", "P2", "P3")


def work_items_list(status: str = "open", limit: int = 50) -> dict:
    limit = max(1, min(int(limit or 50), 100))
    con = _connect()
    sql = ("SELECT id, kind, title, status, priority, target_type, target_id,"
           " next_action, due_at, created_at, updated_at, closed_at"
           " FROM admin_work_items")
    params: tuple = ()
    if status and status != "all":
        sql += " WHERE status = ?"
        params = (status,)
    sql += " ORDER BY id DESC LIMIT ?"
    rows = con.execute(sql, params + (limit,)).fetchall()
    con.close()
    cols = ["id", "kind", "title", "status", "priority", "target_type", "target_id",
            "next_action", "due_at", "created_at", "updated_at", "closed_at"]
    return {"items": [dict(zip(cols, r)) for r in rows]}


def work_item_create(payload: dict) -> dict:
    kind = (payload.get("kind") or "ops").strip()
    title = (payload.get("title") or "").strip()
    priority = (payload.get("priority") or "P2").strip()
    if not title:
        return {"error": "title is required"}
    if kind not in _WORK_KINDS:
        return {"error": f"kind must be one of {_WORK_KINDS}"}
    if priority not in _PRIORITIES:
        return {"error": f"priority must be one of {_PRIORITIES}"}
    now = datetime.datetime.now().isoformat()
    con = _connect()
    cur = con.execute(
        "INSERT INTO admin_work_items (kind, title, status, priority, target_type,"
        " target_id, next_action, due_at, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (kind, title, "open", priority, payload.get("target_type"),
         payload.get("target_id"), payload.get("next_action"),
         payload.get("due_at"), now, now))
    item_id = cur.lastrowid
    con.commit()
    con.close()
    audit_append("work_item_create", target_type="work_item",
                 target_id=str(item_id), note=f"[{priority}/{kind}] {title}")
    return {"status": "OK", "id": item_id}


def work_item_transition(item_id: int, status: str, note: str = None) -> dict:
    if status not in _WORK_STATUSES:
        return {"error": f"status must be one of {_WORK_STATUSES}"}
    now = datetime.datetime.now().isoformat()
    con = _connect()
    row = con.execute("SELECT status, title FROM admin_work_items WHERE id=?",
                      (item_id,)).fetchone()
    if not row:
        con.close()
        return {"error": "work item not found"}
    closed_at = now if status == "closed" else None
    con.execute(
        "UPDATE admin_work_items SET status=?, updated_at=?, closed_at=?"
        " WHERE id=?", (status, now, closed_at, item_id))
    con.commit()
    con.close()
    audit_append("work_item_transition", target_type="work_item",
                 target_id=str(item_id),
                 note=f"{row[0]} → {status}" + (f" | {note}" if note else ""))
    return {"status": "OK", "id": item_id, "from": row[0], "to": status}


def audit_logs(limit: int = 20, cursor: int = None) -> dict:
    limit = max(1, min(int(limit or 20), 100))
    con = _connect()
    sql = ("SELECT id, action, target_type, target_id, note, created_at"
           " FROM admin_audit_log")
    params: tuple = ()
    if cursor:
        sql += " WHERE id < ?"
        params = (int(cursor),)
    sql += " ORDER BY id DESC LIMIT ?"
    params = params + (limit + 1,)
    rows = con.execute(sql, params).fetchall()
    con.close()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {
        "logs": [
            {"id": r[0], "action": r[1], "target_type": r[2], "target_id": r[3],
             "note": r[4], "created_at": r[5]} for r in rows
        ],
        "next_cursor": rows[-1][0] if (has_more and rows) else None,
    }
