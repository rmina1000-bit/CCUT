import os

file_path = r"d:\CCUT1.0.4\ccut_frontend\src\pages\Index.tsx"

with open(file_path, "r", encoding="utf-8") as f:
    text = f.read()

# Analysis sequence block replacement
search_block = """              try {
                setAnalyzeMessage("?몄쭛 ?쒖븞 ?앹꽦 以?..");
                // [STEP 9] 2. Backend Proposal ?앹꽦 (POST /proposals/{source_id})
                try {
                  const quickScanRes = await fetch(
                    videoService.API_BASE_URL + "/quick-scan/" + firstSourceId
                  );
                  if (!quickScanRes.ok) {
                    throw new Error("Quick Scan 조회 실패 (" + quickScanRes.status + ")");
                  }
                  const quickScan = await quickScanRes.json();
                  setQuickScanData(quickScan);
                  setAnalyzeMessage("Quick Scan ?꾨즺");
                } catch (quickScanErr) {
                  console.warn("[Index] Quick Scan Error:", quickScanErr);
                  setAnalyzeMessage("Quick Scan 議고쉶 ?ㅽ뙣 - 怨꾩냽 吏꾪뻾");
                }

                setAnalyzeMessage("Semantic Fragment ?앹꽦 以?..");
                const semanticRes = await fetch(
                  videoService.API_BASE_URL + "/semantic-fragments/" + firstSourceId,
                  { method: "POST" }
                );
                if (!semanticRes.ok) {
                  throw new Error("Semantic Fragment 생성 실패 (" + semanticRes.status + ")");
                }
                const semanticData = await semanticRes.json();
                const semanticRows = semanticData.fragments || [];
                if (semanticRows.length === 0) {
                  throw new Error("Semantic Fragment 寃곌낵媛€ 鍮꾩뼱 ?덉뒿?덈떎.");
                }
                semanticReady = true;
                setSemanticFragments(semanticRows);
                setAnalyzeMessage("Semantic Fragment ?앹꽦 ?꾨즺");

                setAnalyzeMessage("?몄쭛 ?쒖븞 ?앹꽦 以?..");
                const proposalRes = await fetch(videoService.API_BASE_URL + "/proposals/" + firstSourceId, {
                  method: "POST"
                });
                if (!proposalRes.ok) throw new Error("諛깆뿏???쒖븞 ?앹꽦 ?ㅽ뙣");"""

replacement_block = """              try {
                setAnalyzeMessage("편집 제안 생성 중...");
                // [STEP 9] 2. Backend Proposal 생성 (POST /proposals/{source_id})
                try {
                  const quickScanRes = await fetch(
                    `${videoService.API_BASE_URL}/quick-scan/${firstSourceId}`
                  );
                  if (!quickScanRes.ok) {
                    throw new Error(`Quick Scan 조회 실패 (${quickScanRes.status})`);
                  }
                  const quickScan = await quickScanRes.json();
                  setQuickScanData(quickScan);
                  setAnalyzeMessage("Quick Scan 완료");
                } catch (quickScanErr) {
                  console.warn("[Index] Quick Scan Error:", quickScanErr);
                  setAnalyzeMessage("Quick Scan 조회 실패 - 계속 진행");
                }

                setAnalyzeMessage("Semantic Fragment 생성 중...");
                const semanticRes = await fetch(
                  `${videoService.API_BASE_URL}/semantic-fragments/${firstSourceId}`,
                  { method: "POST" }
                );
                if (!semanticRes.ok) {
                  throw new Error(`Semantic Fragment 생성 실패 (${semanticRes.status})`);
                }
                const semanticData = await semanticRes.json();
                const semanticRows = semanticData.fragments || [];
                if (semanticRows.length === 0) {
                  throw new Error("Semantic Fragment 결과가 비어 있습니다.");
                }
                semanticReady = true;
                setSemanticFragments(semanticRows);
                setAnalyzeMessage("Semantic Fragment 생성 완료");

                setAnalyzeMessage("편집 제안 생성 중...");
                const proposalRes = await fetch(`${videoService.API_BASE_URL}/proposals/${firstSourceId}`, {
                  method: "POST"
                });
                if (!proposalRes.ok) throw new Error("백엔드 제안 생성 실패");"""

if search_block in text:
    text = text.replace(search_block, replacement_block)
else:
    print("Block not found exactly. Trying partial fixes.")
    # Fallback to line by line if full block match fails
    text = text.replace('?몄쭛 ?쒖븞 ?앹꽦 以?..', '편집 제안 생성 중...')
    text = text.replace('Quick Scan ?꾨즺', 'Quick Scan 완료')
    text = text.replace('Quick Scan 議고쉶 ?ㅽ뙣 - 怨꾩냽 吏꾪뻾', 'Quick Scan 조회 실패 - 계속 진행')
    text = text.replace('Semantic Fragment ?앹꽦 以?..?곸긽', 'Semantic Fragment 생성 중...')
    text = text.replace('Semantic Fragment 寃곌낵媛€ 鍮꾩뼱 ?덉뒿?덈떎.', 'Semantic Fragment 결과가 비어 있습니다.')
    text = text.replace('Semantic Fragment ?앹꽦 ?꾨즺', 'Semantic Fragment 생성 완료')
    text = text.replace('諛깆뿏???쒖븞 ?앹꽦 ?ㅽ뙣', '백엔드 제안 생성 실패')

with open(file_path, "w", encoding="utf-8") as f:
    f.write(text)
