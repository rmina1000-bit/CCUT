import uuid
import os
import asyncio
from archive.db_models import FragmentTable, SourceTable
from engine.video_engine import video_engine
from database import get_db
from sqlalchemy.orm import Session

class L1Scanner:
    """
    CCUT 1.0.3 - L1 Scanner (Pure DoD Implementation)
    紐⑺몴: 2~5珥??⑥쐞濡??곸긽???좎냽?섍쾶 遺꾪븷?섏뿬 ?뚮끂?쇰쭏 ?먯궛?쇰줈 蹂??
    ?뱀쭠: AI 遺???놁씠 FFmpeg留??ъ슜?섏뿬 洹밴컯???띾룄 蹂댁옣.
    """

    async def scan(self, source_id: str, db: Session):
        source = db.query(SourceTable).filter_by(source_id=source_id).first()
        if not source:
            raise ValueError(f"Source {source_id} not found")

        video_path = source.file_path
        total_duration = source.duration
        
        print(f"[L1] Scanning {video_path} for cognitive units...")
        
        from engine.signal_processor import SignalProcessor
        sp = SignalProcessor(video_path)
        
        # FFmpeg ?좏샇 湲곕컲 ?몄? ?⑥쐞 異붿텧 (DoD ?듭떖)
        try:
            segments = await asyncio.to_thread(sp.build_fragment_segments, total_duration)
        except Exception as e:
            print(f"[L1] SignalProcessor failed: {e}. Falling back to fixed 3.5s.")
            segments = [
                {"index": i, "start": i*3.5, "end": min((i+1)*3.5, total_duration), "duration": 3.5}
                for i in range(int(total_duration // 3.5) + 1)
            ]

        fragments = []
        for seg in segments:
            current_time = seg["start"]
            dur = seg["duration"]
            
            if dur <= 0: continue
                
            frag_id = f"L1_{uuid.uuid4().hex[:6].upper()}_{source_id}"
            
            # 臾쇰━ ?뚯씪 諛??몃꽕???앹꽦
            # [VIRTUAL CLIPPING (N-01)] 臾쇰━??議곌컖 ?뚯씪 ?앹꽦??諛곗젣?섍퀬 硫뷀??곗씠?곕줈留?愿由ы빀?덈떎.
            thumb_path = await asyncio.to_thread(
                video_engine.extract_thumbnail, video_path, current_time, frag_id
            )
            
            # [N-04] Waveform extraction
            from engine.audio_engine import audio_engine
            wav_data = await asyncio.to_thread(
                audio_engine.get_waveform_data, video_path, dur, 100
            )
            
            frag_data = {
                "fragment_id": frag_id,
                "source_id": source_id,
                "start_time": round(current_time, 2),
                "end_time": round(seg["end"], 2),
                "duration": round(dur, 2),
                "intelligence": {
                    "type": "L1_COGNITIVE",
                    "thumb_url": f"http://localhost:8000/static/thumbnails/{frag_id}.jpg",
                    "transcript": "???遺꾩꽍 以?.. (Whisper)"
                },
                "waveform": wav_data,
                "status": "AVAILABLE"
            }
            fragments.append(frag_data)
            
            # DB ???
            new_frag = FragmentTable(
                fragment_id=frag_id,
                source_id=source_id,
                start_time=frag_data["start_time"],
                end_time=frag_data["end_time"],
                duration=frag_data["duration"],
                intelligence=frag_data["intelligence"],
                waveform=frag_data["waveform"]
            )
            db.add(new_frag)
            
        db.commit()
        print(f"[L1] Completed. Created {len(fragments)} cognitive fragments.")
        return fragments

l1_scanner = L1Scanner()

