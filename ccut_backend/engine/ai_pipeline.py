import os
import uuid
from engine.video_engine import video_engine
from engine.ai_engine import ai_engine
from engine.signal_processor import SignalProcessor

class AIPipeline:
    def __init__(self):
        print("AI Pipeline Initialized (Combined Intelligence)")

    async def process_video(self, source):
        video_path = source.file_path
        total_duration = source.duration
        
        sp = SignalProcessor(video_path)
        try:
            segments = sp.build_fragment_segments(total_duration)
            analysis_mode = "SIGNAL"
        except:
            segments = [{"index": 0, "start": 0.0, "end": 5.0, "duration": 5.0}]
            analysis_mode = "FALLBACK"

        fragments_data = []
        for seg in segments:
            frag_id = f"F_{uuid.uuid4().hex[:6]}"
            # Simulating pipeline flow
            transcript = ai_engine.transcribe_segment(video_path, seg['start'], seg['end'])
            intelligence = ai_engine.analyze_intelligence(transcript, f_start=seg['start'], f_end=seg['end'])
            
            fragments_data.append({
                "id": frag_id,
                "fragment_id": frag_id,
                "source_id": source.source_id,
                "start": seg['start'],
                "end": seg['end'],
                "duration": seg['duration'],
                "intelligence": intelligence
            })
        
        return fragments_data, analysis_mode

ai_pipeline = AIPipeline()
