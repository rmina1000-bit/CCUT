import subprocess
import json
import os
import hashlib
import threading
import time
from pathlib import Path

class VideoEngine:
    def __init__(self, storage_path=None):
        if storage_path is None:
            # Fallback for direct imports, but main.py should pass it.
            curr = Path(__file__).resolve()
            while curr.name != "ccut_backend" and curr.parent != curr:
                curr = curr.parent
            project_root = curr.parent if curr.name == "ccut_backend" else Path(__file__).resolve().parent.parent.parent
            storage_path = Path(os.getenv("CCUT_STORAGE_DIR", str(project_root / "storage"))).resolve()
            
        self.storage_path = Path(storage_path)
        self.fragments_path = self.storage_path / "fragments"
        self.thumbnails_path = self.storage_path / "thumbnails"
        self.proxies_path = self.storage_path / "proxies"
        
        # 저장소 폴더 생성
        self.fragments_path.mkdir(parents=True, exist_ok=True)
        self.thumbnails_path.mkdir(parents=True, exist_ok=True)
        self.proxies_path.mkdir(parents=True, exist_ok=True)
        
        # [RACE CONDITION PROTECTION] 동시 작업 추적
        self.ongoing_tasks = set()
        self.lock = threading.Lock()

    def generate_fingerprint(self, video_path: str) -> str:
        """[STEP 1] 영상 파일의 SHA-256 해시를 생성하여 중복 분석 방지용 지문으로 사용"""
        if not os.path.exists(video_path):
            return "empty_fingerprint"
            
        sha256_hash = hashlib.sha256()
        try:
            with open(video_path, "rb") as f:
                for byte_block in iter(lambda: f.read(8192), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            print(f"[VideoEngine] Fingerprint failed: {e}")
            return f"err_{int(time.time())}"

    def create_proxy(self, video_path: str, source_id: str) -> str:
        """[STEP 1] 분석용 저용량 Proxy 영상 생성 (720p, High compress)"""
        output_path = self.proxies_path / f"{source_id}_proxy.mp4"
        if output_path.exists():
            return str(output_path)
            
        if not os.path.exists(video_path):
            return ""

        print(f"[VideoEngine] Creating proxy for {source_id}...")
        cmd = [
            'ffmpeg', '-y', '-i', video_path,
            '-vf', 'scale=1280:720',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28',
            '-c:a', 'aac', '-b:a', '128k',
            str(output_path)
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            print(f"[VideoEngine] Proxy created: {output_path}")
            return str(output_path)
        except Exception as e:
            print(f"[VideoEngine] Proxy creation failed: {e}")
            return video_path # Fallback

    def get_metadata(self, video_path):
        """ffprobe를 이용해 영상의 실제 길이와 정보를 추출"""
        if not os.path.exists(video_path):
            return {"duration": 60.0, "raw": {}, "mock": True, "fps": 30.0}
            
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', video_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True)
            data = json.loads(result.stdout.decode("utf-8", errors="replace"))
            duration = float(data['format']['duration'])
            fps = 30.0
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    r_frame_rate = stream.get('r_frame_rate', '30/1')
                    if '/' in r_frame_rate:
                        num, den = r_frame_rate.split('/')
                        fps = float(num) / float(den)
                    else:
                        fps = float(r_frame_rate)
                    break
            return {"duration": duration, "raw": data, "mock": False, "fps": fps}
        except Exception as e:
            print(f"ffprobe error: {e}")
            return {"duration": 60.0, "raw": {}, "mock": True, "fps": 30.0}

    def extract_thumbnail(self, video_path, timestamp, output_name):
        """특정 시간대에서 스크린샷을 뽑아 조각의 '얼굴' 생성"""
        output_path = self.thumbnails_path / f"{output_name}.jpg"
        if output_path.exists():
            return str(output_path)
            
        if not video_path or not os.path.exists(video_path):
            return None
            
        cmd = [
            'ffmpeg', '-y', '-ss', str(timestamp), '-i', video_path,
            '-vframes', '1', '-q:v', '2', str(output_path)
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=10)
            if output_path.exists():
                return str(output_path)
        except Exception as e:
            print(f"[VideoEngine] ffmpeg thumb error: {e}")
        return None

    def create_fragment_clip(self, video_path, start, duration, output_name):
        """실제로 영상을 잘라 개별 조각 파일(.mp4) 생성"""
        output_path = self.fragments_path / f"{output_name}.mp4"
        if not video_path or not os.path.exists(video_path):
            return None
            
        cmd = [
            'ffmpeg', '-y', '-ss', str(start), '-t', str(duration),
            '-i', video_path, '-c:v', 'libx264', '-preset', 'ultrafast',
            '-crf', '23', '-c:a', 'aac', str(output_path)
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if output_path.exists():
                return str(output_path)
        except Exception as e:
            print(f"[VideoEngine] ffmpeg clip error: {e}")
        return None

    def extract_panorama_frames(self, video_path, start, end, num_frames=12, prefix="panorama"):
        """조각의 구간을 12프레임으로 쪼개서 추출 (Race Condition 방지 + 존재 보장)"""
        frame_urls = [f"http://localhost:8000/static/thumbnails/P_{prefix}_{i}.jpg" for i in range(num_frames)]
        
        # [WAIT/POLLING STRATEGY] 동일 조각에 대한 중복 추출 방지 및 완료 대기
        max_wait = 10.0
        wait_interval = 0.1
        waited = 0
        
        while True:
            with self.lock:
                if prefix not in self.ongoing_tasks:
                    break
            
            # [WAIT] 다른 스레드에서 생성 중임. 완료될 때까지 대기
            time.sleep(wait_interval)
            waited += wait_interval
            if waited >= max_wait:
                break

        # 작업 시작 (내가 주체라면)
        is_owner = False
        with self.lock:
            # 캐시 체크
            all_cached = True
            for i in range(num_frames):
                if not (self.thumbnails_path / f"P_{prefix}_{i}.jpg").exists():
                    all_cached = False
                    break
            
            if all_cached: return frame_urls
            
            if prefix not in self.ongoing_tasks:
                self.ongoing_tasks.add(prefix)
                is_owner = True

        if is_owner:
            try:
                if not os.path.exists(video_path): return frame_urls
                duration = max(0.1, end - start)
                
                # [PBE 정확도 검증 로그] 고유 타임스탬프 계산 (DoD 요구사항)
                planned = [round(start + i * (duration / num_frames), 3) for i in range(num_frames)]
                print(f"[PBE][ACCURACY] Fragment {prefix}: {start}s ~ {end}s (Dur:{duration}s)")
                print(f"[PBE][ACCURACY] Frame timestamps: {planned}")

                cmd = [
                    'ffmpeg', '-y', '-ss', str(start), '-t', str(duration), '-i', video_path,
                    '-vf', f"fps={num_frames}/{duration},scale=320:-1",
                    '-vframes', str(num_frames), '-start_number', '0',
                    str(self.thumbnails_path / f"P_{prefix}_%d.jpg")
                ]
                try:
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
                    print(f"[PBE][OK] Panorama created for {prefix}")
                except Exception as e:
                    print(f"[PBE][ERROR] Panorama creation failed for {prefix}: {e}")
            finally:
                with self.lock:
                    if prefix in self.ongoing_tasks:
                        self.ongoing_tasks.remove(prefix)

        # [EXISTENCE GUARANTEE] 리턴 직전 최종 디스크 존재 확인
        if (self.thumbnails_path / f"P_{prefix}_0.jpg").exists():
            return frame_urls
        else:
            print(f"[PBE][ERROR] Existence failed for {prefix} after wait.")
            return []

    def batch_extract_panoramas(self, video_path, fragments, max_workers=4):
        """[N-03] 여러 조각의 파노라마를 병렬로 동시 생성하여 대기 시간 단축"""
        from concurrent.futures import ThreadPoolExecutor
        t_batch_start = time.time()
        print(f"[PBE][BATCH] Starting parallel extraction for {len(fragments)} fragments (Workers: {max_workers})")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for f in fragments:
                # 각 fragment의 video_path 속성을 우선 사용하고 없으면 인자로 들어온 video_path를 사용
                frag_video_path = f.get("video_path") or video_path
                futures.append(executor.submit(
                    self.extract_panorama_frames,
                    frag_video_path,
                    f['start_time'],
                    f['end_time'],
                    12,
                    f['fragment_id']
                ))
            # Wait for all to complete
            for future in futures:
                try:
                    future.result()
                except Exception as e:
                    print(f"[PBE][BATCH] Worker Error: {e}")
        
        t_batch_end = time.time()
        print(f"[PBE][BATCH] Parallel Extraction Completed. Total: {int((t_batch_end - t_batch_start)*1000)}ms")

video_engine = VideoEngine()
