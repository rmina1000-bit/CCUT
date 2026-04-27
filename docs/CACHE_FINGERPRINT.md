# CACHE + FINGERPRINT v3.2.1
> 기준: CCUT 1.0.4 PROJECT NAVIGATION v3.2.1  
> 핵심: 영상 → Proxy/Segment → Evidence Board → Semantic Fragment → Proposal(JSON) → ExportInput → Render  
> 절대 원칙: Evidence 없이 Semantic 금지 / Semantic 없이 Proposal 금지 / Proposal 없이 Export 금지

## Multi-Layer Cache
### L1 RAM
- Evidence Buffer
- 최근 keyframe cache
- 현재 transcript cache

### L2 Disk
- proxy 영상
- transcript 전체
- keyframe 전체
- Evidence Board 최종 저장

### L3 DB
- semantic fragment
- proposal
- decision log
- user pattern

## Fingerprint
- SHA256 또는 perceptual hash
- duration/fps/resolution/audio hash 보조

## 규칙
- 동일 fingerprint는 재분석 금지
- L3 → L2 → L1 순서로 조회
- cache hit 시 즉시 반환
- Evidence 변경 시 L2 갱신
- Fragment/Proposal 변경 시 L3 갱신

## PASS
- 동일 영상 재업로드 시 cache hit
- User Intent만 변경 시 Semantic re-score 또는 Proposal 재생성만 수행
