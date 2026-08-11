"""
[NIGHT-1 마무리 2026-08-09] 키 공식 대조 테스트 — ledger_r0.py _hash6 vs
editContractClient.ts hash6.

두 언어에 같은 djb2 해시가 중복 구현돼 있다(발급식 item_id = ITEM_{hash6(program_id)}_{fid}_{occ}).
손으로 두 파일을 읽고 "알고리즘이 같다"고 판단하는 대신, 실제 두 구현을 각각
그 언어 런타임으로 실행해 같은 입력에 같은 6자리 hex가 나오는지 raw로 대조한다.

- Python 쪽은 ledger_r0.py 를 그대로 import 해서 진짜 함수를 쓴다(재구현 아님).
- TS 쪽은 editContractClient.ts 소스에서 hash6() 함수 본문을 정규식으로 추출해
  Node 로 실행한다(재구현 아님 — 파일이 바뀌면 이 스크립트도 그 변경을 그대로 따라간다).

실행: python ccut_backend/scripts/shadow_compare_hash6.py
"""
import io
import json
import re
import subprocess
import sys
from pathlib import Path

# Windows 콘솔(cp949)에서 한글/em-dash 출력 시 UnicodeEncodeError 방지
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
TS_FILE = REPO_ROOT / "ccut_frontend" / "src" / "utils" / "editContractClient.ts"

sys.path.insert(0, str(BACKEND_DIR))
import ledger_r0  # noqa: E402  (진짜 함수를 그대로 쓴다)

# 대조 입력 — 실제 프로젝트 id 패턴 + 경계 케이스(빈 문자열/유니코드/장문/특수문자)
TEST_INPUTS = [
    "proj_d0928e8a19c4",   # Clover (real_project_pass_raw의 e18495와 대조 가능)
    "proj_0a19f7facac9",   # Daffodil
    "proj_ff8c890650e4",   # Marigold
    "",
    "a",
    "SF_9901B8_SRC_XXXX_P001",
    "결이 CCUT과 따로 놀고",   # 유니코드(한글)
    "x" * 500,               # 장문
    "proj_!@#$%^&*()_+",     # 특수문자
]


def python_hashes():
    return [ledger_r0._hash6(s) for s in TEST_INPUTS]


def extract_ts_hash6_body(ts_source: str) -> str:
    m = re.search(
        r"function hash6\(s: string\): string \{(.*?)\n\}",
        ts_source,
        re.S,
    )
    if not m:
        raise RuntimeError("hash6() 함수를 editContractClient.ts에서 못 찾았다 — 파일 구조가 바뀌었을 수 있다")
    return m.group(1)


def node_hashes():
    ts_source = TS_FILE.read_text(encoding="utf-8")
    body = extract_ts_hash6_body(ts_source)
    js = f"""
function hash6(s) {{{body}
}}
const inputs = {json.dumps(TEST_INPUTS)};
console.log(JSON.stringify(inputs.map(hash6)));
"""
    proc = subprocess.run(
        ["node", "-e", js],
        capture_output=True, text=True, check=True,
    )
    return json.loads(proc.stdout.strip())


def main():
    py = python_hashes()
    js = node_hashes()
    print(f"TS 소스: {TS_FILE.relative_to(REPO_ROOT)}")
    print(f"{'input':<30} {'python(_hash6)':<16} {'ts(hash6)':<12} {'match'}")
    all_match = True
    for inp, p, j in zip(TEST_INPUTS, py, js):
        ok = (p == j)
        all_match = all_match and ok
        shown = (inp[:27] + "...") if len(inp) > 30 else inp
        print(f"{shown!r:<30} {p:<16} {j:<12} {'OK' if ok else 'MISMATCH'}")
    print()
    print("RESULT:", "PASS — 두 구현이 모든 테스트 입력에서 동일한 해시를 낸다" if all_match
          else "FAIL — 불일치 발견, 두 구현이 갈라졌다")
    sys.exit(0 if all_match else 1)


if __name__ == "__main__":
    main()
