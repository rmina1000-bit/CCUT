# -*- coding: utf-8 -*-
"""[SNS-YT] YouTube 실업로드 통로 (Data API v3, Desktop OAuth).

선행조사(2026-07-04):
  - videos.insert 쿼터 1600->100유닛(2025-12 인하) => 무료 티어로 하루 ~100개 업로드 가능
  - Desktop app OAuth: client_secret.json 필요 (사용자 Google Cloud 콘솔에서 발급)
  - Shorts 판정은 세로 비율+길이(<=3분)로 자동 — 별도 API 없음, #Shorts는 설명에
준비물(1회):
  1) console.cloud.google.com -> 프로젝트 -> YouTube Data API v3 사용 설정
  2) OAuth 동의화면(외부/테스트) + 사용자 본인 이메일을 테스트 사용자로 추가
  3) 사용자 인증 정보 -> OAuth 클라이언트 ID(데스크톱 앱) -> JSON 다운로드
  4) 그 파일을 runtime/sns/client_secret.json 로 저장
토큰: runtime/sns/youtube_token.json (refresh 포함, 자동 갱신)
"""
import json
import os

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(BACKEND_DIR)
SNS_DIR = os.path.join(ROOT, "runtime", "sns")
CLIENT_SECRET = os.path.join(SNS_DIR, "client_secret.json")
TOKEN_PATH = os.path.join(SNS_DIR, "youtube_token.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]


def _load_creds():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    if not os.path.exists(TOKEN_PATH):
        return None
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_PATH, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
        return creds if creds.valid else None
    except Exception as e:
        print(f"[SNS-YT] token load fail: {e}")
        return None


def _service(creds):
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def status() -> dict:
    """{configured, connected, channel_title}"""
    configured = os.path.exists(CLIENT_SECRET)
    creds = _load_creds() if configured else None
    channel = None
    if creds:
        try:
            res = _service(creds).channels().list(part="snippet", mine=True).execute()
            items = res.get("items") or []
            if items:
                channel = items[0]["snippet"]["title"]
        except Exception as e:
            print(f"[SNS-YT] channel check fail: {e}")
            creds = None
    return {"configured": configured, "connected": bool(creds), "channel_title": channel,
            "client_secret_path": CLIENT_SECRET}


def connect() -> dict:
    """브라우저 OAuth (이 PC에서 열림). 성공 시 토큰 저장."""
    if not os.path.exists(CLIENT_SECRET):
        return {"status": "NOT_CONFIGURED",
                "message": f"client_secret.json이 없습니다: {CLIENT_SECRET}"}
    from google_auth_oauthlib.flow import InstalledAppFlow
    os.makedirs(SNS_DIR, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent",
                                  authorization_prompt_message="")
    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    st = status()
    print(f"[SNS-YT] connected: {st.get('channel_title')}")
    return {"status": "OK", **st}


def disconnect() -> dict:
    if os.path.exists(TOKEN_PATH):
        os.remove(TOKEN_PATH)
    return {"status": "OK"}


def upload(file_path: str, title: str, description: str = "",
           privacy: str = "private", tags=None) -> dict:
    """실업로드 (resumable). privacy: private|unlisted|public.
    Shorts 여부는 유튜브가 비율/길이로 자동 판정 — 설명에 #Shorts만 거든다."""
    if not os.path.exists(file_path):
        return {"status": "ERROR", "message": f"파일 없음: {file_path}"}
    creds = _load_creds()
    if not creds:
        return {"status": "NOT_CONNECTED", "message": "먼저 YouTube 채널을 연결하세요"}
    from googleapiclient.http import MediaFileUpload
    body = {
        "snippet": {
            "title": (title or "CCUT 편집 영상")[:95],
            "description": ((description or "").rstrip() + "\n\n#Shorts").strip(),
            "tags": tags or ["CCUT"],
            "categoryId": "22",  # People & Blogs
        },
        "status": {"privacyStatus": privacy if privacy in ("private", "unlisted", "public") else "private",
                    "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(file_path, chunksize=4 * 1024 * 1024, resumable=True, mimetype="video/mp4")
    req = _service(creds).videos().insert(part="snippet,status", body=body, media_body=media)
    print(f"[SNS-YT] upload start: {os.path.basename(file_path)} ({os.path.getsize(file_path)//1024//1024}MB)")
    resp = None
    while resp is None:
        st_, resp = req.next_chunk()
        if st_:
            print(f"[SNS-YT] upload {int(st_.progress() * 100)}%")
    vid = resp.get("id")
    url = f"https://youtube.com/watch?v={vid}"
    print(f"[SNS-YT] upload done: {url} (privacy={privacy})")
    return {"status": "OK", "video_id": vid, "url": url, "privacy": privacy}
