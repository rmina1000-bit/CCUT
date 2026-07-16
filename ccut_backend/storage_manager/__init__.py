"""STORAGE-1 저장공간 관리자. ST-0(계측)~ST-2(Janitor dry-run) 범위.
실삭제는 ST-3 국장 승인 게이트 이후에만 구현된다 — 그 전까지 janitor.delete_candidates()는
NotImplementedError를 낸다.
"""
