import os

file_path = r"d:\CCUT1.0.4\ccut_frontend\src\pages\Index.tsx"

with open(file_path, "r", encoding="utf-8") as f:
    text = f.read()

mapping = {
    '"?놁쓬"': '"없음"',
    "A???쒖꽌": "A안 순서",
    "B???쒖꽌": "B안 순서",
    "A/B 泥?議곌컖 ?ㅻ쫫": "A/B 첫 조각 다름",
    "?곸긽???낅줈?쒗븯??以묒엯?덈떎...": "영상을 업로드하는 중입니다...",
    "?좏깮???뚯씪???놁뒿?덈떎.": "선택된 파일이 없습니다.",
    "泥?議곌컖 thumb:": "첫 조각 thumb:",
    "?곸긽 ?뚯씪???쒕쾭???꾩넚?섎뒗 以묒엯?덈떎...": "영상 파일을 서버에 전송하는 중입니다...",
    "?곸긽 ${label} ?낅줈??以?..": "영상 ${label} 업로드 중...",
    "媛?珥덈쾶 議곌컖 ?꾨즺": "개 초벌 조각 완료",
    "泥?踰덉㎏ ?먮낯 泥섎━ ?ㅽ뙣": "첫 번째 원본 처리 실패",
    "?섎?遺꾩꽍(Whisper) 吏꾪뻾 以묒엯?덈떎...": "의미분석(Whisper) 진행 중입니다...",
    "source_id ?뺤씤 ?ㅽ뙣": "source_id 확인 실패",
    "?몄쭛 ?쒖븞 ?앹꽦 以?..": "편집 제안 생성 중...",
    "Quick Scan ?꾨즺": "Quick Scan 완료",
    "Quick Scan 議고쉶 ?ㅽ뙣 - 怨꾩냽 吏꾪뻾": "Quick Scan 조회 실패 - 계속 진행",
    "Semantic Fragment ?앹꽦 以?..": "Semantic Fragment 생성 중...",
    "Semantic Fragment 寃곌낵媛€ 鍮꾩뼱 ?덉뒿?덈떎.": "Semantic Fragment 결과가 비어 있습니다.",
    "Semantic Fragment ?앹꽦 ?꾨즺": "Semantic Fragment 생성 완료",
    "諛깆뿏???쒖븞 ?앹꽦 ?ㅽ뙣": "백엔드 제안 생성 실패",
    "?쒖옣???몄쭛 (A)": "시장형 편집 (A)",
    "?ъ슜?먯튇?뷀삎 ?몄쭛 (B)": "사용자친화형 편집 (B)",
    "諛깆뿏??遺꾩꽍 湲곕컲 異붿쿇 ?몄쭛?엯?덈떎.": "백엔드 분석 기반 추천 편집안입니다.",
    "Semantic Fragment 議고쉶 ?ㅽ뙣": "Semantic Fragment 조회 실패",
    "?섎? ?곗씠??遺꾩궛 遺€議???": "의미 데이터 분산 부족",
    "遺꾩꽍 ?꾨즺 ?????뺢탳???쒖븞???앹꽦?⑸땲??": "분석 완료 후 더 정교한 제안이 생성됩니다.",
    "遺꾩꽍 ?꾨즺!": "분석 완료!",
    "諛깃렇?쇱슫?쒖뿉??怨꾩냽 吏꾪뻾?????덉뒿?덈떎": "백엔드에서 계속 진행될 수 있습니다",
    "遺꾩꽍 ?ㅽ뙣:": "분석 실패:",
    "遺꾩꽍 以??ㅻ쪟媛€ 諛쒖깮?덉뒿?덈떎. 肄섏넄???뺤씤??二쇱꽭??": "분석 중 오류가 발생했습니다. 콘솔을 확인해 주세요.",
    "sourceFragments媛€ ?놁뼱 ?ъ젣?덉쓣 嫄대꼫?곷땲??": "sourceFragments가 없어 재제안을 건너뜁니다.",
    "?섏텧 ?ㅽ뙣:": "내보내기 실패:",
    "?쒕쾭 ?곌껐 ?ㅻ쪟": "서버 연결 오류",
    "??怨좎쑀 ID 遺€?????먮낯怨?援щ텇?섎뒗 蹂듭궗蹂?": "새 고유 ID 부여 — 원본과 구분되는 복사본",
    "遺꾩꽍 ?쒓컙 珥덇낵": "분석 시간 초과",
    "// [STEP 9] 2. Backend Proposal ?앹꽦": "// [STEP 9] 2. Backend Proposal 생성",
    "Semantic Fragment 생성 실패 (": "Semantic Fragment 생성 실패 (" # No change needed but to be safe
}

for src, dst in mapping.items():
    text = text.replace(src, dst)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(text)
