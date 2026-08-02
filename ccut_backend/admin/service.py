"""[Admin v0] 중앙 관리자 콘솔 서비스 계층 — read-mostly.

원칙 (설계서 SPEC/CONTRACT 기준):
- 전 KPI는 실 DB 집계. 하드코딩 금지.
- 관리자 행동은 admin_audit_log에 append-only 기록.
- 관리자 AI 질의는 승인된 외부 provider로만 전송하며, 미설정 시 정직하게 실패한다.
- billing 계열은 daily_service_metrics 실집계 — 데이터 없으면 "준비 중".
"""
import os
import sqlite3
import datetime
import json
import base64
from pathlib import Path

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")
ENV_PATH = Path(BACKEND_DIR) / ".env"
API_PROVIDER_CONFIG = Path(BACKEND_DIR) / "config" / "admin_api_providers.json"
_API_KEY_CHECKS = {}
_API_KEY_PRIVATE_KEY = None

OPERATOR_ID = "CCUT_PRO"  # auth.manager.user_manager 실계정과 동일 키


def _connect():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    return con


def _api_providers():
    with API_PROVIDER_CONFIG.open("r", encoding="utf-8") as handle:
        return json.load(handle).get("providers", [])


def _api_provider(provider_id: str):
    return next(
        (item for item in _api_providers() if item.get("id") == provider_id),
        None,
    )


def _mask_secret(value: str) -> str:
    value = str(value or "")
    if not value:
        return ""
    prefix = value[:7] if len(value) > 11 else value[:3]
    return f"{prefix}…{value[-4:]}"


def _rsa_private_key():
    global _API_KEY_PRIVATE_KEY
    if _API_KEY_PRIVATE_KEY is None:
        from cryptography.hazmat.primitives.asymmetric import rsa
        _API_KEY_PRIVATE_KEY = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
    return _API_KEY_PRIVATE_KEY


def api_key_public_key() -> dict:
    from cryptography.hazmat.primitives import serialization
    public_key = _rsa_private_key().public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return {
        "algorithm": "RSA-OAEP-256",
        "public_key_pem": public_key.decode("ascii"),
    }


def _decrypt_api_key(ciphertext: str) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    try:
        encrypted = base64.b64decode(ciphertext, validate=True)
        value = _rsa_private_key().decrypt(
            encrypted,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        ).decode("utf-8").strip()
    except Exception as exc:
        raise ValueError("키 암호문을 해독할 수 없습니다") from exc
    if not value or len(value) > 512 or "\n" in value or "\r" in value:
        raise ValueError("키 형식이 올바르지 않습니다")
    return value


def _write_env_value(name: str, value: str):
    raw = ENV_PATH.read_bytes() if ENV_PATH.exists() else b""
    text = raw.decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    replacement = f"{name}={value}"
    replaced = False
    output = []
    for line in lines:
        if line.startswith(f"{name}="):
            if not replaced:
                output.append(replacement)
                replaced = True
            continue
        output.append(line)
    if not replaced:
        output.append(replacement)
    rendered = newline.join(output) + newline
    temp_path = ENV_PATH.with_suffix(".env.tmp")
    temp_path.write_bytes(rendered.encode("utf-8"))
    os.replace(temp_path, ENV_PATH)
    os.environ[name] = value


def api_key_status() -> dict:
    providers = []
    for item in _api_providers():
        provider_id = item["id"]
        value = os.getenv(item["env_key"], "").strip()
        check = _API_KEY_CHECKS.get(provider_id, {})
        # [LAB-52 ③] 키가 있다 ≠ 연결됐다. 구판은 문자열 존재만으로 "connected" 를 냈고,
        #   last_checked_at 이 null 인 채로 초록 배지가 떴다(실측 2026-07-30).
        #   실제 연결 테스트를 통과한 기록이 있을 때만 connected. 나머지는 unverified.
        checked_at = check.get("last_checked_at")
        if not value:
            connection = "unset"
        elif check.get("connection") == "error":
            connection = "error"
        elif check.get("connection") == "connected" and checked_at:
            connection = "connected"
        else:
            connection = "unverified"
        providers.append({
            "id": provider_id,
            "display_name": item["display_name"],
            "configured": bool(value),
            "masked_key": _mask_secret(value),
            "model": os.getenv(item.get("model_env", ""), "").strip() or None,
            "issue_url": item.get("issue_url"),
            "docs_url": item.get("docs_url"),
            "connection": connection,
            "verified": connection == "connected",
            "last_checked_at": checked_at,
            "error": check.get("error"),
        })
    return {"providers": providers}


def _api_key_error_message(exc: Exception) -> str:
    import httpx
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 401:
            return "401 인증 실패"
        if status == 429:
            return "429 사용 한도 또는 요청 한도 초과"
        if status == 404:
            return "404 모델 또는 API 경로를 찾을 수 없음"
        return f"API 오류 {status}"
    if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException)):
        return "네트워크 연결 실패"
    return "연결 테스트 실패"


def _anthropic_error_message(exc: Exception) -> str:
    import httpx
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            message = exc.response.json().get("error", {}).get("message")
        except (ValueError, AttributeError):
            message = None
        message = str(message or "")
        if "credit balance is too low" in message.lower():
            return "API 크레딧 잔액 부족"
        return message or _api_key_error_message(exc)
    return _api_key_error_message(exc)


def _test_anthropic_key(api_key: str) -> str:
    import httpx
    model = os.getenv("CCUT_ADMIN_LLM_MODEL", "").strip()
    if not model:
        raise ValueError("관리자 AI 모델 미설정")
    response = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "Reply OK."}],
        },
        timeout=15,
    )
    response.raise_for_status()
    return model


def api_key_test(provider_id: str, ciphertext: str = None) -> dict:
    provider = _api_provider(provider_id)
    if not provider:
        return {"error": "지원하지 않는 공급자"}
    api_key = (
        _decrypt_api_key(ciphertext)
        if ciphertext
        else os.getenv(provider["env_key"], "").strip()
    )
    if not api_key:
        return {"error": "미설정", "connection": "unset"}
    checked_at = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        if provider_id != "anthropic":
            raise ValueError("지원하지 않는 공급자")
        model = _test_anthropic_key(api_key)
        _API_KEY_CHECKS[provider_id] = {
            "connection": "connected",
            "last_checked_at": checked_at,
            "error": None,
        }
        return {
            "status": "connected",
            "model": model,
            "last_checked_at": checked_at,
        }
    except Exception as exc:
        error = _api_key_error_message(exc)
        _API_KEY_CHECKS[provider_id] = {
            "connection": "error",
            "last_checked_at": checked_at,
            "error": error,
        }
        return {
            "error": error,
            "connection": "error",
            "last_checked_at": checked_at,
        }


def api_key_save(provider_id: str, ciphertext: str) -> dict:
    provider = _api_provider(provider_id)
    if not provider:
        return {"error": "지원하지 않는 공급자"}
    value = _decrypt_api_key(ciphertext)
    _write_env_value(provider["env_key"], value)
    _API_KEY_CHECKS.pop(provider_id, None)
    return {
        "status": "saved",
        "provider": provider_id,
        "masked_key": _mask_secret(value),
    }


def api_key_connect(provider_id: str, ciphertext: str) -> dict:
    """Validate first, then persist. A failed key never reaches .env."""
    provider = _api_provider(provider_id)
    if not provider:
        return {"error": "지원하지 않는 공급자"}
    value = _decrypt_api_key(ciphertext)
    checked_at = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        if provider_id != "anthropic":
            raise ValueError("지원하지 않는 공급자")
        model = _test_anthropic_key(value)
    except Exception as exc:
        error = _api_key_error_message(exc)
        _API_KEY_CHECKS[provider_id] = {
            "connection": "error",
            "last_checked_at": checked_at,
            "error": error,
        }
        return {
            "error": error,
            "connection": "error",
            "last_checked_at": checked_at,
        }

    _write_env_value(provider["env_key"], value)
    _API_KEY_CHECKS[provider_id] = {
        "connection": "connected",
        "last_checked_at": checked_at,
        "error": None,
    }
    return {
        "status": "connected",
        "provider": provider_id,
        "model": model,
        "last_checked_at": checked_at,
        "masked_key": _mask_secret(value),
    }


def api_key_disconnect(provider_id: str) -> dict:
    provider = _api_provider(provider_id)
    if not provider:
        return {"error": "지원하지 않는 공급자"}
    _write_env_value(provider["env_key"], "")
    _API_KEY_CHECKS.pop(provider_id, None)
    return {"status": "disconnected", "provider": provider_id}


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
    # [War Room v1] 법무/수사공조 요청 원장 — v1 추출 기능 없음(요청 기록까지만)
    con.execute(
        """CREATE TABLE IF NOT EXISTS admin_legal_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requester TEXT NOT NULL,
            legal_basis TEXT,
            target_user_id TEXT,
            requested_range TEXT,
            status TEXT NOT NULL,
            data_scope_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            closed_at TEXT
        )"""
    )
    # [War Room v1] AI 실행 로그 — 역할·모델·성공/실패·시간 전부 기록
    con.execute(
        """CREATE TABLE IF NOT EXISTS admin_ai_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            model_key TEXT NOT NULL,
            status TEXT NOT NULL,
            input_summary TEXT,
            output_summary TEXT,
            error TEXT,
            duration_ms INTEGER,
            created_at TEXT NOT NULL
        )"""
    )
    # [War Room v1] 디자인/카피/메뉴 설정 원장 — 실반영은 후속, v1은 원장+상태만
    con.execute(
        """CREATE TABLE IF NOT EXISTS admin_surface_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            key TEXT NOT NULL,
            value_json TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    # [War Room v1] 구독/포인트/상품 원장 — provider 연동 전 "준비 중"
    con.execute(
        """CREATE TABLE IF NOT EXISTS admin_subscription_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            event_type TEXT NOT NULL,
            plan_code TEXT,
            amount REAL,
            currency TEXT,
            provider TEXT,
            raw_ref TEXT,
            created_at TEXT NOT NULL
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS admin_point_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            event_type TEXT NOT NULL,
            points INTEGER NOT NULL,
            reason TEXT,
            ref_type TEXT,
            ref_id TEXT,
            created_at TEXT NOT NULL
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS admin_products (
            product_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            price REAL,
            currency TEXT,
            config_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    # [War Room v1] 보안 이벤트 원장 — 자동 차단 금지, 상태 전이만
    con.execute(
        """CREATE TABLE IF NOT EXISTS admin_security_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            user_id TEXT,
            ip_hash TEXT,
            target_type TEXT,
            target_id TEXT,
            detail_json TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    # [War Room v1] 지원/문의 접수 큐 — 문의·불만·아이디어·버그 단일 원장
    con.execute(
        """CREATE TABLE IF NOT EXISTS admin_support_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            user_id TEXT,
            category TEXT,
            severity TEXT NOT NULL,
            status TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT,
            ai_summary TEXT,
            ai_tags TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
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
        # [NERVE-1] 조각 수는 테이블이 둘이다. 같은 이름으로 뭉치면 두 화면이 다른 수를 낸다
        #   (감사 C-2-c: 상황실 685 vs 편집연구실 812). 이름을 갈라 둘 다 보인다.
        "fragment_vault_count": _one("SELECT COUNT(*) FROM fragment_vault"),
        "semantic_fragment_count": _one("SELECT COUNT(*) FROM semantic_fragments"),
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

_PROBE_FAILED = object()   # 조회 실패 표식 — '값 없음(None)'과 절대 섞지 않는다.


def edit_capability() -> dict:
    """[NERVE-1] 편집 능력 요약 — 편집연구실 실측에서 필요한 수치만 가져온다.

    새 계산을 만들지 않는다. 판정 기준도 편집연구실과 같은 것을 쓴다
    (재료 결손 = non_null 0, ccut_backend/lab/audit.py:build_lab_context 와 동일).
    조회 실패는 status="UNKNOWN" 으로 정직하게 남긴다 — 0건으로 위장하지 않는다.
    """
    try:
        from lab.audit import get_audit
        audit = get_audit()
    except Exception as e:
        return {"status": "UNKNOWN", "error": str(e)}

    materials = [m for m in (audit.get("materials") or []) if isinstance(m, dict)]
    missing = [m for m in materials if not m.get("non_null")]
    rules = audit.get("rules") or {}
    techniques = audit.get("techniques") or {}
    edges = [e for e in (audit.get("edges") or []) if isinstance(e, dict)]
    return {
        "status": "OK",
        "audited_at": audit.get("audited_at"),
        "material_total": len(materials),
        "material_missing": len(missing),
        "material_missing_labels": [m.get("label") for m in missing],
        "rules_declared": rules.get("declared"),
        "rules_registered": rules.get("registered"),
        "rules_unregistered": rules.get("unregistered"),
        # [NERVE-1] 미배선 정의는 wireable_unwired 하나로 통일(국장 결정 2026-07-30).
        #   구 계산 declared-wired 는 모수가 어긋나 폐기.
        "techniques_scope": techniques.get("scope"),
        "techniques_wired": techniques.get("wired"),
        "techniques_active": techniques.get("active"),
        "techniques_wireable_unwired": techniques.get("wireable_unwired"),
        "edges_total": len(edges),
        "edges_broken": sum(1 for e in edges if e.get("status") == "BROKEN"),
        "evidence_missing": (audit.get("evidence_audit") or {}).get("missing"),
    }


def _situation_alerts(con):
    """v1 경보 규칙 — 계약서(CONTRACT_V1 §2) 그대로. 전부 실 DB 조회.

    [LAB-52 ①] 반환은 (alerts, probe_failures).
      구판은 조회 예외를 None 으로 삼키고 `if 값:` 으로 판정해, 경보 쿼리가 실패하면
      경보가 0건이 되고 상태등이 초록(normal)으로 떴다 — 측정 실패의 정상 위장.
      이제 실패는 실패로 세어 올려보내고, 판정은 호출부가 한다.
    """
    alerts = []
    probe_failures = []

    def _try(sql, probe, params=()):
        try:
            return con.execute(sql, params).fetchone()[0]
        except Exception as e:
            probe_failures.append({"probe": probe, "error": str(e)})
            return _PROBE_FAILED

    render_failed_7d = _try(
        "SELECT COUNT(*) FROM export_results WHERE status='RENDER_FAILED'"
        " AND created_at >= datetime('now','-7 day')", "render_failed_7d")
    if (render_failed_7d is not _PROBE_FAILED
            and render_failed_7d is not None and render_failed_7d >= 3):
        alerts.append({
            "severity": "P1", "title": "렌더 실패 반복",
            "reason": f"최근 7일 렌더 실패 {render_failed_7d}건",
            "target_type": "export", "target_id": None,
            "recommended_action": "최근 실패 export_results의 ffmpeg_stderr 확인",
        })

    source_lost = _try(
        "SELECT COUNT(*) FROM fragment_vault WHERE source_alive = 0", "source_lost")
    if source_lost is not _PROBE_FAILED and source_lost:
        alerts.append({
            "severity": "P1", "title": "원본 유실 조각 존재",
            "reason": f"fragment_vault source_alive=0 {source_lost}건",
            "target_type": "vault", "target_id": None,
            "recommended_action": "아카이브 원본 실존 여부와 vault 정합 점검",
        })

    sec_p0 = _try(
        "SELECT COUNT(*) FROM admin_security_events WHERE status='open' AND severity='P0'",
        "security_open_p0")
    sec_rest = _try(
        "SELECT COUNT(*) FROM admin_security_events WHERE status='open' AND severity!='P0'",
        "security_open_rest")
    if sec_p0 is not _PROBE_FAILED and sec_p0:
        alerts.append({
            "severity": "P0", "title": "미처리 P0 보안 이벤트",
            "reason": f"open P0 {sec_p0}건", "target_type": "security", "target_id": None,
            "recommended_action": "보안 관제에서 즉시 triage",
        })
    if sec_rest is not _PROBE_FAILED and sec_rest:
        alerts.append({
            "severity": "P2", "title": "미처리 보안 이벤트",
            "reason": f"open {sec_rest}건", "target_type": "security", "target_id": None,
            "recommended_action": "보안 관제에서 상태 정리",
        })

    support_high = _try(
        "SELECT COUNT(*) FROM admin_support_cases WHERE status='open' AND severity='high'",
        "support_open_high")
    if support_high is not _PROBE_FAILED and support_high:
        alerts.append({
            "severity": "P1", "title": "고심각 문의 대기",
            "reason": f"open high {support_high}건",
            "target_type": "support", "target_id": None,
            "recommended_action": "지원/문의에서 우선 응대",
        })

    return alerts, probe_failures


def _capability_alerts(cap: dict) -> list:
    """[NERVE-1] 편집 능력 결손을 경보로 올린다 — 운영이 초록인데 제작이 멈춘 상태를 덮지 않는다."""
    if cap.get("status") != "OK":
        return []
    alerts = []
    if cap.get("material_missing"):
        labels = ", ".join(l for l in (cap.get("material_missing_labels") or []) if l)
        alerts.append({
            # [NERVE-2] P1 -> P2 (국장 판정 2026-07-30). 결손 3종은 '미계측 확정'(측정기 없음)
            #   이라 매일 뜨는 상수 상태다. P1로 두면 상태등이 영구 watch 가 되어 경보 피로가
            #   생기고, 정작 새로 터진 P1을 덮는다. 사실은 그대로 P2 경보로 남긴다.
            "severity": "P2", "title": "편집 재료 결손",
            "reason": f"재료 {cap['material_missing']}/{cap['material_total']} 값 없음"
                      + (f" ({labels})" if labels else ""),
            "target_type": "edit_lab", "target_id": None,
            "recommended_action": "편집연구실에서 생산 경로 확인 — 값 없는 재료를 요구하는 기법은 잠긴다",
        })
    if cap.get("rules_unregistered"):
        alerts.append({
            "severity": "P2", "title": "검사기 없는 하드룰 선언",
            "reason": f"선언 {cap.get('rules_declared')} 중 미등록 {cap['rules_unregistered']}건",
            "target_type": "edit_lab", "target_id": None,
            "recommended_action": "편집연구실 하드룰 열에서 선언↔registry 대응 확인",
        })
    if cap.get("edges_broken"):
        alerts.append({
            "severity": "P2", "title": "끊긴 능력 간선",
            "reason": f"BROKEN 간선 {cap['edges_broken']}/{cap.get('edges_total')}건",
            "target_type": "edit_lab", "target_id": None,
            "recommended_action": "편집연구실 능력지도에서 BROKEN 간선 근거 확인",
        })
    return alerts


def situation() -> dict:
    """상황실 홈 — 30초 안에 전군 파악. 원장 없는 항목은 null/빈 배열(하드코딩 금지)."""
    con = _connect()
    kpis = _service_counts(con)
    kpis["storage_bytes"] = None        # 저장소 원장 미도입 — 정직 null
    kpis["api_cost_estimate"] = None    # 비용 원장 미도입 — 정직 null

    alerts, probe_failures = _situation_alerts(con)

    # [NERVE-1] 편집 능력(편집연구실 실측)을 상황실 판정에 합친다.
    #   구판은 운영 원장만 봐서, 재료 3종이 0/812인 동안에도 초록이었다(감사 C-1).
    capability = edit_capability()
    if capability.get("status") == "OK":
        alerts.extend(_capability_alerts(capability))
    else:
        probe_failures.append({
            "probe": "edit_capability",
            "error": capability.get("error") or "unknown",
        })

    # [LAB-52 ①] 점검 자체가 실패했으면 그 사실을 경보로 세운다 — 조용히 넘어가지 않는다.
    if probe_failures:
        alerts.append({
            "severity": "P1", "title": "경보 점검 실패",
            "reason": f"경보 규칙 {len(probe_failures)}건 조회 실패 — 해당 지표는 판정 불가",
            "target_type": "situation", "target_id": None,
            "recommended_action":
                "실패 항목 확인: " + ", ".join(f["probe"] for f in probe_failures),
        })

    severities = {a["severity"] for a in alerts}
    # 알려진 위험(P0)이 최우선. 그 다음이 '판정 불가'. 실패는 절대 normal 로 내려가지 않는다.
    if "P0" in severities:
        level, reason = "critical", "P0 경보 존재"
    elif probe_failures:
        level = "unknown"
        reason = f"경보 점검 {len(probe_failures)}건 실패 — 상태 판정 불가"
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
        "edit_capability": capability,
        "alerts": alerts,
        "probe_failures": probe_failures,
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


# ═══════════════════════════════════════════════════════════════════
#   [War Room v1] 지원/문의 — admin_support_cases + 로컬 AI 분류
# ═══════════════════════════════════════════════════════════════════

def _log_ai_run(role, model_key, status, input_summary=None,
                output_summary=None, error=None, duration_ms=None):
    """AI 실행 로그 — admin_ai_runs 도입(STEP 8) 전엔 조용히 무시(원장 없음)."""
    try:
        con = _connect()
        con.execute(
            "INSERT INTO admin_ai_runs (role, model_key, status, input_summary,"
            " output_summary, error, duration_ms, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (role, model_key, status,
             (input_summary or "")[:300], (output_summary or "")[:300],
             (str(error) if error else None), duration_ms,
             datetime.datetime.now().isoformat()))
        con.commit()
        con.close()
    except Exception:
        pass


def support_cases_list(status: str = "open", limit: int = 50) -> dict:
    limit = max(1, min(int(limit or 50), 100))
    con = _connect()
    sql = ("SELECT id, source, user_id, category, severity, status, title, body,"
           " ai_summary, ai_tags, created_at, updated_at FROM admin_support_cases")
    params: tuple = ()
    if status and status != "all":
        sql += " WHERE status = ?"
        params = (status,)
    sql += " ORDER BY id DESC LIMIT ?"
    rows = con.execute(sql, params + (limit,)).fetchall()
    con.close()
    cols = ["id", "source", "user_id", "category", "severity", "status", "title",
            "body", "ai_summary", "ai_tags", "created_at", "updated_at"]
    return {"cases": [dict(zip(cols, r)) for r in rows]}


def support_case_create(payload: dict) -> dict:
    title = (payload.get("title") or "").strip()
    if not title:
        return {"error": "title is required"}
    severity = (payload.get("severity") or "normal").strip()
    now = datetime.datetime.now().isoformat()
    con = _connect()
    cur = con.execute(
        "INSERT INTO admin_support_cases (source, user_id, category, severity,"
        " status, title, body, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        ((payload.get("source") or "manual").strip(), payload.get("user_id"),
         payload.get("category"), severity, "open", title,
         payload.get("body"), now, now))
    case_id = cur.lastrowid
    con.commit()
    con.close()
    audit_append("support_case_create", target_type="support_case",
                 target_id=str(case_id), note=f"[{severity}] {title}")
    return {"status": "OK", "id": case_id}


def support_case_note(case_id: int, note: str) -> dict:
    con = _connect()
    row = con.execute("SELECT id FROM admin_support_cases WHERE id=?",
                      (case_id,)).fetchone()
    con.close()
    if not row:
        return {"error": "case not found"}
    audit_append("support_case_note", target_type="support_case",
                 target_id=str(case_id), note=note)
    return {"status": "OK", "id": case_id}


def support_case_classify(case_id: int) -> dict:
    """로컬 AI만 사용(지시서 §STEP4). 분류 결과는 case에 저장 + audit."""
    import time as _time
    con = _connect()
    row = con.execute(
        "SELECT title, body FROM admin_support_cases WHERE id=?",
        (case_id,)).fetchone()
    con.close()
    if not row:
        return {"error": "case not found"}
    title, body = row
    prompt = (
        "너는 CCUT 서비스의 지원 문의 분류 담당이다.\n"
        f"[문의 제목] {title}\n[문의 내용] {body or '(본문 없음)'}\n\n"
        "이 문의를 분류하라. JSON만 출력:\n"
        '{"category": "complaint|idea|bug|question|abuse",'
        ' "severity": "low|normal|high",'
        ' "summary": "한국어 1문장 요약",'
        ' "tags": ["짧은 태그", ...]}'
    )
    t0 = _time.time()
    try:
        from engine.hub import _ollama_json, HUB_MODEL
        res = _ollama_json(prompt, timeout=60)
        if not res or not res.get("category"):
            raise ValueError("empty classification")
    except Exception as e:
        _log_ai_run("support_classify", "local_hub", "failed",
                    input_summary=title, error=e,
                    duration_ms=int((_time.time() - t0) * 1000))
        return {"error": "hub 응답 없음", "detail": str(e)}
    duration = int((_time.time() - t0) * 1000)

    import json as _json
    tags = _json.dumps(res.get("tags") or [], ensure_ascii=False)
    now = datetime.datetime.now().isoformat()
    con = _connect()
    con.execute(
        "UPDATE admin_support_cases SET category=?, severity=?, ai_summary=?,"
        " ai_tags=?, updated_at=? WHERE id=?",
        (res.get("category"), res.get("severity") or "normal",
         res.get("summary"), tags, now, case_id))
    con.commit()
    con.close()
    _log_ai_run("support_classify", "local_hub", "ok", input_summary=title,
                output_summary=res.get("summary"), duration_ms=duration)
    audit_append("support_case_classify", target_type="support_case",
                 target_id=str(case_id),
                 note=f"{res.get('category')}/{res.get('severity')}: {res.get('summary')}")
    return {"status": "OK", "id": case_id, **res}


# ═══════════════════════════════════════════════════════════════════
#   [War Room v1] 보안 관제 — admin_security_events (자동 차단 금지)
# ═══════════════════════════════════════════════════════════════════

_SEC_STATUSES = ("open", "triaged", "closed")


def security_events_list(status: str = "open", limit: int = 50) -> dict:
    limit = max(1, min(int(limit or 50), 100))
    con = _connect()
    sql = ("SELECT id, event_type, severity, user_id, target_type, target_id,"
           " detail_json, status, created_at FROM admin_security_events")
    params: tuple = ()
    if status and status != "all":
        sql += " WHERE status = ?"
        params = (status,)
    sql += " ORDER BY id DESC LIMIT ?"
    rows = con.execute(sql, params + (limit,)).fetchall()
    con.close()
    cols = ["id", "event_type", "severity", "user_id", "target_type", "target_id",
            "detail_json", "status", "created_at"]
    return {"events": [dict(zip(cols, r)) for r in rows]}


def security_event_create(payload: dict) -> dict:
    event_type = (payload.get("event_type") or "").strip()
    if not event_type:
        return {"error": "event_type is required"}
    severity = (payload.get("severity") or "P2").strip()
    if severity not in _PRIORITIES:
        return {"error": f"severity must be one of {_PRIORITIES}"}
    con = _connect()
    cur = con.execute(
        "INSERT INTO admin_security_events (event_type, severity, user_id, ip_hash,"
        " target_type, target_id, detail_json, status, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (event_type, severity, payload.get("user_id"), payload.get("ip_hash"),
         payload.get("target_type"), payload.get("target_id"),
         payload.get("detail_json"), "open",
         datetime.datetime.now().isoformat()))
    event_id = cur.lastrowid
    con.commit()
    con.close()
    audit_append("security_event_create", target_type="security_event",
                 target_id=str(event_id), note=f"[{severity}] {event_type}")
    return {"status": "OK", "id": event_id}


def security_event_status(event_id: int, status: str) -> dict:
    if status not in _SEC_STATUSES:
        return {"error": f"status must be one of {_SEC_STATUSES}"}
    con = _connect()
    row = con.execute("SELECT status, event_type FROM admin_security_events WHERE id=?",
                      (event_id,)).fetchone()
    if not row:
        con.close()
        return {"error": "security event not found"}
    con.execute("UPDATE admin_security_events SET status=? WHERE id=?",
                (status, event_id))
    con.commit()
    con.close()
    audit_append("security_event_status", target_type="security_event",
                 target_id=str(event_id), note=f"{row[0]} → {status} ({row[1]})")
    return {"status": "OK", "id": event_id, "from": row[0], "to": status}


# ═══════════════════════════════════════════════════════════════════
#   [War Room v1] 수익/구독/포인트 — 상품 카탈로그 + 포인트 원장
# ═══════════════════════════════════════════════════════════════════

_PRODUCT_STATUSES = ("draft", "approved", "published", "retired")


def products_list() -> dict:
    con = _connect()
    rows = con.execute(
        "SELECT product_id, kind, name, status, price, currency, config_json,"
        " created_at, updated_at FROM admin_products ORDER BY created_at DESC"
    ).fetchall()
    con.close()
    cols = ["product_id", "kind", "name", "status", "price", "currency",
            "config_json", "created_at", "updated_at"]
    return {"products": [dict(zip(cols, r)) for r in rows]}


def product_create(payload: dict) -> dict:
    product_id = (payload.get("product_id") or "").strip()
    kind = (payload.get("kind") or "").strip()
    name = (payload.get("name") or "").strip()
    if not product_id or not kind or not name:
        return {"error": "product_id, kind, name are required"}
    now = datetime.datetime.now().isoformat()
    con = _connect()
    dup = con.execute("SELECT 1 FROM admin_products WHERE product_id=?",
                      (product_id,)).fetchone()
    if dup:
        con.close()
        return {"error": "product_id already exists"}
    con.execute(
        "INSERT INTO admin_products (product_id, kind, name, status, price,"
        " currency, config_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (product_id, kind, name, "draft", payload.get("price"),
         payload.get("currency"), payload.get("config_json"), now, now))
    con.commit()
    con.close()
    audit_append("product_create", target_type="product", target_id=product_id,
                 note=f"[draft/{kind}] {name}")
    return {"status": "OK", "product_id": product_id}


def product_status(product_id: str, status: str) -> dict:
    """공개(published)는 승인 상태 전이 필수 — draft에서 바로 published 금지."""
    if status not in _PRODUCT_STATUSES:
        return {"error": f"status must be one of {_PRODUCT_STATUSES}"}
    con = _connect()
    row = con.execute("SELECT status, name FROM admin_products WHERE product_id=?",
                      (product_id,)).fetchone()
    if not row:
        con.close()
        return {"error": "product not found"}
    if status == "published" and row[0] != "approved":
        con.close()
        return {"error": "published 전이는 approved 상태에서만 가능 (승인 단계 필수)"}
    con.execute(
        "UPDATE admin_products SET status=?, updated_at=? WHERE product_id=?",
        (status, datetime.datetime.now().isoformat(), product_id))
    con.commit()
    con.close()
    audit_append("product_status", target_type="product", target_id=product_id,
                 note=f"{row[0]} → {status} ({row[1]})")
    return {"status": "OK", "product_id": product_id, "from": row[0], "to": status}


def points_summary() -> dict:
    con = _connect()
    rows = con.execute(
        "SELECT event_type, COUNT(*), SUM(points) FROM admin_point_events"
        " GROUP BY event_type").fetchall()
    con.close()
    if not rows:
        return {"status": "준비 중", "total": None,
                "message": "포인트 원장 비어 있음 — 포인트 정책 도입 전"}
    return {"status": "OK",
            "by_type": [{"event_type": t, "count": n, "points": p} for t, n, p in rows]}


# ═══════════════════════════════════════════════════════════════════
#   [War Room v1] 디자인/카피/메뉴 제어 — admin_surface_configs
# ═══════════════════════════════════════════════════════════════════

_CONFIG_STATUSES = ("draft", "approved", "retired")


def design_configs_list() -> dict:
    con = _connect()
    rows = con.execute(
        "SELECT id, scope, key, value_json, status, created_at, updated_at"
        " FROM admin_surface_configs ORDER BY id DESC LIMIT 100").fetchall()
    con.close()
    cols = ["id", "scope", "key", "value_json", "status", "created_at", "updated_at"]
    return {"configs": [dict(zip(cols, r)) for r in rows]}


def design_config_create(payload: dict) -> dict:
    """텍스트/플래그 설정만 — 자유 HTML 입력 금지(지시서 §STEP7)."""
    scope = (payload.get("scope") or "").strip()
    key = (payload.get("key") or "").strip()
    value_json = payload.get("value_json")
    if not scope or not key or value_json is None:
        return {"error": "scope, key, value_json are required"}
    import json as _json
    if isinstance(value_json, (dict, list)):
        value_str = _json.dumps(value_json, ensure_ascii=False)
    else:
        value_str = str(value_json)
    if "<" in value_str and ">" in value_str:
        return {"error": "HTML 입력 금지 — 텍스트/플래그 값만 허용"}
    now = datetime.datetime.now().isoformat()
    con = _connect()
    cur = con.execute(
        "INSERT INTO admin_surface_configs (scope, key, value_json, status,"
        " created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (scope, key, value_str, "draft", now, now))
    config_id = cur.lastrowid
    con.commit()
    con.close()
    audit_append("design_config_create", target_type="surface_config",
                 target_id=str(config_id), note=f"{scope}.{key} = {value_str[:80]}")
    return {"status": "OK", "id": config_id}


def design_config_status(config_id: int, status: str) -> dict:
    if status not in _CONFIG_STATUSES:
        return {"error": f"status must be one of {_CONFIG_STATUSES}"}
    con = _connect()
    row = con.execute(
        "SELECT status, scope, key FROM admin_surface_configs WHERE id=?",
        (config_id,)).fetchone()
    if not row:
        con.close()
        return {"error": "config not found"}
    con.execute(
        "UPDATE admin_surface_configs SET status=?, updated_at=? WHERE id=?",
        (status, datetime.datetime.now().isoformat(), config_id))
    con.commit()
    con.close()
    audit_append("design_config_status", target_type="surface_config",
                 target_id=str(config_id),
                 note=f"{row[0]} → {status} ({row[1]}.{row[2]})")
    return {"status": "OK", "id": config_id, "from": row[0], "to": status}


# ═══════════════════════════════════════════════════════════════════
#   [War Room v1] AI 운영실 — 역할별 Anthropic 질의 + 실행 로그
# ═══════════════════════════════════════════════════════════════════

_AI_ROLES = ("ops_brief", "support_classify", "security_triage",
             "strategy_advice", "copy_suggest")

# [ADMIN-AI-UNMUZZLE 2026-08-02] 재갈 전면 해제 (국장 지시: "오히려 다 풀어줘").
#   구판 이력: "지표만 근거로" → (B-3) 판단 허용 → 지금 전면 해제.
#   B-3 까지도 남아 있던 것은 '지표에 없으면 못 본다'는 전제였다. 그 전제 때문에
#   AI 가 국장에게 심부름을 시켰다 — "확인해서 알려주시면 판단해드릴게요".
#   이제 손(admin/ai_tools.py)이 있으므로 그 전제 자체가 사라진다.
_ROLE_PROMPTS = {
    "ops_brief": "너는 CCUT 운영을 함께 보는 참모다. 운영자와 대화하며 상태를 파악하고 판단을 말한다.",
    "support_classify": "너는 지원 문의 분류 담당이다. 질문 내용을 분류·요약하고 판단을 말한다.",
    "security_triage": "너는 보안 이벤트 triage 담당이다. 위험도를 판정하고 첫 조치를 제안한다.",
    "strategy_advice": "너는 서비스 전략 참모다. 데이터를 직접 확인하고 방향을 조언한다.",
    "copy_suggest": "너는 UI 문구 제안 담당이다. 짧고 조용한 한국어 운영 도구 톤으로 제안한다.",
}


def ai_status() -> dict:
    """관리자 AI 설정 상태. 키 값은 응답하거나 로그로 남기지 않는다."""
    provider = os.getenv("CCUT_ADMIN_LLM_PROVIDER", "").strip()
    model = os.getenv("CCUT_ADMIN_LLM_MODEL", "").strip()
    configured = provider == "anthropic" and bool(model) and bool(
        os.getenv("ANTHROPIC_API_KEY", "").strip()
    )
    provider_check = _API_KEY_CHECKS.get(provider, {})
    connection = provider_check.get("connection")
    con = _connect()
    try:
        total, failed = con.execute(
            "SELECT COUNT(*), SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END)"
            " FROM admin_ai_runs").fetchone()
    except Exception:
        total, failed = 0, 0
    con.close()
    return {
        "provider": provider or None,
        "model": model or None,
        "configured": configured,
        "status": (
            provider_check.get("error")
            if connection == "error"
            else ("ready" if configured else "관리자 AI 미설정")
        ),
        "runs_total": total or 0,
        "runs_failed": failed or 0,
        "roles": list(_AI_ROLES),
    }


def ai_runs(limit: int = 50) -> dict:
    limit = max(1, min(int(limit or 50), 100))
    con = _connect()
    try:
        rows = con.execute(
            "SELECT id, role, model_key, status, input_summary, output_summary,"
            " error, duration_ms, created_at FROM admin_ai_runs"
            " ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    except Exception:
        rows = []
    con.close()
    cols = ["id", "role", "model_key", "status", "input_summary", "output_summary",
            "error", "duration_ms", "created_at"]
    return {"runs": [dict(zip(cols, r)) for r in rows]}


def _lab_transfer_context(context: dict) -> dict:
    audit = context.get("audit") if isinstance(context.get("audit"), dict) else {}
    materials = [
        {
            key: item.get(key)
            for key in (
                "id", "label", "non_null", "total", "distinct",
                "producers", "consumers",
            )
        }
        for item in audit.get("materials", [])
        if isinstance(item, dict)
    ]
    rule_block = audit.get("rules") if isinstance(audit.get("rules"), dict) else {}
    rule_items = [
        item for item in rule_block.get("items", [])
        if isinstance(item, dict)
    ]
    config_rule_ids = [
        item.get("id") for item in rule_items
        if str(item.get("declared_in") or "").startswith(
            "ccut_backend/config/production_hard_rules.json:"
        )
    ]
    registry_rule_ids = list(rule_block.get("registered_ids") or [])
    technique_block = (
        audit.get("techniques")
        if isinstance(audit.get("techniques"), dict)
        else {}
    )
    technique_items = [
        {
            key: item.get(key)
            for key in (
                "id", "wired", "requires_materials", "requires_rules",
            )
        }
        for item in technique_block.get("items", [])
        if isinstance(item, dict)
        and str(item.get("declared_in") or "").startswith(
            "ccut_backend/config/editing_techniques.json:"
        )
    ]
    edges = [
        {
            key: edge.get(key)
            for key in ("from", "to", "kind", "status", "evidence")
        }
        for edge in audit.get("edges", [])
        if isinstance(edge, dict)
    ]
    status_counts = {
        status: sum(1 for edge in edges if edge.get("status") == status)
        for status in ("LIVE", "LOCKED", "BROKEN", "UNDECLARED")
    }
    return {
        "screen": "편집연구실",
        "materials": materials,
        "rules": {
            "config_declared_ids": config_rule_ids,
            "registry_registered_ids": registry_rule_ids,
            "intersection_ids": sorted(set(config_rule_ids) & set(registry_rule_ids)),
        },
        "techniques": technique_items,
        "wired_technique_ids": list(technique_block.get("wired_ids") or []),
        "edges": edges,
        "status_summary": {
            **status_counts,
            # [NERVE-1] 미배선 정의 통일(국장 결정 2026-07-30) — wireable_unwired 하나만 쓴다.
            #   구 계산 declared-wired 는 declared 에 모수 밖 기법(사용자 전용·인프라·룰 후보)이
            #   섞이고 wired 에는 declared 에 없는 as_is 가 들어가 모집단이 어긋났다(실측 24 vs 2).
            "wireable_unwired_techniques": technique_block.get("wireable_unwired"),
        },
        "omitted": {
            "materials": max(0, len(audit.get("materials", [])) - len(materials)),
            "rules": max(0, len(rule_items) - len(config_rule_ids) - len(registry_rule_ids)),
            "techniques": max(
                0,
                len(technique_block.get("items", [])) - len(technique_items) - 1,
            ),
            "edges": max(0, len(audit.get("edges", [])) - len(edges)),
        },
    }


# [ADMIN-AI-UNMUZZLE 2026-08-02] 남기는 것은 규율 하나뿐 (국장 지시 2-2 원문).
#   ★ 이것은 재갈이 아니다. 국장이 Claude·실행자에게 똑같이 거는 규율이다.
#     재갈은 "생각하지 마라"고 말하고, 규율은 "말할 때 근거의 성격을 밝히라"고 말한다.
_JUDGMENT_RULES = (
    "원인이나 판단을 말할 때 앞에 '측정했습니다' 또는 '추정입니다'를 붙인다.\n"
    "모르면 모른다고 하되, 알아볼 수 있으면 직접 알아본 뒤 말한다.\n"
)

# [ADMIN-AI-UNMUZZLE 3] 손을 달았으므로 그 사실을 알린다.
#   구판은 '주어진 지표가 세상의 전부'인 줄 알았다. 그래서 없는 수치를 물으면
#   운영자에게 확인을 부탁했다 — 국장은 실행자가 아니다.
_TOOL_RULES = (
    "너에게는 이 시스템을 직접 들여다보는 도구가 있다.\n"
    "- db_query: 운영 DB 에 SELECT. 어느 테이블이든 본다. 스키마를 모르면 "
    "sqlite_master 부터 조회하라.\n"
    "- read_log: 백엔드 로그를 읽는다.\n"
    "- read_file: 프로젝트 소스·설정·문서를 읽는다.\n"
    "아래 [운영 지표]는 출발점일 뿐 전부가 아니다. 지표에 없는 것을 물으면 "
    "운영자에게 확인을 부탁하지 말고 네가 직접 조회해서 답하라.\n"
    "한 번 조회해서 부족하면 결과를 보고 다시 조회하라. 답을 지어내는 것보다 "
    "한 번 더 조회하는 편이 낫다.\n"
)


def _build_admin_prompt(role: str, query: str, context: dict = None) -> tuple[str, str, dict]:
    """[ADMIN-AI-LIVE B-2] (system, user, transmitted) 로 가른다.

    왜 가르는가: 구판은 역할·규칙·지표·질문·출력계약을 user 메시지 하나에 뭉쳤다.
      그 상태로 대화를 이으면 지표와 계약이 매 턴 history 에 중복 적재되고,
      모델이 '지난 턴의 지표'와 '이번 턴의 지표'를 두 개의 사실로 읽는다.
      고정값(역할·규칙·지표)은 system 으로 올리고 messages 에는 대화만 남긴다.
    """
    is_lab = bool(context and context.get("screen") == "편집연구실")
    if is_lab:
        transmitted = _lab_transfer_context(context)
        context_rules = "화면 이름을 그대로 되받지 마라.\n"
    else:
        con = _connect()
        transmitted = _service_counts(con)
        con.close()
        context_rules = ""
    payload_text = (
        json.dumps(transmitted, ensure_ascii=False, separators=(",", ":"))
        if is_lab
        else "\n".join(f"- {key}: {value}" for key, value in transmitted.items())
    )
    # [UNMUZZLE 2-1] 삭제한 것: "지표만을 근거로", "지표에 없는 수치는 답하지 않는다",
    #   "N문장 이내", 'JSON만 출력' 출력계약. 앞의 셋은 생각을 막았고, JSON 계약은
    #   도구 왕복(tool_use 블록)과 양립하지 않는다 — 답변이 통째로 버려지는 경로였다.
    system_text = (
        f"{_ROLE_PROMPTS[role]}\n"
        f"{context_rules}"
        f"{_JUDGMENT_RULES}"
        f"{_TOOL_RULES}"
        "앞선 대화가 있으면 기억하고 이어서 답한다. 한국어로 답한다.\n\n"
        f"[운영 지표 — 출발점]\n{payload_text}"
    )
    return system_text, query, transmitted


# [ADMIN-AI-LIVE 2026-08-02 B-2] 대화로 실어 보내는 최근 턴 수.
#   근거(실측): system 에 올라가는 운영 지표는 9줄(_service_counts) — 100토큰 내외.
#   응답은 output_summary 저장 한도와 같은 300자(≈200토큰) 규모.
#   8턴이면 (질문 60 + 답 200) x 8 ≈ 2,100토큰 + 지표·규칙 300 ≈ 2,400토큰.
#   max_tokens 1000 을 더해도 컨텍스트 여유가 크고, 8턴이면 국장이 화면에서
#   되짚는 범위(패널이 보관하는 10건)를 실질적으로 덮는다.
ADMIN_AI_HISTORY_TURNS = 8


# [ADMIN-AI-UNMUZZLE 3] 도구 왕복 상한.
#   1차 8회 → 2차 16회. 올린 근거는 추정이 아니라 실측이다:
#   실증 케이스 "저 173개 제안은 뭐야?" 가 8회 상한에 **걸렸다**(tool_calls=18, 76초).
#   AI 는 DB 를 18번 조회해 "A/B 쌍이라 173(홀수)이 된 시점은 없다"까지 밝혀냈지만,
#   그 숫자를 표시한 화면 소스를 read_file 로 찾기 전에 상한에 걸려 국장에게 되물었다.
#   손을 달아놓고 상한으로 심부름을 시키게 만든 셈이라 올린다.
#   ★ 상한에 걸리면 조용히 멈추지 않는다 — 몇 번 돌았고 무엇을 못 봤는지 답변에 실어 보낸다.
ADMIN_AI_MAX_TOOL_ROUNDS = 16


def _anthropic_admin_query(system_text: str, user_text: str,
                           history: list = None) -> tuple[str, str, dict]:
    """[UNMUZZLE] 도구를 쥐여준 채 왕복시킨다.

    구판은 1회 호출로 끝났고 출력이 JSON {"answer":...} 이 아니면 답을 통째로 버렸다.
    도구를 달면 응답에 tool_use 블록이 섞이므로 그 계약은 성립하지 않는다 — 걷어냈다.
    반환: (answer, model, trace) — trace 는 실제로 무엇을 조회했는지의 기록이다.
    """
    provider = os.getenv("CCUT_ADMIN_LLM_PROVIDER", "").strip()
    model = os.getenv("CCUT_ADMIN_LLM_MODEL", "").strip()
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if provider != "anthropic" or not model or not api_key:
        raise RuntimeError("관리자 AI 미설정")

    from admin import ai_tools

    # [B-2] 이전 대화 → messages. 형식이 어긋난 항목은 조용히 버리지 않고 개수를 로그로 남긴다.
    messages = []
    skipped = 0
    for turn in (history or [])[-ADMIN_AI_HISTORY_TURNS:]:
        if not isinstance(turn, dict):
            skipped += 1
            continue
        q = str(turn.get("query") or "").strip()
        a = str(turn.get("result") or "").strip()
        if not q or not a:
            skipped += 1          # 실패한 턴(error)은 대화에 넣지 않는다
            continue
        messages.append({"role": "user", "content": q})
        messages.append({"role": "assistant", "content": a})
    if skipped:
        print(f"[ADMIN-AI] history 항목 {skipped}건 제외(형식 불일치·실패 턴)")
    messages.append({"role": "user", "content": user_text})

    import httpx
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    trace = {"tool_calls": 0, "rounds": 0, "calls": [], "hit_round_limit": False}

    for _round in range(ADMIN_AI_MAX_TOOL_ROUNDS):
        trace["rounds"] = _round + 1
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json={
                "model": model,
                "max_tokens": 4000,
                "system": system_text,
                "messages": messages,
                "tools": ai_tools.TOOL_DEFS,
            },
            timeout=180,
        )
        response.raise_for_status()
        body = response.json()
        content = body.get("content", []) or []
        text = "".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        ).strip()

        if body.get("stop_reason") != "tool_use":
            if not text:
                raise ValueError("empty Anthropic response")
            return text, model, trace

        # 도구를 부르겠다고 했다 — 실제로 실행해 결과를 되돌려준다.
        messages.append({"role": "assistant", "content": content})
        results = []
        for block in content:
            if not (isinstance(block, dict) and block.get("type") == "tool_use"):
                continue
            name = block.get("name")
            args = block.get("input") or {}
            out = ai_tools.run(name, args)
            trace["tool_calls"] += 1
            trace["calls"].append({
                "tool": name,
                "input": args,
                "output_chars": len(out),
                "is_error": '"error"' in out[:200],
            })
            print(f"[ADMIN-AI][TOOL] {name} {json.dumps(args, ensure_ascii=False)[:200]} "
                  f"-> {len(out)}자", flush=True)
            results.append({
                "type": "tool_result",
                "tool_use_id": block.get("id"),
                "content": out,
            })
        messages.append({"role": "user", "content": results})

    # 상한 도달 — 조용히 끝내지 않는다. 마지막으로 도구 없이 한 번 정리시킨다.
    trace["hit_round_limit"] = True
    print(f"[ADMIN-AI][TOOL-LIMIT] {ADMIN_AI_MAX_TOOL_ROUNDS}회 왕복 상한 도달", flush=True)
    messages.append({
        "role": "user",
        "content": (f"도구 왕복 상한({ADMIN_AI_MAX_TOOL_ROUNDS}회)에 도달했다. "
                    "지금까지 조회한 것만으로 답하고, 아직 확인하지 못한 것이 있으면 "
                    "무엇을 못 봤는지 밝혀라."),
    })
    response = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers=headers,
        json={"model": model, "max_tokens": 4000,
              "system": system_text, "messages": messages},
        timeout=180,
    )
    response.raise_for_status()
    text = "".join(
        b.get("text", "") for b in (response.json().get("content", []) or [])
        if isinstance(b, dict) and b.get("type") == "text"
    ).strip()
    if not text:
        raise ValueError("empty Anthropic response")
    return text, model, trace


def ai_query(role: str, query: str, context: dict = None, record: bool = True,
             history: list = None) -> dict:
    """역할별 관리자 API 질의. EDIT LAB은 실행·감사 로그를 남기지 않는다.

    [ADMIN-AI-LIVE B-2] history: 프론트가 들고 있는 이전 대화
      ([{query, result}, ...] 오래된 것부터). 없으면 구판과 같은 단발 질의다 —
      기존 호출자는 손대지 않아도 그대로 동작한다.
    """
    import time as _time
    if role not in _AI_ROLES:
        return {"error": f"role must be one of {_AI_ROLES}"}

    system_text, user_text, transmitted = _build_admin_prompt(role, query, context)
    t0 = _time.time()
    try:
        answer, model, tool_trace = _anthropic_admin_query(system_text, user_text, history)
    except Exception as e:
        error = (
            "관리자 AI 미설정"
            if str(e) == "관리자 AI 미설정"
            else _anthropic_error_message(e)
        )
        if os.getenv("CCUT_ADMIN_LLM_PROVIDER", "").strip() == "anthropic":
            _API_KEY_CHECKS["anthropic"] = {
                "connection": "error",
                "last_checked_at": datetime.datetime.now().astimezone().isoformat(
                    timespec="seconds"
                ),
                "error": error,
            }
        if record:
            _log_ai_run(role, "admin_anthropic", "failed", input_summary=query, error=e,
                        duration_ms=int((_time.time() - t0) * 1000))
        return {"error": error, "role": role}
    duration = int((_time.time() - t0) * 1000)
    if record:
        _log_ai_run(role, model, "ok", input_summary=query,
                    output_summary=answer, duration_ms=duration)
        audit_append("ai_query", target_type="ai_run", note=f"[{role}] {query}")
    return {"role": role, "query": query, "result": answer,
            "duration_ms": duration,
            "sources_referenced": len(transmitted),
            # [B-2] 이번 답이 몇 턴을 기억하고 나왔는지 — 화면·검증이 확인할 수 있게.
            "turns_carried": min(len([
                t for t in (history or [])
                if isinstance(t, dict) and t.get("query") and t.get("result")
            ]), ADMIN_AI_HISTORY_TURNS),
            # [UNMUZZLE 3] 무엇을 직접 조회했는지 — 심부름을 시켰는지 스스로 봤는지가 여기서 갈린다.
            "tool_calls": tool_trace.get("tool_calls", 0),
            "tool_trace": tool_trace.get("calls", []),
            "tool_round_limit": tool_trace.get("hit_round_limit", False)}


# ═══════════════════════════════════════════════════════════════════
#   [War Room v1] 행동 분석 — 실 원장 created_at 집계만 (세그먼트는 원장 미도입)
# ═══════════════════════════════════════════════════════════════════

def analytics_activity(days: int = 14) -> dict:
    days = max(1, min(int(days or 14), 90))
    con = _connect()

    def _per_day(table):
        try:
            return dict(con.execute(
                f"SELECT substr(created_at,1,10) AS d, COUNT(*) FROM {table}"
                f" WHERE created_at >= datetime('now','-{days} day') GROUP BY d"
            ).fetchall())
        except Exception:
            return {}

    src = _per_day("sources")
    prop = _per_day("proposals")
    exp = _per_day("export_results")
    con.close()

    out = []
    today = datetime.date.today()
    for i in range(days - 1, -1, -1):
        d = (today - datetime.timedelta(days=i)).isoformat()
        out.append({"date": d, "sources": src.get(d, 0),
                    "proposals": prop.get(d, 0), "exports": exp.get(d, 0)})
    return {"days": out, "note": "실 원장 created_at 집계 — 세그먼트 분석은 원장 미도입"}


# ═══════════════════════════════════════════════════════════════════
#   [War Room v1] 법무/수사공조 — 요청 원장 (추출 기능 없음, 별도 승인 후)
# ═══════════════════════════════════════════════════════════════════

_LEGAL_STATUSES = ("draft", "reviewing", "approved", "closed")


def legal_requests_list() -> dict:
    con = _connect()
    rows = con.execute(
        "SELECT id, requester, legal_basis, target_user_id, requested_range,"
        " status, data_scope_json, created_at, updated_at, closed_at"
        " FROM admin_legal_requests ORDER BY id DESC LIMIT 100").fetchall()
    con.close()
    cols = ["id", "requester", "legal_basis", "target_user_id", "requested_range",
            "status", "data_scope_json", "created_at", "updated_at", "closed_at"]
    return {"requests": [dict(zip(cols, r)) for r in rows]}


def legal_request_create(payload: dict) -> dict:
    requester = (payload.get("requester") or "").strip()
    if not requester:
        return {"error": "requester is required"}
    now = datetime.datetime.now().isoformat()
    con = _connect()
    cur = con.execute(
        "INSERT INTO admin_legal_requests (requester, legal_basis, target_user_id,"
        " requested_range, status, data_scope_json, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (requester, payload.get("legal_basis"), payload.get("target_user_id"),
         payload.get("requested_range"), "draft",
         payload.get("data_scope_json"), now, now))
    req_id = cur.lastrowid
    con.commit()
    con.close()
    audit_append("legal_request_create", target_type="legal_request",
                 target_id=str(req_id), note=f"{requester}")
    return {"status": "OK", "id": req_id}


def legal_request_status(req_id: int, status: str) -> dict:
    if status not in _LEGAL_STATUSES:
        return {"error": f"status must be one of {_LEGAL_STATUSES}"}
    now = datetime.datetime.now().isoformat()
    con = _connect()
    row = con.execute("SELECT status, requester FROM admin_legal_requests WHERE id=?",
                      (req_id,)).fetchone()
    if not row:
        con.close()
        return {"error": "legal request not found"}
    closed_at = now if status == "closed" else None
    con.execute(
        "UPDATE admin_legal_requests SET status=?, updated_at=?, closed_at=?"
        " WHERE id=?", (status, now, closed_at, req_id))
    con.commit()
    con.close()
    audit_append("legal_request_status", target_type="legal_request",
                 target_id=str(req_id), note=f"{row[0]} → {status} ({row[1]})")
    return {"status": "OK", "id": req_id, "from": row[0], "to": status}


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
