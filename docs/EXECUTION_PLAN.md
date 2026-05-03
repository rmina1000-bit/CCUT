# EXECUTION_PLAN v3.3.0

> 기준: CCUT 1.0.4 PROJECT NAVIGATION v3.3.0  
> 핵심: 영상 → 분석 → 편집스토리 초안 → 사용자 협의 → StoryIntent → A/B 제안 → Render  
> **현재 기준 SHA:** `56554c70e76ad03537193d5b560fd19457ce2477`

## Updated Core Execution Flow

1. Upload Source Videos
2. Proxy / Segment / Fingerprint (STEP 1)
3. Evidence Board (STEP 2)
4. Semantic Fragment (STEP 4)
5. Quick Scan / Hypothesis (STEP 3)
6. **Narrative Consultation (New)**
   - 분석 결과를 편집스토리 초안으로 변환
   - 사용자에게 먼저 이야기 방향을 묻는다
   - 사용자의 자연어 의견을 StoryIntent로 정리
7. **Proposal Generation**
   - StoryIntent 확정 후 A/B 제안 생성
   - A안: 시장형/하이라이트형
   - B안: 사용자 의도 반영형/기록형
8. Preview / Commit
9. ExportInput (STEP 7)
10. Render (STEP 8)

## Prohibited Order

- 분석 직후 A/B 제안 즉시 노출 금지
- 사용자 협의 전 편집 제안 영상 노출 금지
- StoryIntent 없이 ProposalEngine에 사용자 의도를 강하게 반영했다고 주장 금지
- Narrative Consultation 이전 Export/Render 접근 금지

## Next Priority

1. R10-D: Ollama Timeout / keep_alive / JSON Stabilization (Current)
2. ChatGPT Form Narrative Chat Repair
3. StoryIntent → Proposal Request 연결
4. AI Boundary Integration with main.py (Non-runtime to Runtime)

---

## Completed Steps

## STEP 0. 기준선 확보 ✅ PASS
... (이하 기존 내용 유지)

## STEP 6. Proposal Engine ✅ PASS (Re-positioned after Narrative)
- backend semantic 기반 A/B 생성
- StoryIntent를 입력값으로 받도록 확장 예정

... (이하 기존 내용 유지)
