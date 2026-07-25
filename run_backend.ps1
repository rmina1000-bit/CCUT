$env:FOR_DISABLE_CONSOLE_CTRL_HANDLER="T"
# [GATE-LOOP-01 0-2 2026-07-25] 게이트 강제 구문 제거 — 유일한 출처는 ccut_backend/.env.
# 여기서 $env:CCUT_* 를 세우면 그 값이 .env를 이기므로(override=False) 기동 경로마다
# 제품이 달라진다. 그게 오늘 정리한 병소다. 게이트를 바꾸려면 .env를 고친다.
python ccut_backend/main.py
