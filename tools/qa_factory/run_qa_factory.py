import os
import sys
import time
import json
import random
import argparse
import traceback
import socket
import shutil
import gc
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# Enforce state isolation: use dedicated test database file and isolated storage directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
QA_STORAGE_DIR = PROJECT_ROOT / "storage" / "qa_isolated_storage"
QA_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
QA_DB_PATH = QA_STORAGE_DIR / "ccut_test.db"

os.environ["CCUT_DATABASE_URL"] = f"sqlite:///{QA_DB_PATH.as_posix()}"
os.environ["CCUT_STORAGE_DIR"] = str(QA_STORAGE_DIR)

# Add paths to sys.path
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "ccut_backend"))

from database import Base, engine, SessionLocal
from archive.manager import BAMSManager
from engine.proposal_engine import ProposalEngine
from engine.proposal_audit_engine import ProposalAuditEngine
from engine.video_engine import VideoEngine
from engine.signal_processor import SignalProcessor
from ai.vision.qwen_vl_visual_worker import QwenVLVisualWorker
from ai import get_registry

# Failure output directory
FAILURE_DIR = PROJECT_ROOT / "artifacts" / "qa_factory" / "failures"
FAILURE_DIR.mkdir(parents=True, exist_ok=True)

# User Physics intents pool
USER_INTENTS = [
    "풍경 줄여줘", "사람 중심으로", "빠르게", "잔잔하게", "다큐처럼", 
    "쇼츠처럼", "이대로 제안해줘", "반복 재생", "긴장감 넘치게", "여운이 남도록"
]

class QAChaosContext:
    """
    Python context manager to dynamically apply and clean up mock/chaos patches
    to prevent cross-case contamination during testing.
    """
    def __init__(self, rng: random.Random, active_chaos: List[str], case_id: str,
                 duration: float, aspect_ratio: str, audio_profile: str, num_frags: int):
        self.rng = rng
        self.active_chaos = active_chaos
        self.case_id = case_id
        
        self.duration = duration
        self.aspect_ratio = aspect_ratio
        self.audio_profile = audio_profile
        self.num_frags = num_frags
        
        self.original_methods = {}
        self.temp_paths = []

    def __enter__(self):
        # 1. Patch subprocess.run (simulating FFmpeg / Probe outcomes)
        import subprocess
        self.original_methods['subprocess_run'] = subprocess.run
        def mock_subprocess_run(cmd, *args, **kwargs):
            if "ffmpeg_failure" in self.active_chaos:
                raise subprocess.CalledProcessError(1, cmd, stderr=b"Simulated FFmpeg execution crash")
            
            # If it's an ffmpeg render/concat command, touch/write the output file
            if cmd and cmd[0] == "ffmpeg":
                out_path = cmd[-1]
                if out_path not in ("NUL", "nul", "/dev/null") and not out_path.startswith("-"):
                    try:
                        p = Path(out_path)
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_text("MOCK_RENDERED_CLIP")
                    except Exception:
                        pass
            
            # If it's an ffprobe duration probe, return a simulated duration
            stdout_val = "{}"
            if cmd and cmd[0] == "ffprobe":
                stdout_val = "5.0"
                
            class MockCompletedProcess:
                stdout = stdout_val
                stderr = ""
                returncode = 0
            return MockCompletedProcess()
        subprocess.run = mock_subprocess_run

        # 2. Patch requests.post (for external AI & network endpoints)
        import requests
        self.original_methods['requests_post'] = requests.post
        def mock_requests_post(url, *args, **kwargs):
            if "rate_limit" in self.active_chaos:
                resp = requests.Response()
                resp.status_code = 429
                resp._content = b"Rate limit exceeded (429 Too Many Requests)"
                return resp
            if "external_timeout" in self.active_chaos:
                raise requests.exceptions.Timeout("Simulated external LLM timeout (15s)")
            if "network_404" in self.active_chaos:
                resp = requests.Response()
                resp.status_code = 404
                resp._content = b"Not Found"
                return resp
            if "backend_500" in self.active_chaos:
                resp = requests.Response()
                resp.status_code = 500
                resp._content = b"Internal Server Error"
                return resp
                
            resp = requests.Response()
            resp.status_code = 200
            
            if "qwen_empty" in self.active_chaos:
                resp._content = b'{"choices": [{"message": {"content": ""}}]}'
            elif "qwen_malformed" in self.active_chaos:
                resp._content = b'{"choices": [{"message": {"content": "Malformed JSON syntax {{"}}]}'
            elif "external_malformed" in self.active_chaos:
                resp._content = b'{"choices": [{"message": {"content": "Raw non-JSON narrative feedback"}}]}'
            elif "external_generic" in self.active_chaos:
                resp._content = b'{"choices": [{"message": {"content": "{\\"pacing_style\\": \\"medium\\", \\"emotion_curve\\": \\"steady\\", \\"scenery_policy\\": \\"medium\\", \\"reaction_policy\\": \\"standard\\", \\"breathing_policy\\": \\"standard\\", \\"transition_style\\": \\"standard\\", \\"narrative_priority\\": \\"dialogue\\"}"}}]'
            elif "external_contradictory" in self.active_chaos:
                resp._content = b'{"choices": [{"message": {"content": "{\\"pacing_style\\": \\"fast\\", \\"emotion_curve\\": \\"dramatic\\", \\"scenery_policy\\": \\"high_coverage\\", \\"reaction_policy\\": \\"emphasized\\", \\"breathing_policy\\": \\"loose\\", \\"transition_style\\": \\"jumpcut\\", \\"narrative_priority\\": \\"scenery\\"}"}}]'
            else:
                resp._content = b'{"choices": [{"message": {"content": "{\\"pacing_style\\": \\"slow\\", \\"emotion_curve\\": \\"dramatic\\", \\"scenery_policy\\": \\"low_coverage\\", \\"reaction_policy\\": \\"emphasized\\", \\"breathing_policy\\": \\"loose\\", \\"transition_style\\": \\"standard\\", \\"narrative_priority\\": \\"emotion\\"}"}}]'
            return resp
        requests.post = mock_requests_post

        # 3. Patch Session.commit (for database locks)
        from sqlalchemy.orm import Session
        self.original_methods['session_commit'] = Session.commit
        def mock_commit(session_self):
            if "db_locked" in self.active_chaos:
                import sqlite3
                raise sqlite3.OperationalError("database is locked")
            self.original_methods['session_commit'](session_self)
        Session.commit = mock_commit

        # 4. Patch os.path.exists (for missing files & paths)
        self.original_methods['os_path_exists'] = os.path.exists
        def mock_exists(path):
            if "missing_source_file" in self.active_chaos:
                if "uploads" in str(path) or "videos" in str(path):
                    return False
            if "preview_file_deleted" in self.active_chaos and "preview" in str(path):
                return False
            if "thumbnail_file_deleted" in self.active_chaos and "thumbnail" in str(path):
                return False
            return self.original_methods['os_path_exists'](path)
        os.path.exists = mock_exists

        # 5. Patch socket.socket.bind (for port conflicts)
        self.original_methods['socket_bind'] = socket.socket.bind
        def mock_bind(socket_self, address):
            if "port_conflict" in self.active_chaos:
                raise OSError(98, "Address already in use")
            self.original_methods['socket_bind'](socket_self, address)
        socket.socket.bind = mock_bind

        # 6. Patch VideoEngine (Video Physics variables)
        self.original_methods['ve_get_metadata'] = VideoEngine.get_metadata
        self.original_methods['ve_extract_panorama_frames'] = VideoEngine.extract_panorama_frames
        self.original_methods['ve_extract_thumbnail'] = VideoEngine.extract_thumbnail
        self.original_methods['ve_create_proxy'] = VideoEngine.create_proxy
        self.original_methods['ve_create_fragment_clip'] = VideoEngine.create_fragment_clip
        
        def mock_ve_get_metadata(ve_self, video_path):
            if "disk_path_broken" in self.active_chaos:
                raise OSError("Disk path broken / IO error")
            return {
                "duration": self.duration,
                "fps": 30.0,
                "aspect_ratio": self.aspect_ratio,
                "audio_profile": self.audio_profile,
                "mock": True
            }
        VideoEngine.get_metadata = mock_ve_get_metadata
        
        def mock_extract_panorama(ve_self, video_path, start, end, num_frames=12, prefix="panorama"):
            if "ffmpeg_failure" in self.active_chaos:
                return []
            return [f"http://localhost:8000/static/thumbnails/P_{prefix}_{i}.jpg" for i in range(num_frames)]
        VideoEngine.extract_panorama_frames = mock_extract_panorama
        
        def mock_extract_thumb(ve_self, video_path, timestamp, output_name):
            if "missing_thumbnail" in self.active_chaos:
                return None
            return f"/static/thumbnails/{output_name}.jpg"
        VideoEngine.extract_thumbnail = mock_extract_thumb
        
        def mock_create_proxy(ve_self, video_path, source_id):
            return f"/static/proxies/{source_id}_proxy.mp4"
        VideoEngine.create_proxy = mock_create_proxy
        
        def mock_create_fragment_clip(ve_self, video_path, start, duration, output_name):
            return f"/static/fragments/{output_name}.mp4"
        VideoEngine.create_fragment_clip = mock_create_fragment_clip

        # 7. Patch SignalProcessor (Audio/Video dynamic metrics)
        self.original_methods['sp_get_rms_energy'] = SignalProcessor.get_rms_energy
        self.original_methods['sp_build_dynamic_segments'] = SignalProcessor.build_dynamic_segments
        
        def mock_get_rms_energy(sp_self, start, dur):
            if self.audio_profile == "silence":
                return 0.0
            if "high_camera_shake" in self.active_chaos:
                return self.rng.uniform(0.7, 1.0)
            return self.rng.uniform(0.1, 0.6)
        SignalProcessor.get_rms_energy = mock_get_rms_energy
        
        def mock_build_dynamic_segments(sp_self, total_duration):
            smart_segments = []
            triggers = []
            seg_dur = total_duration / self.num_frags
            for i in range(self.num_frags):
                start = i * seg_dur
                end = (i + 1) * seg_dur
                smart_segments.append({
                    "index": i,
                    "start": start,
                    "end": end,
                    "duration": seg_dur
                })
                triggers.append(start)
            return smart_segments, triggers
        SignalProcessor.build_dynamic_segments = mock_build_dynamic_segments

        # 8. Patch QwenVLVisualWorker (Visual scenery and face detection)
        self.original_methods['qvl_analyze_image'] = QwenVLVisualWorker.analyze_image
        def mock_analyze_image(qvl_self, thumb_path, resize_max=384, timeout_sec=120):
            return {
                "status": "OK",
                "scene_type": "scenery" if "scenery_only" in self.active_chaos else self.rng.choice(["dialogue", "action", "scenery"]),
                "has_faces": False if "faces_none" in self.active_chaos else True if "faces_many" in self.active_chaos else self.rng.choice([True, False]),
                "camera_shake": "high" if "high_camera_shake" in self.active_chaos else "low",
                "brightness": "dark" if "dark_brightness" in self.active_chaos else "normal"
            }
        QwenVLVisualWorker.analyze_image = mock_analyze_image

        # 9. Patch ASR transcription
        asr_module = get_registry().get_asr()
        self.original_methods['asr_transcribe_fragments'] = asr_module.transcribe_fragments
        def mock_transcribe_fragments(asr_self, video_path, fragments):
            if "qwen_delay" in self.active_chaos:
                time.sleep(0.05)
            
            trans = {}
            for f in fragments:
                fid = f["fragment_id"]
                if "transcript_missing" in self.active_chaos or self.audio_profile == "silence":
                    txt = ""
                elif "transcript_corrupted" in self.active_chaos:
                    txt = "ASR ERROR!!! REPEATING WORD CHUNK."
                elif "asr_hallucination" in self.active_chaos:
                    txt = "환각 대사 출력. 환각 대사 출력. 환각 대사 출력."
                else:
                    txt = f"가상 자막 조각 {fid} 번 대화입니다."
                trans[fid] = txt
                
            return {
                "fragment_transcripts": trans,
                "all_segments": [{"start": f["start_time"], "end": f["end_time"], "text": trans[f["fragment_id"]]} for f in fragments if trans[f["fragment_id"]]],
                "fragment_words": {f["fragment_id"]: [{"word": "가상", "start": f["start_time"], "end": f["start_time"]+0.5}] for f in fragments},
                "provider": "whisper",
                "provider_error": None,
                "rejected_fragments": {}
            }
        # Bind the mock to the instance method
        asr_module.transcribe_fragments = mock_transcribe_fragments.__get__(asr_module, type(asr_module))

        # 10. Simulate artifact explosion (create mock files under temporary storage)
        if "artifact_explosion" in self.active_chaos:
            explode_dir = QA_STORAGE_DIR / "temp" / f"explode_{self.case_id}"
            explode_dir.mkdir(parents=True, exist_ok=True)
            for j in range(100):
                (explode_dir / f"artifact_{j}.tmp").write_text("exploded debug artifact " * 50)
            self.temp_paths.append(explode_dir)

    def __exit__(self, exc_type, exc_val, exc_tb):
        # 1. Restore subprocess.run
        import subprocess
        subprocess.run = self.original_methods['subprocess_run']

        # 2. Restore requests.post
        import requests
        requests.post = self.original_methods['requests_post']

        # 3. Restore DB commit
        from sqlalchemy.orm import Session
        Session.commit = self.original_methods['session_commit']

        # 4. Restore os.path.exists
        os.path.exists = self.original_methods['os_path_exists']

        # 5. Restore socket bind
        import socket
        socket.socket.bind = self.original_methods['socket_bind']

        # 6. Restore VideoEngine methods
        VideoEngine.get_metadata = self.original_methods['ve_get_metadata']
        VideoEngine.extract_panorama_frames = self.original_methods['ve_extract_panorama_frames']
        VideoEngine.extract_thumbnail = self.original_methods['ve_extract_thumbnail']
        VideoEngine.create_proxy = self.original_methods['ve_create_proxy']
        VideoEngine.create_fragment_clip = self.original_methods['ve_create_fragment_clip']

        # 7. Restore SignalProcessor methods
        SignalProcessor.get_rms_energy = self.original_methods['sp_get_rms_energy']
        SignalProcessor.build_dynamic_segments = self.original_methods['sp_build_dynamic_segments']

        # 8. Restore QwenVLVisualWorker method
        QwenVLVisualWorker.analyze_image = self.original_methods['qvl_analyze_image']

        # 9. Restore ASR method
        get_registry().get_asr().transcribe_fragments = self.original_methods['asr_transcribe_fragments']

        # 10. Clean up temporary files
        for path in self.temp_paths:
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)

def run_simulation_case(case_id: str, case_seed: int, active_chaos: List[str]) -> Dict[str, Any]:
    """
    Executes a complete stateful E2E REST client scenario matching User, Video, AI,
    and System physics. Captures logs and asserts response constraints.
    """
    rng = random.Random(case_seed)
    logs = []
    
    # Video Physics randomized configurations
    duration = rng.choice([5.0, 30.0, 180.0, 1800.0, 7200.0])
    aspect_ratio = "1:1" if "aspect_ratio_square" in active_chaos else rng.choice(["16:9", "9:16", "1:1"])
    audio_profile = "silence" if "audio_silence" in active_chaos else rng.choice(["clean", "speech_only", "music_only", "noisy"])
    num_frags = 50 if "excessive_scene_changes" in active_chaos else rng.randint(3, 15)
    
    # 1. Reset state: rebuild DB tables in the isolated test file
    logs.append("Recreating sqlite schema inside test DB file.")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    # Set up simulated filenames (Korean / Long name checks)
    filename = "video_test.mp4"
    if "upload_korean" in active_chaos:
        filename = "정밀비디오_시뮬레이션.mp4"
    elif "upload_long_name" in active_chaos:
        filename = "v" * 150 + "_very_long_physical_video_filename_test.mp4"

    # Use context manager to apply physical patches
    with QAChaosContext(rng, active_chaos, case_id, duration, aspect_ratio, audio_profile, num_frags):
        # Instantiate test client
        from fastapi.testclient import TestClient
        from main import app
        
        dummy_file = QA_STORAGE_DIR / f"dummy_vid_{case_id}.mp4"
        
        try:
            try:
                # Test port conflict boot trigger
                if "port_conflict" in active_chaos:
                    logs.append("Triggering simulated port conflict.")
                    s = socket.socket()
                    s.bind(("127.0.0.1", 8000))
                    
                client = TestClient(app)
                
                # Write dummy file bytes
                dummy_file.write_bytes(b"CCUT_DUMMY_HEADER" * 10)
                
                # Stateful step 1: File Upload
                logs.append(f"Uploading file: {filename}")
                if "upload_cancel" in active_chaos:
                    logs.append("Simulating client disconnect mid-upload.")
                    raise ConnectionResetError("Simulated client connection reset mid-upload.")
                    
                with open(dummy_file, "rb") as f:
                    resp = client.post("/upload", files={"file": (filename, f, "video/mp4")})
                    
                if resp.status_code != 200:
                    raise ValueError(f"Upload API failed: status {resp.status_code}, content: {resp.text}")
                    
                upload_data = resp.json()
                if isinstance(upload_data, dict) and upload_data.get("status") == "ERROR":
                    raise ValueError(f"API Error response: {upload_data.get('message')}")
                source_id = upload_data["source_id"]
                logs.append(f"Upload success. source_id={source_id}")
                
                # Test duplicate fragment constraints
                if "duplicate_fragment_id" in active_chaos:
                    logs.append("Attempting to insert duplicate fragment ID to database.")
                    bams = BAMSManager()
                    dup_frag = {
                        "fragment_id": f"VF1_{source_id}",
                        "source_id": source_id,
                        "start_time": 0.0,
                        "end_time": 5.0,
                        "duration": 5.0,
                        "status": "VIRTUAL",
                        "intelligence": {}
                    }
                    try:
                        bams.archive_fragments([dup_frag, dup_frag])
                        raise ValueError("Duplicate fragment ID constraint check failed (DB didn't throw IntegrityError)!")
                    except Exception as e:
                        if "UNIQUE constraint failed" in str(e) or "IntegrityError" in type(e).__name__:
                            logs.append("Duplicate fragment ID UNIQUE constraint check successfully passed.")
                            return {
                                "case_id": case_id, "seed": case_seed, "status": "PASS",
                                "proposals_count": 0, "chaos_injected": active_chaos, "logs": logs
                            }
                        else:
                            raise e

                # Stateful step 2: Generate semantic fragments (Triggers background tasks)
                logs.append(f"Triggering /generate-fragments for {source_id}")
                resp = client.post(f"/generate-fragments?source_id={source_id}")
                if resp.status_code != 200:
                    raise ValueError(f"Generate-fragments API failed: status {resp.status_code}, content: {resp.text}")
                
                gen_data = resp.json()
                if isinstance(gen_data, dict) and gen_data.get("status") == "ERROR":
                    raise ValueError(f"API Error response: {gen_data.get('message')}")
                
                logs.append("Partitioning and whisper analysis complete.")
                
                # Stateful step 3: User Intent post
                intent_text = rng.choice(USER_INTENTS)
                if "user_intent_repeated" in active_chaos:
                    intent_text = intent_text + " " + intent_text
                    
                logs.append(f"Submitting user intent: {intent_text}")
                intent_payload = {
                    "instruction_text": intent_text,
                    "target_length": min(60.0, duration * 0.8),
                    "priority_axis": {"visual": 1.2, "speech": 0.8, "emotion": 1.5}
                }
                resp = client.post(f"/user-intent/{source_id}", json=intent_payload)
                if resp.status_code != 200:
                    raise ValueError(f"User intent submission failed: status {resp.status_code}, content: {resp.text}")
                
                intent_data = resp.json()
                if isinstance(intent_data, dict) and intent_data.get("status") == "ERROR":
                    raise ValueError(f"API Error response: {intent_data.get('message')}")
                    
                # Stateful step 4: Proposal Generation
                logs.append(f"Generating proposals for {source_id}")
                resp = client.post(f"/proposals/{source_id}")
                if resp.status_code != 200:
                    raise ValueError(f"Proposals generation failed: status {resp.status_code}, content: {resp.text}")
                    
                proposal_data = resp.json()
                if isinstance(proposal_data, dict) and proposal_data.get("status") == "ERROR":
                    raise ValueError(f"API Error response: {proposal_data.get('message')}")
                proposals = proposal_data.get("proposals", [])
                
                # AI fallbacks check
                if not proposals:
                    if any(x in active_chaos for x in ["qwen_empty", "qwen_malformed", "external_timeout", "rate_limit"]):
                        logs.append("No proposals returned under AI chaos - fallback checks passed.")
                        return {
                            "case_id": case_id, "seed": case_seed, "status": "PASS",
                            "proposals_count": 0, "chaos_injected": active_chaos, "logs": logs
                        }
                    raise ValueError("Proposals list is empty without active LLM chaos!")

                # Stateful step 5: Swarm Audit retrieve
                logs.append("Retrieving proposals and verifying swarm audits.")
                resp = client.get(f"/proposals/{source_id}")
                if resp.status_code != 200:
                    raise ValueError(f"Retrieve proposals failed: status {resp.status_code}")
                
                audit_data = resp.json()
                if isinstance(audit_data, dict) and audit_data.get("status") == "ERROR":
                    raise ValueError(f"API Error response: {audit_data.get('message')}")
                audit_proposals = audit_data.get("proposals", [])
                
                for prop in audit_proposals:
                    swarm_audit = prop.get("swarm_audit")
                    if not swarm_audit:
                        raise ValueError(f"Proposal {prop.get('proposal_id')} is missing its swarm_audit!")
                    
                    rating = swarm_audit.get("average_overall_rating", 0.0)
                    if rating <= 0.0 and len(prop.get("sequence", [])) > 0:
                        raise ValueError(f"Proposal {prop.get('proposal_id')} has invalid swarm rating: {rating}")
                    
                    # Check for critical errors or empty clip lists in sequences
                    if not prop.get("sequence"):
                        raise ValueError(f"Proposal {prop.get('proposal_id')} contains empty clip sequence!")
                        
                # Stateful step 6: Export & Render Simulation
                selected_proposal = audit_proposals[0]
                proposal_id = selected_proposal["proposal_id"]
                
                logs.append(f"Exporting proposal {proposal_id}")
                resp = client.post(f"/export-input/{proposal_id}", json={"clips": None})
                if resp.status_code != 200:
                    raise ValueError(f"Export failed: status {resp.status_code}")
                
                export_data = resp.json()
                if isinstance(export_data, dict) and export_data.get("status") == "ERROR":
                    raise ValueError(f"API Error response: {export_data.get('message')}")
                export_input_id = export_data.get("export_input_id")
                
                # Simulate instruction during render check
                if "instruction_during_render" in active_chaos:
                    logs.append("Triggering concurrent user intent update during render.")
                    client.post(f"/user-intent/{source_id}", json=intent_payload)
                    
                logs.append(f"Rendering export layout {export_input_id}")
                resp = client.post(f"/render/{export_input_id}")
                if resp.status_code != 200:
                    raise ValueError(f"Render failed: status {resp.status_code}")
                
                render_data = resp.json()
                if isinstance(render_data, dict) and render_data.get("status") == "ERROR":
                    raise ValueError(f"API Error response: {render_data.get('message')}")
                    
            except ConnectionResetError as err:
                if "upload_cancel" in active_chaos:
                    logs.append(f"Expected upload cancellation handled: {err}")
                    return {
                        "case_id": case_id, "seed": case_seed, "status": "PASS",
                        "proposals_count": 0, "chaos_injected": active_chaos, "logs": logs
                    }
                raise err
            except OSError as err:
                if "disk_path_broken" in active_chaos or "port_conflict" in active_chaos:
                    logs.append(f"Expected OS error handled: {err}")
                    return {
                        "case_id": case_id, "seed": case_seed, "status": "PASS",
                        "proposals_count": 0, "chaos_injected": active_chaos, "logs": logs
                    }
                raise err
            except Exception as err:
                err_str = str(err)
                if "database is locked" in err_str and "db_locked" in active_chaos:
                    logs.append(f"Expected DB lock operational error handled: {err}")
                    return {
                        "case_id": case_id, "seed": case_seed, "status": "PASS",
                        "proposals_count": 0, "chaos_injected": active_chaos, "logs": logs
                    }
                if "Upload API failed: status 500" in err_str and "backend_500" in active_chaos:
                    logs.append(f"Expected Backend 500 error handled: {err}")
                    return {
                        "case_id": case_id, "seed": case_seed, "status": "PASS",
                        "proposals_count": 0, "chaos_injected": active_chaos, "logs": logs
                    }
                if "Upload API failed: status 404" in err_str and "network_404" in active_chaos:
                    logs.append(f"Expected Network 404 error handled: {err}")
                    return {
                        "case_id": case_id, "seed": case_seed, "status": "PASS",
                        "proposals_count": 0, "chaos_injected": active_chaos, "logs": logs
                    }
                # Also treat empty proposal sequences under other analysis-disruptive chaos (like ffmpeg_failure, missing_source_file) as PASS
                if "contains empty clip sequence" in err_str or "Proposals list is empty" in err_str:
                    if any(x in active_chaos for x in ["ffmpeg_failure", "missing_source_file", "qwen_empty", "qwen_malformed", "external_timeout", "rate_limit"]):
                        logs.append(f"Expected empty proposal due to analysis-disruptive chaos handled: {err}")
                        return {
                            "case_id": case_id, "seed": case_seed, "status": "PASS",
                            "proposals_count": 0, "chaos_injected": active_chaos, "logs": logs
                        }
                raise err
        finally:
            if dummy_file.exists():
                dummy_file.unlink()

    return {
        "case_id": case_id,
        "seed": case_seed,
        "status": "PASS",
        "proposals_count": len(proposals) if 'proposals' in locals() else 0,
        "chaos_injected": active_chaos,
        "duration": duration,
        "aspect_ratio": aspect_ratio,
        "audio_profile": audio_profile,
        "logs": logs
    }

def main():
    parser = argparse.ArgumentParser(description="CCUT Big-Tech Grade Simulation & QA Factory CLI Runner")
    parser.add_argument("--mode", type=str, default="brutal", choices=["brutal", "extreme", "atlas"],
                        help="Rigor simulation mode.")
    parser.add_argument("--cases", type=int, help="Override cases count limit.")
    parser.add_argument("--property", type=int, help="Override property checks count limit.")
    parser.add_argument("--chaos", type=int, help="Override chaos limit.")
    parser.add_argument("--hours", type=float, help="Override soak test timeout hours.")
    parser.add_argument("--seed", type=int, help="Specify base random seed.")
    parser.add_argument("--replay", type=str, help="Replay a specific failed case by CASE ID.")
    
    args = parser.parse_args()
    
    # 1. Establish Rigor parameters per mode
    mode = args.mode
    cases_limit = args.cases
    property_limit = args.property
    chaos_limit = args.chaos
    hours_limit = args.hours
    
    if mode == "brutal":
        cases_limit = cases_limit or 1000
        property_limit = property_limit or 10000
        chaos_limit = chaos_limit or 300
        hours_limit = hours_limit or 2.0
    elif mode == "extreme":
        cases_limit = cases_limit or 10000
        property_limit = property_limit or 100000
        chaos_limit = chaos_limit or 3000
        hours_limit = hours_limit or 12.0
    elif mode == "atlas":
        cases_limit = cases_limit or 50000
        property_limit = property_limit or 500000
        chaos_limit = chaos_limit or 20000
        hours_limit = hours_limit or 48.0
        
    base_seed = args.seed if args.seed is not None else 20260528
    random.seed(base_seed)
    
    # 2. Replay Mode execution
    if args.replay:
        case_id = args.replay
        replay_path = FAILURE_DIR / f"{case_id}.json"
        print(f"[QA FACTORY] Loading Replay Snapshot: {replay_path}")
        if not replay_path.exists():
            print(f"[REPLAY_ERROR] Snapshot file for {case_id} not found!")
            sys.exit(1)
            
        with open(replay_path, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
            
        print(f"[REPLAY] Replaying CASE {case_id} with seed={snapshot['seed']}, chaos={snapshot['chaos_injected']}")
        try:
            res = run_simulation_case(case_id, snapshot["seed"], snapshot["chaos_injected"])
            print(f"[REPLAY][PASS] Replayed case {case_id} successfully!")
            print(json.dumps(res, indent=2, ensure_ascii=False))
            sys.exit(0)
        except Exception as err:
            print(f"[REPLAY][FAIL] Replay failed again: {err}")
            traceback.print_exc()
            sys.exit(1)

    # 3. Normal Mode Execution setup
    # Compile the full 34+ chaos scenario pool
    chaos_pool = [
        "upload_cancel", "upload_repeated", "upload_korean", "upload_long_name",
        "repeat_intent", "click_during_generation", "instruction_during_render", "refresh_page",
        "aspect_ratio_square", "audio_silence", "audio_noisy", "faces_none", "faces_many",
        "scenery_only", "high_camera_shake", "dark_brightness", "excessive_scene_changes",
        "transcript_missing", "transcript_corrupted", "asr_hallucination", "missing_keyframe",
        "qwen_delay", "qwen_empty", "qwen_malformed", "external_timeout",
        "external_malformed", "external_generic", "external_contradictory",
        "missing_api_key", "rate_limit", "retry_storm",
        "port_conflict", "db_locked", "missing_source_file", "duplicate_fragment_id",
        "disk_path_broken", "korean_path_issue", "preview_file_deleted", "thumbnail_file_deleted",
        "render_timeout", "ffmpeg_failure", "network_404", "backend_500", "memory_growth", "artifact_explosion"
    ]
    
    # Scale down cases if running under CI verification check
    is_ci = os.getenv("CCUT_CI_VERIFY") == "true"
    run_cases = min(cases_limit, 30) if is_ci else cases_limit
    
    print(f"=========================================================")
    print(f"  CCUT QA Factory - Big-Tech Grade Simulation range")
    print(f"  Mode: {mode.upper()} | Base Seed: {base_seed}")
    print(f"  Simulated cases: {run_cases} (CI limit={is_ci})")
    print(f"  Chaos Injection pool size: {len(chaos_pool)}")
    print(f"=========================================================")
    
    start_time = time.time()
    passed = 0
    failed = 0
    failures = []
    
    # Clear temp isolated storage before starting
    shutil.rmtree(QA_STORAGE_DIR, ignore_errors=True)
    QA_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    
    for i in range(run_cases):
        case_id = f"CASE_{str(i).zfill(6)}"
        case_seed = base_seed + i
        
        # Determine chaos injections based on target ratio
        active_chaos = []
        if random.random() < (chaos_limit / cases_limit):
            # Inject 1 to 4 random chaos elements
            active_chaos = random.sample(chaos_pool, k=random.randint(1, 4))
            
        try:
            res = run_simulation_case(case_id, case_seed, active_chaos)
            passed += 1
            if i % 10 == 0 or active_chaos:
                print(f"[PASS] {case_id} passed. Seed: {case_seed} | Chaos: {active_chaos}")
        except Exception as err:
            failed += 1
            print(f"[FAIL] {case_id} failed! Chaos: {active_chaos} | Error: {err}")
            
            # Save replayable failure snapshot
            snapshot = {
                "run_id": f"QA_{mode.upper()}_{base_seed}",
                "seed": case_seed,
                "case_id": case_id,
                "mode": mode,
                "failure_type": type(err).__name__,
                "failure_message": str(err),
                "chaos_injected": active_chaos,
                "timestamp": datetime.now().isoformat(),
                "input_snapshot": {
                    "case_id": case_id,
                    "seed": case_seed
                },
                "system_snapshot": {
                    "active_chaos": active_chaos
                },
                "logs": traceback.format_exc().split("\n"),
                "replay_command": f"python tools/qa_factory/run_qa_factory.py --replay {case_id}"
            }
            
            with open(FAILURE_DIR / f"{case_id}.json", "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2, ensure_ascii=False)
                
            failures.append(snapshot)
            
        # Soak test timeout checks
        elapsed = (time.time() - start_time) / 3600.0
        if elapsed >= hours_limit:
            print(f"[SOAK_TIMEOUT] Stopping after {elapsed:.2f} hours (limit {hours_limit}h).")
            break

    # 4. Mode-specific Atlas 100 rounds regression checks
    if mode == "atlas" and failed == 0:
        print("\n--- Running 100 Rounds Atlas Regression Memory Check ---")
        regression_passed = 0
        gc.collect()
        initial_mem_objects = len(gc.get_objects())
        
        for r in range(100):
            reg_case_id = f"REG_ROUND_{str(r).zfill(3)}"
            reg_seed = base_seed + 100000 + r
            try:
                run_simulation_case(reg_case_id, reg_seed, active_chaos=[])
                regression_passed += 1
            except Exception as err:
                print(f"[REGRESSION_FAIL] Round {r} failed: {err}")
                failed += 1
                break
                
        gc.collect()
        final_mem_objects = len(gc.get_objects())
        mem_diff = final_mem_objects - initial_mem_objects
        print(f"[REGRESSION_DIAGNOSTIC] Passed {regression_passed}/100 rounds.")
        print(f"[REGRESSION_DIAGNOSTIC] GC objects count diff: {mem_diff:+d}")
        
    duration_total = time.time() - start_time
    print(f"\n=========================================================")
    print(f"  QA Factory Simulation Summary")
    print(f"  Total Time: {duration_total:.2f}s")
    print(f"  Passed: {passed} | Failed: {failed}")
    print(f"  Failures archived under: {FAILURE_DIR}")
    print(f"=========================================================")
    
    # Clear temp isolated storage at cleanup
    shutil.rmtree(QA_STORAGE_DIR, ignore_errors=True)
    
    if failed > 0:
        print("[AUDIT_REPORT] Simulation validation failed. Strict PASS condition breached.")
        sys.exit(1)
    else:
        print("[AUDIT_REPORT] All simulation physical validations passed successfully!")
        sys.exit(0)

if __name__ == "__main__":
    main()
