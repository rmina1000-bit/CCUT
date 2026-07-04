# -*- coding: utf-8 -*-
"""[PERSON-PALETTE] 사람 팔레트 — 얼굴 검출·군집·이름 저장.

선행자 조사 결론(2026-07-04): OpenCV 내장 YuNet(검출, <1MB) + SFace(임베딩, 37MB)
  - 추가 pip 의존성 0 (cv2.FaceDetectorYN / cv2.FaceRecognizerSF)
  - CPU 실시간급 → Ollama(GPU)와 자원 경합 없음
  - SFace 공식 cosine 동일인 임계 0.363

원칙:
  - 센서층: 여기서는 '얼굴이 있다/누구와 같다'까지만. 이름은 사용자가 준다(문진).
  - 이름이 저장되면 fragment_index.visual_desc/main_subjects에 주입
    → hub judge·검색·편집("OO 나오는 장면만")이 그 이름을 그대로 본다.
  - 거부(reject)하면 그 군집은 다시 묻지 않는다.

저장:
  persons(person_id, name, status[pending|named|rejected], embedding, face_path, ...)
  person_faces(person_id, fragment_id, score)
얼굴 크롭: {STORAGE}/faces/{person_id}.jpg → /static/faces/… 로 서빙.
"""
import datetime
import os
import sqlite3
import uuid

import numpy as np

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(BACKEND_DIR)
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")
# [이중 storage 주의] 키프레임은 backend/storage, static 마운트는 ROOT/storage
KEYFRAME_DIR = os.path.join(BACKEND_DIR, "storage", "search_keyframes")
FACES_DIR = os.path.join(ROOT, "storage", "faces")
YUNET = os.path.join(ROOT, "runtime", "face", "face_detection_yunet_2023mar.onnx")
SFACE = os.path.join(ROOT, "runtime", "face", "face_recognition_sface_2021dec.onnx")

SAME_PERSON_COS = 0.363   # SFace 공식 임계
MIN_FACE = 40             # px — 너무 작은 얼굴은 신원 판단 불가

_detector = None
_recognizer = None


def _lazy_models():
    global _detector, _recognizer
    import cv2
    if _detector is None:
        _detector = cv2.FaceDetectorYN.create(YUNET, "", (320, 320), 0.8, 0.3, 5000)
    if _recognizer is None:
        _recognizer = cv2.FaceRecognizerSF.create(SFACE, "")
    return _detector, _recognizer


def _connect():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    return con


def ensure_schema(con):
    con.execute("""CREATE TABLE IF NOT EXISTS persons (
        person_id TEXT PRIMARY KEY,
        name TEXT,
        status TEXT DEFAULT 'pending',
        embedding BLOB,
        face_path TEXT,
        face_count INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS person_faces (
        person_id TEXT,
        fragment_id TEXT,
        score REAL,
        PRIMARY KEY (person_id, fragment_id))""")
    con.commit()


def _cos(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def scan_project(project_id: str, max_frames: int = 400) -> dict:
    """프로젝트 소스들의 키프레임에서 얼굴 검출·군집. 멱등(이미 본 fragment는 skip)."""
    import cv2
    det, rec = _lazy_models()
    os.makedirs(FACES_DIR, exist_ok=True)
    con = _connect()
    ensure_schema(con)

    sids = [r[0] for r in con.execute(
        "SELECT source_id FROM project_sources WHERE program_id=?", (project_id,))]
    if not sids:
        con.close()
        return {"status": "NO_SOURCES", "clusters": 0, "faces": 0}

    ph = ",".join("?" * len(sids))
    frags = [r[0] for r in con.execute(
        f"SELECT fragment_id FROM fragment_index WHERE source_id IN ({ph})", sids)]
    seen = {r[0] for r in con.execute("SELECT DISTINCT fragment_id FROM person_faces")}

    # 기존 군집 로드 (프로젝트 무관 전역 — 아카이브 재사용의 핵심)
    persons = []
    for pid, emb, status in con.execute("SELECT person_id, embedding, status FROM persons"):
        if emb:
            persons.append({"pid": pid, "emb": np.frombuffer(emb, dtype=np.float32), "status": status})

    now = datetime.datetime.now().isoformat()
    faces_found = 0
    new_clusters = 0
    scanned = 0
    for fid in frags:
        if fid in seen:
            continue
        kf = os.path.join(KEYFRAME_DIR, f"{fid}.jpg")
        if not os.path.exists(kf):
            continue
        if scanned >= max_frames:
            break
        scanned += 1
        img = cv2.imread(kf)
        if img is None:
            continue
        h, w = img.shape[:2]
        det.setInputSize((w, h))
        _, dets = det.detect(img)
        if dets is None:
            continue
        for d in dets:
            bw, bh = int(d[2]), int(d[3])
            if bw < MIN_FACE or bh < MIN_FACE:
                continue
            aligned = rec.alignCrop(img, d)
            feat = rec.feature(aligned).flatten().astype(np.float32)
            faces_found += 1
            # 가장 가까운 기존 인물 탐색
            best, best_cos = None, 0.0
            for p in persons:
                c = _cos(feat, p["emb"])
                if c > best_cos:
                    best, best_cos = p, c
            if best is not None and best_cos >= SAME_PERSON_COS:
                pid = best["pid"]
                # 군집 중심 이동 평균 (완만하게)
                best["emb"] = (best["emb"] * 0.8 + feat * 0.2).astype(np.float32)
                con.execute("UPDATE persons SET embedding=?, face_count=face_count+1, updated_at=? WHERE person_id=?",
                            (best["emb"].tobytes(), now, pid))
            else:
                pid = f"PER_{uuid.uuid4().hex[:8].upper()}"
                face_path = os.path.join(FACES_DIR, f"{pid}.jpg")
                cv2.imwrite(face_path, aligned)
                con.execute(
                    "INSERT INTO persons (person_id, name, status, embedding, face_path, face_count, created_at, updated_at) "
                    "VALUES (?, NULL, 'pending', ?, ?, 1, ?, ?)",
                    (pid, feat.tobytes(), f"/static/faces/{pid}.jpg", now, now))
                persons.append({"pid": pid, "emb": feat, "status": "pending"})
                new_clusters += 1
            con.execute("INSERT OR REPLACE INTO person_faces (person_id, fragment_id, score) VALUES (?, ?, ?)",
                        (pid, fid, round(best_cos if best else 1.0, 4)))
        con.commit()

    con.close()
    print(f"[PERSON-PALETTE] scan {project_id}: frames={scanned} faces={faces_found} new_clusters={new_clusters}")
    return {"status": "OK", "scanned": scanned, "faces": faces_found, "new_clusters": new_clusters}


def list_pending(project_id: str = None, min_faces: int = 2) -> list:
    """이름을 물어볼 후보 군집 (얼굴 min_faces회 이상 등장한 것만 — 스치는 행인 제외)."""
    con = _connect()
    ensure_schema(con)
    q = """SELECT p.person_id, p.face_path, p.face_count,
                  (SELECT COUNT(*) FROM person_faces pf WHERE pf.person_id = p.person_id) AS links
           FROM persons p WHERE p.status = 'pending' AND p.face_count >= ?
           ORDER BY p.face_count DESC"""
    rows = list(con.execute(q, (min_faces,)))
    out = []
    for pid, face_path, cnt, links in rows:
        if project_id:
            sids = [r[0] for r in con.execute(
                "SELECT source_id FROM project_sources WHERE program_id=?", (project_id,))]
            if sids:
                ph = ",".join("?" * len(sids))
                hit = con.execute(
                    f"""SELECT COUNT(*) FROM person_faces pf
                        JOIN fragment_index fi ON fi.fragment_id = pf.fragment_id
                        WHERE pf.person_id=? AND fi.source_id IN ({ph})""",
                    [pid] + sids).fetchone()[0]
                if hit == 0:
                    continue
        out.append({"person_id": pid, "face_url": face_path, "appearances": cnt})
    con.close()
    return out


def set_name(person_id: str, name: str) -> dict:
    """이름 저장 → 연결 조각들의 visual_desc/main_subjects에 이름 주입 (judge·검색이 보게)."""
    name = (name or "").strip()
    if not name:
        return {"status": "ERROR", "message": "이름이 비었습니다"}
    con = _connect()
    ensure_schema(con)
    now = datetime.datetime.now().isoformat()
    con.execute("UPDATE persons SET name=?, status='named', updated_at=? WHERE person_id=?",
                (name, now, person_id))
    fids = [r[0] for r in con.execute(
        "SELECT fragment_id FROM person_faces WHERE person_id=?", (person_id,))]
    tagged = 0
    for fid in fids:
        row = con.execute(
            "SELECT visual_desc, main_subjects, search_text FROM fragment_index WHERE fragment_id=?",
            (fid,)).fetchone()
        if not row:
            continue
        vd, ms, st = row
        tag = f"인물:{name}"
        if tag not in (vd or ""):
            vd = f"{(vd or '').rstrip()} ({tag})".strip()
        subjects = [s for s in (ms or "").split(",") if s.strip()]
        if name not in subjects:
            subjects.append(name)
        st2 = st or ""
        if name not in st2:
            st2 = f"{st2} {name}".strip()
        con.execute(
            "UPDATE fragment_index SET visual_desc=?, main_subjects=?, search_text=?, updated_at=? WHERE fragment_id=?",
            (vd, ",".join(subjects), st2, now, fid))
        tagged += 1
    con.commit()
    con.close()
    print(f"[PERSON-PALETTE] named {person_id}='{name}' tagged_fragments={tagged}")
    return {"status": "OK", "person_id": person_id, "name": name, "tagged_fragments": tagged}


def reject(person_id: str) -> dict:
    con = _connect()
    ensure_schema(con)
    con.execute("UPDATE persons SET status='rejected', updated_at=? WHERE person_id=?",
                (datetime.datetime.now().isoformat(), person_id))
    con.commit()
    con.close()
    return {"status": "OK", "person_id": person_id}
