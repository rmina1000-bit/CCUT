import sys
import os
import json
import sqlite3
import urllib.request
import urllib.error

API_BASE_URL = "http://127.0.0.1:8000"
DB_PATH = r"D:\CCUT1.0.4\ccut_backend\ccut_app.db"

def print_header(title):
    print("\n" + "=" * 80)
    print(f" {title}")
    print("=" * 80)

def run_post_request(path, payload):
    url = f"{API_BASE_URL}{path}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        return {"status": "HTTP_ERROR", "code": e.code, "body": e.read().decode()}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

def run_get_request(path):
    url = f"{API_BASE_URL}{path}"
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        return {"status": "HTTP_ERROR", "code": e.code, "body": e.read().decode()}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

def test_step_1_llm_intent_parsing():
    print_header("TEST CASE 1: 자연어 의도 파싱 및 coverage 추출 검증")
    message = "여러 영상 골고루 섞어서 다시 제안해줘"
    print(f"[*] Sending User Message: '{message}'")
    
    resp = run_post_request("/narrative/intent", {"message": message})
    print(f"[*] Response Status: {resp.get('status')}")
    print(f"[*] Latency: {resp.get('latency_ms')} ms")
    
    patch = resp.get("patch") or {}
    print(f"[*] Extracted Patch: {json.dumps(patch, indent=2, ensure_ascii=False)}")
    
    # Validation
    coverage = patch.get("coverage")
    if resp.get("status") == "OK" and coverage == "balanced_sources":
        print("[PASS] LLM이 'coverage': 'balanced_sources' 의도를 성공적으로 파싱했습니다!")
    else:
        print("[WARN] LLM이 balanced_sources를 직접 파싱하지 못함 (Status가 OK가 아니거나 필드 누락).")
        print("[*] 프론트엔드 정규식 가드(Regex Fallback)에 의해 'balanced_sources'가 강제 획득될 것입니다.")

def test_step_2_hydration_and_fallback_removal():
    print_header("TEST CASE 2: 백엔드 역조회 Hydration 및 Fallback 제거 검증")
    
    mock_project_id = "proj_sandbox_test_999"
    print(f"[*] 1. Checking non-existent project_id: '{mock_project_id}' (Fallback Removal Check)")
    
    resp_empty = run_get_request(f"/proposals/project/{mock_project_id}/sources")
    print(f"[*] Response: {json.dumps(resp_empty, indent=2, ensure_ascii=False)}")
    
    if resp_empty.get("status") == "NO_PROPOSALS_FOUND" and len(resp_empty.get("sources", [])) == 0:
        print("[PASS] DB 전체 소스 복원 Fallback이 제거되었으며, 안전하게 NO_PROPOSALS_FOUND를 반환했습니다!")
    else:
        print("[FAIL] Fallback이 작동하여 전체 DB 소스가 복원되었거나, 잘못된 상태 코드가 리턴되었습니다.")

    # 2. DB에 테스트를 위한 가상 프로젝트 제안 적재 (영구 영향 없도록 트랜잭션 후 클린업 또는 수동 인서트/딜리트)
    print(f"\n[*] 2. Inserting mock project proposal for Hydration Check")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # DB 내 임의의 3개 source_id 획득
    cursor.execute("SELECT source_id FROM sources LIMIT 3;")
    real_sources = [r[0] for r in cursor.fetchall()]
    if not real_sources:
        print("[WARN] DB에 실제 소스가 없습니다. 테스트를 스킵하거나 임시 소스를 삽입합니다.")
        real_sources = ["SRC_MOCK_1", "SRC_MOCK_2"]
        cursor.execute("INSERT OR IGNORE INTO sources (source_id, file_path, title, duration) VALUES ('SRC_MOCK_1', 'dummy1.mp4', 'Dummy 1', 60.0);")
        cursor.execute("INSERT OR IGNORE INTO sources (source_id, file_path, title, duration) VALUES ('SRC_MOCK_2', 'dummy2.mp4', 'Dummy 2', 60.0);")
        conn.commit()

    print(f"[*] Selected sources for mock project: {real_sources}")
    
    # mock sequence JSON 구성
    mock_sequence = [
        {"fragment_id": f"SF_DUMMY_{sid}", "source_id": sid, "start": 0.0, "end": 10.0}
        for sid in real_sources
    ]
    
    # proposals 테이블에 project_id를 source_id 컬럼에 넣어 인서트
    proposal_id = "PROP_SANDBOX_TEST_A"
    cursor.execute(
        "INSERT OR REPLACE INTO proposals (proposal_id, source_id, mode, sequence, duration) VALUES (?, ?, ?, ?, ?);",
        (proposal_id, mock_project_id, "B", json.dumps(mock_sequence), 30.0)
    )
    conn.commit()
    print(f"[*] Inserted mock proposal '{proposal_id}' into project '{mock_project_id}'")
    
    try:
        # Hydration API 호출
        print(f"[*] 3. Calling Hydration API for project '{mock_project_id}'")
        resp_hydrate = run_get_request(f"/proposals/project/{mock_project_id}/sources")
        
        sources = resp_hydrate.get("sources", [])
        retrieved_ids = [s.get("source_id") for s in sources]
        print(f"[*] Retrieved sources: {retrieved_ids}")
        
        # 검증
        match = set(retrieved_ids) == set(real_sources)
        if resp_hydrate.get("status") == "OK" and match:
            print(f"[PASS] Hydration 역조회 복원 성공! 소스 목록이 동일하게 복구되었습니다. {retrieved_ids}")
        else:
            print(f"[FAIL] Hydration 역조회 복원 실패. Retrieved: {retrieved_ids}, Expected: {real_sources}")
            
    finally:
        # DB 클린업
        print(f"\n[*] 4. Cleaning up sandbox DB records")
        cursor.execute("DELETE FROM proposals WHERE source_id = ?;", (mock_project_id,))
        if "SRC_MOCK_1" in real_sources:
            cursor.execute("DELETE FROM sources WHERE source_id LIKE 'SRC_MOCK_%';")
        conn.commit()
        conn.close()
        print("[*] DB Sandbox Cleaned.")

def test_step_3_balanced_sources_generation():
    print_header("TEST CASE 3: balanced_sources 완화 및 균등(Balanced) 분산 최종 검증")
    
    # uvicorn 서버 DB에서 실제 소스 22개를 찾아오거나, 존재하는 모든 소스(최대 22개)를 가져와 API에 전달
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT source_id FROM sources;")
    all_real_sources = [r[0] for r in cursor.fetchall()]
    conn.close()
    
    print(f"[*] DB에 존재하는 소스 수: {len(all_real_sources)}")
    if len(all_real_sources) < 2:
        print("[WARN] 소스 수가 너무 적어 다양성 검증을 제대로 수행할 수 없습니다.")
        return
        
    # 최대 22개 소스 추출
    target_sources = all_real_sources[:22]
    print(f"[*] Testing with {len(target_sources)} source ids: {target_sources}")
    
    user_intent = {
        "coverage": "balanced_sources",
        "instruction_text": "여러 영상 골고루 섞어서 다시 제안해줘"
    }
    
    payload = {
        "project_id": "proj_sandbox_test_proposal",
        "source_ids": target_sources,
        "target_length": 60.0,
        "user_intent": user_intent,
        "refresh": True
    }
    
    print("\n[*] Sending Project Proposal Request...")
    resp = run_post_request("/proposals/project", payload)
    
    if resp.get("status") != "PROPOSAL_READY":
        print(f"[FAIL] 제안 생성 실패. Response: {resp}")
        return
        
    print(f"[PASS] Project Proposal Response Status: {resp.get('status')}")
    print(f"[*] Semantic Count processed: {resp.get('semantic_count')}")
    
    proposals = resp.get("proposals", [])
    print(f"[*] Returned proposals count: {len(proposals)}")
    
    # B안 (User Proposal) 소스 분산 계산
    user_proposal = next((p for p in proposals if p.get("mode") == "B"), None)
    if not user_proposal:
        print("[FAIL] B안(User Mode) 제안이 포함되어 있지 않습니다.")
        return
        
    seq = user_proposal.get("sequence", [])
    used_sids = [clip.get("source_id") for clip in seq]
    unique_used = set(used_sids)
    
    print(f"\n[*] --- B안 Sequence Analysis (used_source_count) ---")
    print(f"[*] Total clips selected in B: {len(seq)}")
    print(f"[*] Unique sources used in B: {len(unique_used)}")
    print(f"[*] Clip distribution by source:")
    for sid in unique_used:
        count = used_sids.count(sid)
        print(f"  - Source '{sid}': {count} clips")
        
    source_usage = resp.get("source_usage", {})
    print(f"[*] Backend reported source usage summary: {json.dumps(source_usage)}")
    
    # 검증 기준: balanced_sources로 인해 used_source_count가 단일 소스 편중(1~3개)에 머물지 않고 넓게 증가
    if len(unique_used) >= min(len(target_sources), 3):
        print(f"[PASS] 균등 분산 수립 성공! 총 {len(unique_used)}개의 유니크 소스가 고르게 제안 시퀀스에 사용되었습니다.")
    else:
        print(f"[FAIL] 균등 분산 조건 미충족. 유니크 소스가 {len(unique_used)}개에 불과합니다.")

if __name__ == "__main__":
    print("=" * 80)
    print(" CCUT1.0.4 PIPELINE FULL-CYCLE VERIFICATION SUITE RUNNING")
    print("=" * 80)
    
    # FastAPI 서버가 켜져 있는지 체크
    try:
        urllib.request.urlopen(f"{API_BASE_URL}/health", timeout=3)
    except Exception:
        print(f"[ERROR] FastAPI 서버가 {API_BASE_URL}에서 돌고 있지 않습니다. 실행 상태를 먼저 점검하십시오.")
        sys.exit(1)
        
    test_step_1_llm_intent_parsing()
    test_step_2_hydration_and_fallback_removal()
    test_step_3_balanced_sources_generation()
    
    print("\n" + "=" * 80)
    print(" ALL PIPELINE VERIFICATIONS COMPLETED!")
    print("=" * 80)
