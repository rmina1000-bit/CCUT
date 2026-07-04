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
import functools
import os
import sqlite3
import threading
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
# [정면도 v3 — ISO/IEC 29794-5 방식] solvePnP 5점 → yaw/pitch/roll(도),
# 품질 = cos²(yaw)·cos²(pitch)·cos²(roll) (OFIQ HeadPose와 동일 매핑, 축별 0~100 대신 곱).
# 실측 분리대(2026-07-04 Iris 59얼굴 눈검증): 정면 0.58~0.99 vs 3/4측면 0.49 이하.
# (구 v2 자체공식 0.28 문턱은 정면을 0.248~0.279로 오탐 탈락시켜 폐기)
FRONTAL_MIN = 0.55
# [대표 품질 게이트] 실측 기반 문턱 (2026-07-04, 31군집 대표 crop + Iris 59얼굴 raw 측정)
DARK_MIN = 25.0           # 정렬 crop 전체 평균 밝기 — 노출 하한(거의 검은 crop 15.7 실측)
BLUR_MIN = 55.0           # Laplacian var — 흐린 crop 16~48 vs 선명 55~2969
SKIN_MIN = 0.30           # 피부색 비율 문턱 — 하관·중안부 상대 비교에 사용 (아래 주석)
# 마스크 판정은 하관 단독이 아니라 '중안부는 피부인데 하관만 아님'일 때만 —
# 화이트밸런스가 깨진 프레임(YCrCb 피부검출 전체 실패: 하관 0.00·중안부 0.03 실측 맨얼굴)을
# 마스크로 오탐하지 않기 위한 자기정규화. 마스크 실측: 하관 0.07 vs 중안부 1.00.
# 눈가림(선글라스)도 절대밝기(구 45 문턱) 대신 얼굴 평균 대비 상대밝기 —
# 어두운 실내 정상 눈(절대 41~47, 상대 0.69~1.12)을 오탐하지 않고
# 밝은 얼굴 위의 검은 렌즈(상대 ~0.2대)만 걸러낸다. 실측 분리대: 정상 최저 0.61.
EYE_REL_MIN = 0.55

_detector = None
_recognizer = None
# cv2 DNN(YuNet/SFace)은 스레드 불안전 — UI가 /persons/scan을 이중 발사하면 executor
# 스레드 2개가 전역 모델을 동시 사용해 BlobManager assertion(500) 또는 네이티브
# 프로세스 즉사를 유발 (2026-07-04 실증: 동시 2요청 재현, 무트레이스백 사망 3회).
# 모델을 쓰는 함수 전체를 직렬화한다 — 중복 스캔은 seen 로드가 락 안에 있어
# 두 번째 요청이 자연히 skip되므로 face_count 이중 증가도 함께 막힌다.
_MODEL_LOCK = threading.RLock()


def _serialized(fn):
    @functools.wraps(fn)
    def wrap(*args, **kwargs):
        with _MODEL_LOCK:
            return fn(*args, **kwargs)
    return wrap


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


# 일반 3D 얼굴 5점 모델 (YuNet 랜드마크 순서: 오른눈, 왼눈, 코끝, 입오른끝, 입왼끝).
# 단위 임의 — solvePnP는 상대 기하만 쓴다. 코끝 원점, 눈/입은 뒤쪽(-z).
_MODEL_5PT = np.array([
    (-165.0, 170.0, -135.0),
    (165.0, 170.0, -135.0),
    (0.0, 0.0, 0.0),
    (-150.0, -150.0, -125.0),
    (150.0, -150.0, -125.0),
], dtype=np.float64)


def _frontal_score(d, img_w, img_h):
    """YuNet 검출 1건의 '정면도' v3 — ISO/IEC 29794-5(OFIQ) 방식.
    랜드마크 5점 solvePnP로 머리자세 yaw/pitch/roll(도)을 추정하고
    cos²(yaw)·cos²(pitch)·cos²(roll)로 품질화 (정면=1.0, 45° 한 축이면 0.5).
    카메라 내참: focal=img_w, 주점=프레임 중앙 (표준 근사)."""
    import cv2
    img_pts = np.array([(d[4], d[5]), (d[6], d[7]), (d[8], d[9]),
                        (d[10], d[11]), (d[12], d[13])], dtype=np.float64)
    focal = float(img_w)
    K = np.array([(focal, 0, img_w / 2.0), (0, focal, img_h / 2.0), (0, 0, 1)],
                 dtype=np.float64)
    try:
        ok, rvec, tvec = cv2.solvePnP(_MODEL_5PT, img_pts, K, None,
                                      flags=cv2.SOLVEPNP_EPNP)
        if not ok:
            return 0.0
        rvec, tvec = cv2.solvePnP(_MODEL_5PT, img_pts, K, None, rvec, tvec,
                                  useExtrinsicGuess=True,
                                  flags=cv2.SOLVEPNP_ITERATIVE)[1:]
        R, _ = cv2.Rodrigues(rvec)
        euler = cv2.decomposeProjectionMatrix(K @ np.hstack([R, tvec]))[6].flatten()
    except cv2.error:
        return 0.0
    pitch, yaw, roll = float(euler[0]), float(euler[1]), float(euler[2])
    if pitch > 90:
        pitch -= 180
    elif pitch < -90:
        pitch += 180
    q = 1.0
    for ang in (pitch, yaw, roll):
        q *= max(0.0, np.cos(np.radians(ang))) ** 2
    return float(q)


def _face_quality(aligned):
    """대표 사진 자격 검사 — (ok, 사유). aligned = SFace alignCrop(112x112 BGR).
    노출(dark)·흐림(blur)·선글라스/눈가림(상대밝기)·마스크(하관vs중안부 피부율)를 걸러낸다.
    모자·일반안경은 통과. 상대 측정으로 어두운 장면·화이트밸런스 깨짐에 자기정규화
    (문턱 근거는 상수 블록 주석의 실측)."""
    import cv2
    g = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    face_mean = float(g.mean())
    if face_mean < DARK_MIN:
        return False, f"dark={face_mean:.0f}"
    blur = cv2.Laplacian(g, cv2.CV_64F).var()
    if blur < BLUR_MIN:
        return False, f"blur={blur:.0f}"
    # SFace 정렬 표준 눈좌표 (38.3,51.7)/(73.5,51.5) @112 — 비율로 환산
    eye_means, eye_stds = [], []
    for ex, ey in ((int(w * 0.34), int(h * 0.46)), (int(w * 0.66), int(h * 0.46))):
        patch = g[max(ey - 8, 0):ey + 8, max(ex - 8, 0):ex + 8]
        eye_means.append(float(patch.mean()))
        eye_stds.append(float(patch.std()))
    eye_rel = max(eye_means) / face_mean
    if eye_rel < EYE_REL_MIN:
        return False, f"eyes_hidden={eye_rel:.2f}"
    if max(eye_means) < 30 and max(eye_stds) < 8:
        # 상대밝기를 통과해도 절대 암흑 + 무질감(렌즈/머리카락 균일 가림)이면 탈락
        return False, f"eyes_flat={max(eye_means):.0f}/{max(eye_stds):.1f}"
    ycrcb = cv2.cvtColor(aligned, cv2.COLOR_BGR2YCrCb)
    skin_all = cv2.inRange(ycrcb, (0, 133, 77), (255, 180, 127))
    lower = skin_all[int(h * 0.55):int(h * 0.95), int(w * 0.20):int(w * 0.80)]
    mid = skin_all[int(h * 0.25):int(h * 0.50), int(w * 0.15):int(w * 0.85)]
    skin_low = float(np.count_nonzero(lower)) / lower.size
    skin_mid = float(np.count_nonzero(mid)) / mid.size
    if skin_low < SKIN_MIN and skin_mid >= SKIN_MIN:
        return False, f"skin={skin_low:.2f}/{skin_mid:.2f}"
    return True, "ok"


def _ensure_frontal_column(con):
    try:
        con.execute("ALTER TABLE persons ADD COLUMN frontal REAL DEFAULT 0")
        con.commit()
    except sqlite3.OperationalError:
        pass  # 이미 있음


@_serialized
def scan_project(project_id: str, max_frames: int = 400) -> dict:
    """프로젝트 소스들의 키프레임에서 얼굴 검출·군집. 멱등(이미 본 fragment는 skip)."""
    import cv2
    det, rec = _lazy_models()
    os.makedirs(FACES_DIR, exist_ok=True)
    con = _connect()
    ensure_schema(con)
    _ensure_frontal_column(con)

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
    for pid, emb, status, frontal, pname in con.execute(
            "SELECT person_id, embedding, status, COALESCE(frontal, 0), name FROM persons"):
        if emb:
            persons.append({"pid": pid, "emb": np.frombuffer(emb, dtype=np.float32),
                            "status": status, "frontal": float(frontal), "name": pname})

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
            fs = _frontal_score(d, w, h)
            if best is not None and best_cos >= SAME_PERSON_COS:
                pid = best["pid"]
                # 군집 중심 이동 평균 (완만하게)
                best["emb"] = (best["emb"] * 0.8 + feat * 0.2).astype(np.float32)
                con.execute("UPDATE persons SET embedding=?, face_count=face_count+1, updated_at=? WHERE person_id=?",
                            (best["emb"].tobytes(), now, pid))
                # [정면 대표] 더 정면인 얼굴이 오면 대표 사진 교체 (품질 게이트 통과분만)
                if fs > best.get("frontal", 0.0) + 0.03 and _face_quality(aligned)[0]:
                    cv2.imwrite(os.path.join(FACES_DIR, f"{pid}.jpg"), aligned)
                    con.execute("UPDATE persons SET frontal=? WHERE person_id=?", (fs, pid))
                    best["frontal"] = fs
                # [PERSON-RELINK C1] named 군집에 새 조각이 귀속되면 이름 태그도 즉시 주입.
                # 재조각화 후 scan이 링크는 복구하는데 검색 어휘(visual_desc 태그)는
                # 안 살아나던 공백(Hollyhock/lavender keep=0 실증)의 직접 원인 봉합.
                if (os.getenv("CCUT_PERSON_RELINK", "0") in ("1", "true", "True")
                        and best.get("status") == "named" and best.get("name")):
                    _inject_name_tag(con, best["name"], fid, now)
            else:
                pid = f"PER_{uuid.uuid4().hex[:8].upper()}"
                face_path = os.path.join(FACES_DIR, f"{pid}.jpg")
                cv2.imwrite(face_path, aligned)
                # 품질 미달(흐림/마스크/선글라스) 첫 얼굴은 frontal=0 → 카드 자격 없음.
                # 이후 스캔/refresh에서 품질 통과 얼굴이 나오면 그때 대표·frontal 갱신.
                rep_fs = fs if _face_quality(aligned)[0] else 0.0
                con.execute(
                    "INSERT INTO persons (person_id, name, status, embedding, face_path, face_count, frontal, created_at, updated_at) "
                    "VALUES (?, NULL, 'pending', ?, ?, 1, ?, ?, ?)",
                    (pid, feat.tobytes(), f"/static/faces/{pid}.jpg", rep_fs, now, now))
                persons.append({"pid": pid, "emb": feat, "status": "pending", "frontal": rep_fs})
                new_clusters += 1
            con.execute("INSERT OR REPLACE INTO person_faces (person_id, fragment_id, score) VALUES (?, ?, ?)",
                        (pid, fid, round(best_cos if best else 1.0, 4)))
        con.commit()

    con.close()
    # [정면 대표] 이미 스캔된 군집(위 seen-skip 대상)도 소급 갱신.
    # 중복 병합(merge_duplicates)은 과병합 사고 이후 자동 실행하지 않는다 — dry-run 검증 후 수동.
    refreshed = refresh_representatives()
    print(f"[PERSON-PALETTE] scan {project_id}: frames={scanned} faces={faces_found} "
          f"new_clusters={new_clusters} rep_refreshed={refreshed}")
    return {"status": "OK", "scanned": scanned, "faces": faces_found,
            "new_clusters": new_clusters, "rep_refreshed": refreshed}


@_serialized
def merge_duplicates(dry_run: bool = True) -> int:
    """같은 사람이 쪼개진 pending 군집 병합 (기본 dry-run: 후보만 출력).
    증거: 각 얼굴의 소속(argmax) 군집 외에 다른 군집 중심과도 cos>=임계면 교차표(cross)에
    기록하고, 양방향 존재 + 서로 다른 keyframe 합계 3회 이상인 쌍만 병합.
    — 단일 얼굴 1건 일치 + 전이 연쇄로 병합했다가 남아·성인여성까지 한 군집(59)으로
      휩쓸린 사고(2026-07-04)의 재발 방지. 중심끼리 cos는 드리프트로 신뢰 불가(실측:
      동일인 쌍 0.313 < 타인 쌍 0.308과 역전)."""
    import cv2
    det, rec = _lazy_models()
    con = _connect()
    ensure_schema(con)
    _ensure_frontal_column(con)
    rows = list(con.execute(
        "SELECT person_id, embedding, face_count FROM persons "
        "WHERE status='pending' AND embedding IS NOT NULL"))
    if len(rows) < 2:
        con.close()
        return 0
    clusters = {pid: {"emb": np.frombuffer(e, dtype=np.float32), "count": c}
                for pid, e, c in rows}
    fids = {fid for (fid,) in con.execute(
        "SELECT DISTINCT pf.fragment_id FROM person_faces pf "
        "JOIN persons p ON p.person_id = pf.person_id WHERE p.status='pending'")}

    cross = {}  # (owner, other) -> set of fids
    for fid in fids:
        kf = os.path.join(KEYFRAME_DIR, f"{fid}.jpg")
        img = cv2.imread(kf) if os.path.exists(kf) else None
        if img is None:
            continue
        h, w = img.shape[:2]
        det.setInputSize((w, h))
        _, dets = det.detect(img)
        if dets is None:
            continue
        for d in dets:
            if int(d[2]) < MIN_FACE or int(d[3]) < MIN_FACE:
                continue
            feat = rec.feature(rec.alignCrop(img, d)).flatten().astype(np.float32)
            sims = {pid: _cos(feat, c["emb"]) for pid, c in clusters.items()}
            hit = [pid for pid, s in sims.items() if s >= SAME_PERSON_COS]
            if len(hit) < 2:
                continue
            owner = max(hit, key=lambda p: sims[p])
            for other in hit:
                if other != owner:
                    cross.setdefault((owner, other), set()).add(fid)

    def evidence(a, b):
        ab = cross.get((a, b), set())
        ba = cross.get((b, a), set())
        return len(ab), len(ba), len(ab | ba)

    pairs = []
    pids = list(clusters)
    for i in range(len(pids)):
        for j in range(i + 1, len(pids)):
            n_ab, n_ba, n_all = evidence(pids[i], pids[j])
            if n_all > 0:
                strong = n_ab >= 1 and n_ba >= 1 and n_all >= 3
                pairs.append((pids[i], pids[j], n_ab, n_ba, n_all, strong))
                print(f"[PERSON-PALETTE] dup-evidence {pids[i]}~{pids[j]} "
                      f"a->b={n_ab} b->a={n_ba} frames={n_all} {'MERGE' if strong else 'weak'}")
    if dry_run:
        con.close()
        return 0

    parent = {pid: pid for pid in clusters}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, _, _, _, strong in pairs:
        if strong and find(a) != find(b):
            parent[find(b)] = find(a)
    groups = {}
    for pid in clusters:
        groups.setdefault(find(pid), []).append(pid)
    merged = 0
    now = datetime.datetime.now().isoformat()
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda p: clusters[p]["count"], reverse=True)
        win, losers = members[0], members[1:]
        total = sum(clusters[p]["count"] for p in members)
        emb = np.sum([clusters[p]["emb"] * clusters[p]["count"] for p in members],
                     axis=0) / max(total, 1)
        for lo in losers:
            con.execute("INSERT OR IGNORE INTO person_faces (person_id, fragment_id, score) "
                        "SELECT ?, fragment_id, score FROM person_faces WHERE person_id=?",
                        (win, lo))
            con.execute("DELETE FROM person_faces WHERE person_id=?", (lo,))
            con.execute("DELETE FROM persons WHERE person_id=?", (lo,))
            try:
                os.remove(os.path.join(FACES_DIR, f"{lo}.jpg"))
            except OSError:
                pass
            merged += 1
            print(f"[PERSON-PALETTE] merged {lo} -> {win}")
        con.execute("UPDATE persons SET embedding=?, face_count=?, updated_at=? WHERE person_id=?",
                    (emb.astype(np.float32).tobytes(), total, now, win))
    con.commit()
    con.close()
    return merged


@_serialized
def refresh_representatives(min_gain: float = 0.03, force: bool = False) -> int:
    """pending 군집의 대표 사진을 '가장 정면인 얼굴'로 소급 교체.
    각 군집에 연결된 조각 키프레임을 재검출 → 임베딩이 그 군집과 일치(cos≥임계)하는
    얼굴 중 정면도(frontal) 최고를 대표로. frontal=0(구버전 기록)도 이때 채워진다.
    force=True: 기록된 frontal을 무시하고 전 군집 재선정(점수식 변경 시 필요)."""
    import cv2
    det, rec = _lazy_models()
    con = _connect()
    ensure_schema(con)
    _ensure_frontal_column(con)
    rows = list(con.execute(
        "SELECT person_id, embedding, COALESCE(frontal, 0) FROM persons WHERE status='pending' AND embedding IS NOT NULL"))
    refreshed = 0
    for pid, emb_blob, cur_fs in rows:
        emb = np.frombuffer(emb_blob, dtype=np.float32)
        fids = [r[0] for r in con.execute(
            "SELECT fragment_id FROM person_faces WHERE person_id=?", (pid,))]
        best_fs, best_img = (0.0 if force else float(cur_fs)), None
        for fid in fids:
            kf = os.path.join(KEYFRAME_DIR, f"{fid}.jpg")
            img = cv2.imread(kf) if os.path.exists(kf) else None
            if img is None:
                continue
            h, w = img.shape[:2]
            det.setInputSize((w, h))
            _, dets = det.detect(img)
            if dets is None:
                continue
            for d in dets:
                if int(d[2]) < MIN_FACE or int(d[3]) < MIN_FACE:
                    continue
                fs = _frontal_score(d, w, h)
                if fs <= best_fs + min_gain:
                    continue
                aligned = rec.alignCrop(img, d)
                if not _face_quality(aligned)[0]:
                    continue  # 흐림/마스크/선글라스 crop은 대표 자격 없음
                feat = rec.feature(aligned).flatten().astype(np.float32)
                if _cos(feat, emb) < SAME_PERSON_COS:
                    continue  # 같은 프레임의 다른 사람 얼굴 배제
                best_fs, best_img = fs, aligned
        if best_img is not None:
            cv2.imwrite(os.path.join(FACES_DIR, f"{pid}.jpg"), best_img)
            con.execute("UPDATE persons SET frontal=?, updated_at=? WHERE person_id=?",
                        (best_fs, datetime.datetime.now().isoformat(), pid))
            refreshed += 1
            print(f"[PERSON-PALETTE] rep refreshed {pid} frontal={best_fs:.3f}")
        elif force:
            # 재선정 모드에서 정면 얼굴을 한 건도 재확인 못한 군집 → 새 점수 기준으로 기록
            # (구식 점수로 문턱을 넘어 옆모습 카드가 남는 것 방지)
            con.execute("UPDATE persons SET frontal=?, updated_at=? WHERE person_id=?",
                        (best_fs, datetime.datetime.now().isoformat(), pid))
            print(f"[PERSON-PALETTE] rep re-scored(no better face) {pid} frontal={best_fs:.3f}")
    con.commit()
    con.close()
    return refreshed


def list_pending(project_id: str = None, min_faces: int = 2) -> list:
    """이름을 물어볼 후보 군집 (얼굴 min_faces회 이상 등장한 것만 — 스치는 행인 제외)."""
    con = _connect()
    ensure_schema(con)
    _ensure_frontal_column(con)
    # [정면 대표] 정면 얼굴이 한 번도 안 잡힌 군집(옆모습뿐)은 알아볼 수 없어 묻지 않는다.
    # 이후 스캔에서 정면이 나오면(frontal 갱신) 자동으로 다시 후보에 오른다.
    q = """SELECT p.person_id, p.face_path, p.face_count, p.updated_at,
                  (SELECT COUNT(*) FROM person_faces pf WHERE pf.person_id = p.person_id) AS links
           FROM persons p WHERE p.status = 'pending' AND p.face_count >= ?
                 AND COALESCE(p.frontal, 0) >= ?
           ORDER BY p.face_count DESC"""
    rows = list(con.execute(q, (min_faces, FRONTAL_MIN)))
    out = []
    for pid, face_path, cnt, updated_at, links in rows:
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
        # [정면 대표] 대표 사진 교체 시 브라우저 캐시 무효화 (파일명 동일 → mtime 쿼리)
        ver = "".join(c for c in (updated_at or "") if c.isdigit())[:14]
        out.append({"person_id": pid,
                    "face_url": f"{face_path}?v={ver}" if ver else face_path,
                    "appearances": cnt})
    con.close()
    return out


def _inject_name_tag(con, name: str, fragment_id: str, now: str = None) -> int:
    """fragment_index 행에 이름 태그 주입 (visual_desc/main_subjects/search_text).
    set_name·scan 링크(C1)·재인덱싱 재주입(C2)의 공용 경로.
    행 없으면 0. append-only 멱등 — 이미 태그돼 있어도 안전."""
    row = con.execute(
        "SELECT visual_desc, main_subjects, search_text FROM fragment_index WHERE fragment_id=?",
        (fragment_id,)).fetchone()
    if not row:
        return 0
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
        (vd, ",".join(subjects), st2, now or datetime.datetime.now().isoformat(), fragment_id))
    return 1


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
        tagged += _inject_name_tag(con, name, fid, now)
    con.commit()
    con.close()
    print(f"[PERSON-PALETTE] named {person_id}='{name}' tagged_fragments={tagged}")
    return {"status": "OK", "person_id": person_id, "name": name, "tagged_fragments": tagged}


def reinject_names_for_source(source_id: str) -> int:
    """[PERSON-RELINK C2] 재인덱싱(reindex_source)이 visual_desc를 전체 교체하며
    지운 named 이름 태그를 재주입. 살아있는 person_faces 링크 × 해당 source의
    fragment_index 행 조인 → _inject_name_tag (append-only 멱등).
    cv2 미사용(순수 sqlite) — _MODEL_LOCK 불필요. 재주입 수 반환."""
    con = _connect()
    ensure_schema(con)
    rows = list(con.execute(
        "SELECT p.name, pf.fragment_id FROM person_faces pf "
        "JOIN persons p ON p.person_id = pf.person_id "
        "JOIN fragment_index fi ON fi.fragment_id = pf.fragment_id "
        "WHERE p.status='named' AND p.name IS NOT NULL AND fi.source_id = ?",
        (source_id,)))
    n = 0
    for name, fid in rows:
        n += _inject_name_tag(con, name, fid)
    con.commit()
    con.close()
    if n:
        print(f"[PERSON-RELINK] reinject source={source_id} tagged={n}")
    return n


def reject(person_id: str) -> dict:
    con = _connect()
    ensure_schema(con)
    con.execute("UPDATE persons SET status='rejected', updated_at=? WHERE person_id=?",
                (datetime.datetime.now().isoformat(), person_id))
    con.commit()
    con.close()
    return {"status": "OK", "person_id": person_id}
