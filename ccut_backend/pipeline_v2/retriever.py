# -*- coding: utf-8 -*-
"""[V2-α] Retriever — 3채널 분리 + 비가중 RRF(k=60).

채널:
  dense   : bge-m3 /api/embed, 문서 = fragment_index.search_text (조각 화면 직접 근거)
  note    : 소스 노트 원문 임베딩 매치 → 그 소스 소속 조각 전파.
            전파 원소는 evidence_scope=SOURCE 필수 (노트 일치 ≠ 조각 화면 검증).
  lexical : search_text + 소스 노트의 단순 토큰 일치(결정론)

융합: 비가중 RRF, k=60. score = Σ_채널 1/(k + rank).
exclude selector는 RRF에 미반영 — CandidateSet에 excluded=true + 사유만 표기
(삭제 판단은 조립(Assembly) 단계의 몫 — 헌장 §exclude-비파괴).

DB: read-only(mode=ro). fragment_index 쓰기 0. LLM 추론 0 (임베딩만).
"""
import json
import sqlite3
import urllib.request

DB = r"D:\CCUT1.0.4\ccut_backend\ccut_app.db"
OLLAMA_EMBED = "http://127.0.0.1:11434/api/embed"
EMBED_MODEL = "bge-m3"
RRF_K = 60


def _embed(texts):
    body = json.dumps({"model": EMBED_MODEL, "input": texts}).encode("utf-8")
    req = urllib.request.Request(OLLAMA_EMBED, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8"))["embeddings"]


def _l2(v):
    n = sum(x * x for x in v) ** 0.5
    return [x / n for x in v] if n else v


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b))


class RetrieverV2:
    """프로젝트 조각 풀 1회 적재 → 질의 N회. 모든 근거는 원문 발췌로 동반."""

    def __init__(self, source_ids):
        con = sqlite3.connect("file:" + DB.replace("\\", "/") + "?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        self.frags = []          # 풀 순서 보존
        self.notes = {}          # sid -> [note원문]
        for sid in source_ids:
            for r in con.execute(
                    'SELECT sf.fragment_id, sf.source_id, sf.start, sf."end", '
                    "COALESCE(fi.search_text,'') st, COALESCE(fi.visual_desc,'') vd, "
                    "COALESCE(fi.transcript,'') tr "
                    "FROM semantic_fragments sf "
                    "LEFT JOIN fragment_index fi ON fi.fragment_id=sf.fragment_id "
                    "WHERE sf.source_id=? ORDER BY sf.start", (sid,)):
                self.frags.append(dict(r) | {"fragment_id": r["fragment_id"]})
            self.notes[sid] = [n[0] for n in con.execute(
                "SELECT text FROM narrative_notes WHERE target_kind='source' "
                "AND target_id=? ORDER BY note_id", (sid,))]
        con.close()
        self.fids = [f["fragment_id"] for f in self.frags]
        # dense 문서 임베딩 1회
        self._doc_vecs = [_l2(v) for v in _embed([f["st"] or " " for f in self.frags])]
        # note 임베딩 1회 (sid별 노트 전체를 개행 결합 — 첫 노트만 쓰지 않는다)
        self._note_sids = [sid for sid in self.notes if self.notes[sid]]
        self._note_vecs = ([_l2(v) for v in _embed(
            ["\n".join(self.notes[sid]) for sid in self._note_sids])]
            if self._note_sids else [])

    # ── 채널별 랭킹: [(fid, 근거점수)] — 리스트에 없는 fid는 그 채널 미등재 ──
    def _dense_rank(self, qvec):
        scored = sorted(zip(self.fids, (_cos(qvec, d) for d in self._doc_vecs)),
                        key=lambda x: -x[1])
        return scored

    def _note_rank(self, qvec):
        if not self._note_sids:
            return []
        src_score = {sid: _cos(qvec, v) for sid, v in zip(self._note_sids, self._note_vecs)}
        ranked_sids = sorted(src_score, key=lambda s: -src_score[s])
        out = []
        for sid in ranked_sids:
            for f in self.frags:                       # 소스 점수를 소속 조각에 전파
                if f["source_id"] == sid:
                    out.append((f["fragment_id"], src_score[sid]))
        return out

    def _lexical_rank(self, query):
        tokens = [t for t in query.replace(",", " ").split() if len(t) >= 2]
        scored = []
        for f in self.frags:
            hay = (f["st"] or "") + " " + " ".join(self.notes.get(f["source_id"], []))
            hits = sum(1 for t in tokens if t in hay)
            if hits > 0:
                scored.append((f["fragment_id"], float(hits)))
        scored.sort(key=lambda x: -x[1])
        return scored

    def retrieve(self, work_order):
        """WorkOrderV2 → CandidateSet(list[dict]). exclude는 표기만, 순위 미반영."""
        keeps = [s.phrase for s in work_order.selectors if s.mode == "keep"]
        excludes = [s.phrase for s in work_order.selectors if s.mode == "exclude"]
        query = " ".join(keeps) if keeps else work_order.raw_user_text

        qvec = _l2(_embed([query])[0])
        channels = {
            "dense": self._dense_rank(qvec),
            "note": self._note_rank(qvec),
            "lexical": self._lexical_rank(query),
        }

        rrf = {fid: 0.0 for fid in self.fids}
        ranks = {fid: {} for fid in self.fids}
        for ch, lst in channels.items():
            for rank, (fid, _s) in enumerate(lst, 1):
                rrf[fid] += 1.0 / (RRF_K + rank)
                ranks[fid][ch] = rank

        by_fid = {f["fragment_id"]: f for f in self.frags}
        candidates = []
        for fid in sorted(self.fids, key=lambda f: -rrf[f]):
            f = by_fid[fid]
            src_notes = self.notes.get(f["source_id"], [])
            # exclude 표기(비파괴): exclude 어구가 조각 화면(search_text) 또는
            # 소스 노트에 나타나면 사유와 함께 excluded=true
            ex_reason = None
            for ex in excludes:
                if ex in (f["st"] or ""):
                    ex_reason = f"exclude '{ex}' matched search_text"
                    break
                if any(ex in n for n in src_notes):
                    ex_reason = f"exclude '{ex}' matched source note (evidence_scope=SOURCE)"
                    break
            candidates.append({
                "fid": fid,
                "channel_ranks": ranks[fid],
                "rrf_score": round(rrf[fid], 6),
                "evidence": {
                    "note": (" | ".join(src_notes)[:160] if src_notes else None),
                    "note_evidence_scope": "SOURCE" if src_notes else None,
                    "visual": (f["vd"][:120] or None),
                    "transcript": (f["tr"][:80] or None),
                },
                "excluded": ex_reason is not None,
                "excluded_reason": ex_reason,
            })
        return {"query_used": query, "channels_raw": {
                    ch: [(fid, round(s, 4)) for fid, s in lst] for ch, lst in channels.items()},
                "candidates": candidates}
