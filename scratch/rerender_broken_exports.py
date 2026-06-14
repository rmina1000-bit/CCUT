"""[STREAM-FIX] 기존 export 일괄 재렌더 (1.357fps -> 30fps 정규화).

- export_results 각각의 export_input.clips로 _render_with_ffmpeg 재실행
- 같은 output_path_internal로 덮어쓰기 (DB/URL 불변, 파일만 교체)
- 성공 시에만 교체(임시 출력 -> os.replace), 실패 시 원본 유지
- start/end null인 비정상 clips는 건너뛰고 보고
"""
import sys, os, io, json, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
os.chdir(os.path.join(os.path.dirname(__file__), "..", "ccut_backend"))
sys.path.insert(0, ".")

from archive.manager import bams
from engine.render_engine import render_engine

con = sqlite3.connect("ccut_app.db")
cur = con.cursor()

# export_input 맵
cur.execute("SELECT export_id, source_id, clips FROM export_input WHERE clips IS NOT NULL")
ei_map = {}
for eid, sid, clips in cur.fetchall():
    ei_map[eid] = {"source_id": sid, "clips": json.loads(clips) if isinstance(clips, str) else clips}

# export_results (실제 파일 있는 것)
cur.execute("SELECT id, export_input_id, output_path_internal FROM export_results WHERE status='RENDER_SUCCESS'")
rows = cur.fetchall()
con.close()

print(f"=== 재렌더 대상 export_results: {len(rows)} ===")
ok, skip_null, skip_nofile, fail = 0, 0, 0, 0
done_files = set()

for rnd_id, eid, out_path in rows:
    ei = ei_map.get(eid)
    if not ei:
        skip_nofile += 1
        continue
    clips = ei["clips"]
    # null clips 검증
    if not clips or any(c.get("start") is None or c.get("end") is None for c in clips):
        skip_null += 1
        print(f"  [SKIP-null] {rnd_id} ({eid}) start/end null")
        continue
    if not out_path or not os.path.exists(out_path):
        skip_nofile += 1
        continue
    # 같은 파일 중복 작업 방지
    if out_path in done_files:
        continue
    done_files.add(out_path)

    # source_paths
    spaths = {}
    for c in clips:
        s = c.get("source_id") or ei["source_id"]
        if s not in spaths:
            sd = bams.get_source(s)
            if sd:
                spaths[s] = sd.file_path
    if not spaths:
        fail += 1
        print(f"  [FAIL-nosrc] {rnd_id}")
        continue

    out_tmp = out_path + ".new.mp4"
    try:
        res = render_engine._render_with_ffmpeg(clips, spaths, out_tmp)
        if res.get("success") and os.path.exists(out_tmp) and os.path.getsize(out_tmp) > 0:
            os.replace(out_tmp, out_path)
            ok += 1
            if ok % 10 == 0:
                print(f"  ... {ok}개 재렌더 완료")
        else:
            fail += 1
            print(f"  [FAIL] {rnd_id}: {res.get('error_msg', res.get('stderr',''))[:100]}")
            if os.path.exists(out_tmp):
                os.remove(out_tmp)
    except Exception as e:
        fail += 1
        print(f"  [FAIL-exc] {rnd_id}: {e}")
        if os.path.exists(out_tmp):
            os.remove(out_tmp)

print(f"\n=== 완료 ===")
print(f"재렌더 성공: {ok}")
print(f"건너뜀(null 데이터): {skip_null}")
print(f"건너뜀(파일/입력 없음): {skip_nofile}")
print(f"실패: {fail}")
