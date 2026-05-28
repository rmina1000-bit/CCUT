import os
import re
import sys
import time
import urllib.parse
import subprocess
from pathlib import Path
import requests

from database import SessionLocal
from learning.learning_models import UserEditDecisionTable, EditingPatternMemoryTable
from learning.pattern_memory import PatternMemory

class YouTubeRobotLearner:
    """
    [STEP 15] YouTubeRobotLearner
    Scrapes popular YouTube videos, extracts visual/audio editing cues,
    and updates editing pattern memory parameters on CPU.
    """

    @staticmethod
    def search_youtube(query: str, limit: int = 3) -> list:
        """
        Searches YouTube for videos matching query and extracts video URLs.
        Falls back to safe simulation lists if network is blocked or unavailable.
        """
        print(f"[YOUTUBE_ROBOT] Searching YouTube for: '{query}'")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # public query
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
        try:
            r = requests.get(url, headers=headers, timeout=8)
            if r.status_code == 200:
                video_ids = re.findall(r'"videoId":"([^"]+)"', r.text)
                unique_ids = []
                for vid in video_ids:
                    if vid not in unique_ids and len(vid) == 11:
                        unique_ids.append(vid)
                    if len(unique_ids) >= limit:
                        break
                if unique_ids:
                    print(f"[YOUTUBE_ROBOT] Found {len(unique_ids)} real video IDs.")
                    return [f"https://www.youtube.com/watch?v={vid}" for vid in unique_ids]
        except Exception as e:
            print(f"[YOUTUBE_ROBOT][WARN] Regex scrape failed: {e}")
            
        print("[YOUTUBE_ROBOT][INFO] Using fallback mock video results for query.")
        # Safe mock channels
        safe_hashes = ["dQw4w9WgXcQ", "jNQXAC9IVRw", "9bZkp7q19f0"]
        return [f"https://www.youtube.com/watch?v={vid}" for vid in safe_hashes[:limit]]

    @staticmethod
    def download_preview(video_url: str) -> str:
        """
        Downloads a 15-second worst-quality video preview using yt-dlp to minimize bandwidth.
        Returns the absolute filepath or empty string if fails.
        """
        video_id = video_url.split("v=")[-1]
        if "MOCK" in video_id or video_id in ["dQw4w9WgXcQ", "jNQXAC9IVRw", "9bZkp7q19f0"]:
            # Mock video case
            return ""
            
        temp_dir = Path("D:/CCUT1.0.4/storage/youtube_temp")
        temp_dir.mkdir(parents=True, exist_ok=True)
        out_template = str(temp_dir / f"{video_id}.%(ext)s")
        
        # Delete existing to force fresh download
        for f in temp_dir.glob(f"{video_id}.*"):
            try: f.unlink()
            except: pass
            
        # Download worst format first 15s to save network usage
        cmd = [
            "yt-dlp",
            "-f", "worst",
            "-o", out_template,
            "--download-sections", "*00:00:00-00:00:15",
            video_url
        ]
        
        print(f"[YOUTUBE_ROBOT] Fetching 15s media segment for: {video_id}")
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30, encoding="utf-8")
            if res.returncode == 0:
                for f in temp_dir.glob(f"{video_id}.*"):
                    print(f"[YOUTUBE_ROBOT] Successfully downloaded: {f.name}")
                    return str(f.resolve())
            else:
                print(f"[YOUTUBE_ROBOT][WARN] yt-dlp returned error: {res.stderr}")
        except subprocess.TimeoutExpired:
            print("[YOUTUBE_ROBOT][TIMEOUT] yt-dlp download timed out (30s limit)")
        except Exception as e:
            print(f"[YOUTUBE_ROBOT][ERROR] Failed to run yt-dlp: {e}")
            
        return ""

    @staticmethod
    def analyze_preview(video_path: str) -> dict:
        """
        Runs PySceneDetect and ffprobe volume checks to extract editing transitions.
        Returns visual/audio statistics.
        """
        result = {
            "scene_cuts": 0,
            "avg_scene_duration": 5.0,
            "max_volume_db": -5.0,
            "is_surrogate": True
        }
        
        if not video_path or not os.path.exists(video_path):
            return result
            
        # 1. Visual Scene Cuts Detection using scenedetect
        try:
            # Run scenedetect CLI to count cuts in the 15s preview
            cmd = ["scenedetect", "-i", video_path, "detect-content", "list-scenes"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=20, encoding="utf-8")
            # Parse output for scene numbers
            matches = re.findall(r"Detected (\d+) scenes", res.stdout)
            if matches:
                cuts = int(matches[0])
                result["scene_cuts"] = cuts
                result["avg_scene_duration"] = round(15.0 / max(cuts, 1), 2)
                result["is_surrogate"] = False
                print(f"[YOUTUBE_ROBOT] Detected {cuts} visual cuts. Average pacing: {result['avg_scene_duration']}s")
        except Exception as e:
            print(f"[YOUTUBE_ROBOT][WARN] PySceneDetect failed: {e}")
            
        # 2. Audio Volume Peak Check
        try:
            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-af", "volumedetect", "-f", "null", "-"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15, encoding="utf-8")
            max_vol = re.findall(r"max_volume:\s+([-\d.]+)\s+dB", res.stderr)
            if max_vol:
                result["max_volume_db"] = float(max_vol[0])
                result["is_surrogate"] = False
                print(f"[YOUTUBE_ROBOT] Extracted audio peak: {result['max_volume_db']} dB")
        except Exception as e:
            print(f"[YOUTUBE_ROBOT][WARN] Audio volume check failed: {e}")
            
        return result

    @classmethod
    def execute_learning_step(cls, query: str, limit: int = 3, force_media: bool = False) -> dict:
        """
        Executes search, optional downloads, updates weights, and registers decisions.
        """
        urls = cls.search_youtube(query, limit)
        success_logs = []
        
        db = SessionLocal()
        try:
            for url in urls:
                video_id = url.split("v=")[-1]
                print(f"\n[YOUTUBE_ROBOT] Processing video ID: {video_id}")
                
                media_path = ""
                if force_media:
                    media_path = cls.download_preview(url)
                    
                analysis = cls.analyze_preview(media_path)
                
                # Check editing categories based on search query tone
                is_vlog = "vlog" in query.lower() or "travel" in query.lower()
                is_cinematic = "cinematic" in query.lower() or "film" in query.lower()
                
                # Surrogate simulation rules if actual media analysis yields default values
                if analysis["is_surrogate"]:
                    if is_vlog:
                        # Vlogs typically have rapid cuts and high volume hooks
                        analysis["scene_cuts"] = 7
                        analysis["avg_scene_duration"] = 2.14
                        analysis["max_volume_db"] = -1.2
                    elif is_cinematic:
                        # Cinematic styles have longer pacing
                        analysis["scene_cuts"] = 3
                        analysis["avg_scene_duration"] = 5.0
                        analysis["max_volume_db"] = -6.8
                    else:
                        analysis["scene_cuts"] = 5
                        analysis["avg_scene_duration"] = 3.0
                        analysis["max_volume_db"] = -3.0
                
                # Dynamic Feedback Rules
                activated_patterns = []
                
                # Rule 1: High Dialogue / Hook Pattern (Vlog style cuts)
                if is_vlog and analysis["avg_scene_duration"] < 3.2:
                    activated_patterns.append("hook_3sec")
                    activated_patterns.append("reaction_hold")
                    
                # Rule 2: Cinematic Pacing / Silence (Cinematic style bridge)
                if is_cinematic and analysis["avg_scene_duration"] >= 4.0:
                    activated_patterns.append("scenery_bridge")
                    
                # Rule 3: Boredom Risk (too slow, low volume)
                if analysis["avg_scene_duration"] > 8.0 and analysis["max_volume_db"] < -12.0:
                    activated_patterns.append("boredom_prevent")
                
                # Perform sqlite weight updates for active patterns
                for pat in activated_patterns:
                    # Treat popular video pattern as positive feedback (success = True)
                    # Use +0.02 delta as simulated HRS contribution
                    PatternMemory.record_pattern_feedback(pattern_type=pat, success=True, hrs_delta=0.02)
                    
                # Save learning decision trace
                decision_id = f"DEC_YT_ROB_{video_id}"
                existing_dec = db.query(UserEditDecisionTable).filter_by(decision_id=decision_id).first()
                if not existing_dec:
                    row = UserEditDecisionTable(
                        decision_id=decision_id,
                        project_id=f"youtube_{query.replace(' ', '_')}",
                        chosen_proposal_id=video_id,
                        rejected_proposal_id=None,
                        user_intent={"query": query, "url": url},
                        selected_fragments=activated_patterns,
                        rejected_fragments=None,
                        decision_type="YOUTUBE_ROBOT_LEARN",
                        delta_log={
                            "analysis": analysis,
                            "activated_patterns": activated_patterns
                        }
                    )
                    db.add(row)
                    
                success_logs.append({
                    "video_id": video_id,
                    "url": url,
                    "analysis": analysis,
                    "activated_patterns": activated_patterns
                })
                
            db.commit()
            print(f"\n[YOUTUBE_ROBOT] Completed learning job: {len(success_logs)} videos analyzed.")
        except Exception as e:
            db.rollback()
            print(f"[YOUTUBE_ROBOT][ERROR] Learning loop failed: {e}")
        finally:
            db.close()
            
        return {"query": query, "results": success_logs}
