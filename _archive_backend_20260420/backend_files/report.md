### 1. uvicorn.log 최근 내역
```text
INFO:     Started server process [5936]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
Voice Engine Initialized (Simulation)
Vector Engine Initialized [MODE: simulation]
Search Engine Initialized (Simulation)
Vision Engine Initialized (Simulation)
LLM Engine Initialized (Simulation)
Generative Engine Initialized (Simulation)
AI PD Engine Initialized (Lazy Mode)
AI Pipeline Initialized (Combined Intelligence)
INFO:     127.0.0.1:59857 - "GET /docs HTTP/1.1" 200 OK
INFO:     127.0.0.1:59857 - "GET /openapi.json HTTP/1.1" 200 OK
[UPLOAD] ���� �Ϸ�: D:\CCUT_1.0.3\ccut_backend\storage\uploads\20130512_143229.mp4 �� source_id=SRC_48FDD88F
INFO:     127.0.0.1:65524 - "POST /upload HTTP/1.1" 200 OK
[GENERATE-FRAGMENTS] source_id=SRC_48FDD88F (Registry) �� D:\CCUT_1.0.3\ccut_backend\storage\uploads\20130512_143229.mp4
[GENERATE-FRAGMENTS] ����: D:\CCUT_1.0.3\ccut_backend\storage\uploads\20130512_143229.mp4
[SignalProcessor] Starting cognitive analysis for 54.381134s video...
[SignalProcessor] Created 16 cognitive segments.
[GENERATE-FRAGMENTS] 16�� ���׸�Ʈ Ž�� (SIGNAL_BASED)
[GENERATE-FRAGMENTS] L1 �Ϸ�. 16�� Virtual Fragment ��� ��ȯ.
INFO:     127.0.0.1:57283 - "POST /generate-fragments?source_id=SRC_48FDD88F HTTP/1.1" 200 OK
[PIPELINE] Whisper pipeline STARTED
AI PD Engine Initialized (Lazy Mode)
INFO:     127.0.0.1:58340 - "GET /static/thumbnails/VF1_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:55821 - "GET /static/thumbnails/VF2_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:63921 - "GET /static/thumbnails/VF4_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:51452 - "GET /static/thumbnails/VF3_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:52724 - "GET /static/thumbnails/VF5_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:50507 - "GET /static/thumbnails/VF6_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:50788 - "GET /static/thumbnails/VF1_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:55930 - "GET /static/thumbnails/VF3_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:51768 - "GET /static/thumbnails/VF4_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:60942 - "GET /static/thumbnails/VF2_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:64570 - "GET /static/thumbnails/VF5_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:49163 - "GET /static/thumbnails/VF6_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:56452 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 200 OK
INFO:     127.0.0.1:61229 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 304 Not Modified
INFO:     127.0.0.1:58893 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 304 Not Modified
INFO:     127.0.0.1:63738 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 304 Not Modified
INFO:     127.0.0.1:51473 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 200 OK
INFO:     127.0.0.1:51472 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 200 OK
INFO:     127.0.0.1:59556 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 200 OK
INFO:     127.0.0.1:51437 - "GET /static/thumbnails/VF11_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:49508 - "GET /static/thumbnails/VF12_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:50981 - "GET /static/thumbnails/VF10_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:62687 - "GET /static/thumbnails/VF8_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:64902 - "GET /static/thumbnails/VF9_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:49498 - "GET /static/thumbnails/VF7_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:49190 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 304 Not Modified
INFO:     127.0.0.1:65109 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 304 Not Modified
INFO:     127.0.0.1:53528 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 200 OK
INFO:     127.0.0.1:53529 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 200 OK
INFO:     127.0.0.1:59116 - "GET /static/thumbnails/VF16_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:63308 - "GET /static/thumbnails/VF13_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:54422 - "GET /static/thumbnails/VF14_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:50545 - "GET /static/thumbnails/VF15_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:64791 - "GET /static/thumbnails/VF11_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:60884 - "GET /static/thumbnails/VF12_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:49511 - "GET /static/thumbnails/VF10_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:63878 - "GET /static/thumbnails/VF8_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:61050 - "GET /static/thumbnails/VF9_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:54881 - "GET /static/thumbnails/VF16_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:65066 - "GET /static/thumbnails/VF7_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:61975 - "GET /static/thumbnails/VF13_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:65295 - "GET /static/thumbnails/VF14_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:59184 - "GET /static/thumbnails/VF15_SRC_48FDD88F.jpg HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:60828 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 200 OK
INFO:     127.0.0.1:60829 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 200 OK
INFO:     127.0.0.1:54466 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 304 Not Modified
INFO:     127.0.0.1:56076 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 304 Not Modified
INFO:     127.0.0.1:52100 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 304 Not Modified
INFO:     127.0.0.1:55999 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 304 Not Modified
INFO:     127.0.0.1:56599 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 200 OK
INFO:     127.0.0.1:64119 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 200 OK
INFO:     127.0.0.1:62212 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 200 OK
INFO:     127.0.0.1:63163 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 200 OK
[LlamaServer] �⵿: D:/CCUT_1.0.3/tools/llama.cpp/llama-server.exe -m D:/CCUT_1.0.3/ccut_backend/ai_models/qwen3-asr-0.6b/Qwen3-ASR-0.6B-Q8_0.gguf --port 8091 --host 127.0.0.1 --ctx-size 4096 --n-gpu-layers 0 --mmproj D:/CCUT_1.0.3/ccut_backend/ai_models/qwen3-asr-0.6b/mmproj-Qwen3-ASR-0.6B-Q8_0.gguf
[LlamaServer] �غ� �Ϸ� �� port=8091
INFO:     127.0.0.1:61013 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:57300 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 200 OK
INFO:     127.0.0.1:57301 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 200 OK
INFO:     127.0.0.1:65351 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:63069 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:54377 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:58216 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:61078 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:60316 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:65324 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:63164 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 200 OK
INFO:     127.0.0.1:63165 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 200 OK
INFO:     127.0.0.1:55658 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:52819 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:50558 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:55472 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:51810 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:63353 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:59158 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:51781 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:64839 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:53587 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:61979 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:63850 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:52413 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:56182 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:61474 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:49478 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:51474 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:55517 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:54983 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:65102 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
[ASR BG] VF1_SRC_48FDD88F | hook=0.381 | role=Intro | transcript='language None<asr_te'
[ASR BG] VF2_SRC_48FDD88F | hook=0.512 | role=Main | transcript='language None<asr_te'
[ASR BG] VF3_SRC_48FDD88F | hook=0.708 | role=Hook | transcript='language Korean<asr_'
[ASR BG] VF4_SRC_48FDD88F | hook=0.381 | role=Intro | transcript='language None<asr_te'
[ASR BG] VF5_SRC_48FDD88F | hook=0.554 | role=Main | transcript='language Chinese<asr'
INFO:     127.0.0.1:63379 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
[ASR BG] VF6_SRC_48FDD88F | hook=0.381 | role=Main | transcript='language Chinese<asr'
[ASR BG] VF7_SRC_48FDD88F | hook=0.381 | role=Main | transcript='language None<asr_te'
[ASR BG] VF8_SRC_48FDD88F | hook=0.381 | role=Main | transcript='language Chinese<asr'
[ASR BG] VF9_SRC_48FDD88F | hook=0.554 | role=Main | transcript='language Chinese<asr'
[ASR BG] VF10_SRC_48FDD88F | hook=0.512 | role=Main | transcript='language Korean<asr_'
[ASR BG] VF11_SRC_48FDD88F | hook=0.381 | role=Main | transcript='language Chinese<asr'
[ASR BG] VF12_SRC_48FDD88F | hook=0.381 | role=Main | transcript='language Chinese<asr'
[ASR BG] VF13_SRC_48FDD88F | hook=0.381 | role=Main | transcript='language Chinese<asr'
[ASR BG] VF14_SRC_48FDD88F | hook=0.381 | role=Main | transcript='language Chinese<asr'
INFO:     127.0.0.1:54295 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
[ASR BG] VF15_SRC_48FDD88F | hook=0.381 | role=Closing | transcript='language Chinese<asr'
[ASR BG] VF16_SRC_48FDD88F | hook=0.381 | role=Closing | transcript='language Chinese<asr'
[REBALANCE] ���� | unique={'Intro', 'Closing', 'Main', 'Hook'} | count=16
[hook-log] ���� �Ϸ�: logs/hook_distribution/SRC_48FDD88F.json
[ASR BG] SRC_48FDD88F �Ϸ�
[PANORAMA BG] source_id=SRC_48FDD88F �ĳ�� ���� ����
[PANORAMA BG] VF1_SRC_48FDD88F ����� ���� �Ϸ�: d:\CCUT_1.0.3\ccut_backend\storage\thumbnails\VF1_SRC_48FDD88F.jpg
[PANORAMA BG] VF2_SRC_48FDD88F ����� ���� �Ϸ�: d:\CCUT_1.0.3\ccut_backend\storage\thumbnails\VF2_SRC_48FDD88F.jpg
[PANORAMA BG] VF3_SRC_48FDD88F ����� ���� �Ϸ�: d:\CCUT_1.0.3\ccut_backend\storage\thumbnails\VF3_SRC_48FDD88F.jpg
[PANORAMA BG] VF4_SRC_48FDD88F ����� ���� �Ϸ�: d:\CCUT_1.0.3\ccut_backend\storage\thumbnails\VF4_SRC_48FDD88F.jpg
[PANORAMA BG] VF5_SRC_48FDD88F ����� ���� �Ϸ�: d:\CCUT_1.0.3\ccut_backend\storage\thumbnails\VF5_SRC_48FDD88F.jpg
[PANORAMA BG] VF6_SRC_48FDD88F ����� ���� �Ϸ�: d:\CCUT_1.0.3\ccut_backend\storage\thumbnails\VF6_SRC_48FDD88F.jpg
[PANORAMA BG] VF7_SRC_48FDD88F ����� ���� �Ϸ�: d:\CCUT_1.0.3\ccut_backend\storage\thumbnails\VF7_SRC_48FDD88F.jpg
[PANORAMA BG] VF8_SRC_48FDD88F ����� ���� �Ϸ�: d:\CCUT_1.0.3\ccut_backend\storage\thumbnails\VF8_SRC_48FDD88F.jpg
[PANORAMA BG] VF9_SRC_48FDD88F ����� ���� �Ϸ�: d:\CCUT_1.0.3\ccut_backend\storage\thumbnails\VF9_SRC_48FDD88F.jpg
[PANORAMA BG] VF10_SRC_48FDD88F ����� ���� �Ϸ�: d:\CCUT_1.0.3\ccut_backend\storage\thumbnails\VF10_SRC_48FDD88F.jpg
INFO:     127.0.0.1:59108 - "GET /generate-fragments/status/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:61232 - "GET /fragments/SRC_48FDD88F HTTP/1.1" 200 OK
INFO:     127.0.0.1:59625 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 200 OK
INFO:     127.0.0.1:59626 - "GET /static/uploads/20130512_143229.mp4 HTTP/1.1" 200 OK
[PANORAMA BG] VF11_SRC_48FDD88F ����� ���� �Ϸ�: d:\CCUT_1.0.3\ccut_backend\storage\thumbnails\VF11_SRC_48FDD88F.jpg
[PANORAMA BG] VF12_SRC_48FDD88F ����� ���� �Ϸ�: d:\CCUT_1.0.3\ccut_backend\storage\thumbnails\VF12_SRC_48FDD88F.jpg
INFO:     127.0.0.1:53631 - "GET /static/thumbnails/VF3_SRC_48FDD88F.jpg HTTP/1.1" 200 OK
INFO:     127.0.0.1:59507 - "GET /static/thumbnails/VF9_SRC_48FDD88F.jpg HTTP/1.1" 200 OK
[PANORAMA BG] VF13_SRC_48FDD88F ����� ���� �Ϸ�: d:\CCUT_1.0.3\ccut_backend\storage\thumbnails\VF13_SRC_48FDD88F.jpg
[PANORAMA BG] VF14_SRC_48FDD88F ����� ���� �Ϸ�: d:\CCUT_1.0.3\ccut_backend\storage\thumbnails\VF14_SRC_48FDD88F.jpg
[PANORAMA BG] VF15_SRC_48FDD88F ����� ���� �Ϸ�: d:\CCUT_1.0.3\ccut_backend\storage\thumbnails\VF15_SRC_48FDD88F.jpg
[PANORAMA BG] VF16_SRC_48FDD88F ����� ���� �Ϸ�: d:\CCUT_1.0.3\ccut_backend\storage\thumbnails\VF16_SRC_48FDD88F.jpg
[PANORAMA BG] source_id=SRC_48FDD88F �ĳ�� ��ü �Ϸ�
INFO:     127.0.0.1:64587 - "GET /static/thumbnails/VF5_SRC_48FDD88F.jpg HTTP/1.1" 200 OK
INFO:     127.0.0.1:64587 - "GET /static/thumbnails/VF2_SRC_48FDD88F.jpg HTTP/1.1" 200 OK
INFO:     127.0.0.1:64587 - "GET /static/thumbnails/VF10_SRC_48FDD88F.jpg HTTP/1.1" 200 OK
INFO:     127.0.0.1:64587 - "GET /static/thumbnails/VF1_SRC_48FDD88F.jpg HTTP/1.1" 200 OK
INFO:     127.0.0.1:64587 - "GET /static/thumbnails/VF4_SRC_48FDD88F.jpg HTTP/1.1" 200 OK
INFO:     127.0.0.1:64587 - "GET /static/thumbnails/VF6_SRC_48FDD88F.jpg HTTP/1.1" 200 OK
INFO:     127.0.0.1:64587 - "GET /static/thumbnails/VF11_SRC_48FDD88F.jpg HTTP/1.1" 200 OK
INFO:     127.0.0.1:63642 - "GET /static/thumbnails/VF12_SRC_48FDD88F.jpg HTTP/1.1" 200 OK
INFO:     127.0.0.1:51186 - "GET /static/thumbnails/VF14_SRC_48FDD88F.jpg HTTP/1.1" 200 OK
INFO:     127.0.0.1:59765 - "GET /static/thumbnails/VF13_SRC_48FDD88F.jpg HTTP/1.1" 200 OK
INFO:     127.0.0.1:57922 - "GET /static/thumbnails/VF16_SRC_48FDD88F.jpg HTTP/1.1" 200 OK
INFO:     127.0.0.1:58085 - "GET /static/thumbnails/VF15_SRC_48FDD88F.jpg HTTP/1.1" 200 OK
```
### 2. DB Schema Error 및 Data(intelligence)
명령하신 `transcript` 컬럼은 스키마 상 존재하지 않아 쿼리 에러가 발생했습니다. DB 테이블에는 `intelligence` (JSON) 컬럼만 존재함을 확인하여 이를 대신 추출합니다.
```text
DB Error: no such column: source_video
```