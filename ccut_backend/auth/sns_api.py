import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

class YouTubePublisher:
    def __init__(self):
        self.api_service_name = "youtube"
        self.api_version = "v3"

    def publish(self, video_path, title, description, credentials_dict=None):
        """
        [REAL SNS PUBLISH]
        ?ㅼ젣 援ш? OAuth ?좏겙???ъ슜?섏뿬 ?좏뒠釉?梨꾨꼸???곸긽??寃뚯떆?⑸땲??
        credentials_dict媛 ?놁쑝硫??쒕??덉씠?섏쑝濡??泥댄빀?덈떎.
        """
        if not credentials_dict:
            # OAuth ?좏겙 ?놁씠 媛쒕컻 以묒씪 ?뚯쓽 ?덉쟾???대갚
            print(f"[SIMULATION] ?먭꺽利앸챸 ?놁쓬 ???쒕??덉씠??紐⑤뱶濡??泥? {title}")
            return {
                "status": "SUCCESS",
                "video_id": "CCUT_DEV_PREVIEW",
                "url": "https://youtu.be/CCUT_DEV_PREVIEW"
            }

        credentials = Credentials.from_authorized_user_info(credentials_dict)
        youtube = build(self.api_service_name, self.api_version, credentials=credentials)

        # ?곸긽 硫뷀??곗씠???ㅼ젙
        request_body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": ["CCUT", "AI_PD", "Personal_Broadcasting"],
                "categoryId": "22"  # ?몃Ъ/釉붾줈洹?
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False
            }
        }

        # ?ㅼ젣 ?뚯씪 ?낅줈??媛앹껜 ?앹꽦 (?대젰 ?ш컻 媛?ν븳 resumable 諛⑹떇)
        media = MediaFileUpload(
            video_path,
            mimetype='video/mp4',
            resumable=True
        )

        print(f"REAL TRANSMISSION: [{title}] ?≪텧 ?쒖옉... (?뚯씪: {video_path})")

        # ?ㅼ젣 API ?몄텧 ?ㅽ뻾
        request = youtube.videos().insert(
            part="snippet,status",
            body=request_body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"... ?낅줈??吏꾪뻾瑜? {int(status.progress() * 100)}%")

        print(f"TRANSMISSION COMPLETE: https://youtu.be/{response['id']}")
        return {
            "status": "SUCCESS",
            "video_id": response['id'],
            "url": f"https://youtu.be/{response['id']}"
        }

sns_publisher = YouTubePublisher()

