"""
CCUT 1.0.6 ??濡쒖뺄 AI ?붿깉 援ъ텞 ?ㅽ겕由쏀듃 (setup_local_ai.py)
"Pure Local Autonomous Studio"

???ㅽ겕由쏀듃 ?섎굹濡?CCUT??6? AI 吏?μ쓣
援?옣?섏쓽 ?섎뱶?붿뒪?ъ뿉 ?곴뎄 ?댁떇?⑸땲??

?ㅽ뻾:
    python setup_local_ai.py             # ?꾩껜 ?ㅼ튂
    python setup_local_ai.py --ear       # Whisper留?
    python setup_local_ai.py --eye       # Qwen2-VL留?
    python setup_local_ai.py --voice     # XTTS v2留?
    python setup_local_ai.py --brain     # Ollama ?곹깭 ?뺤씤留?
    python setup_local_ai.py --check     # ?ㅼ튂 ?꾪솴 由ы룷??

?⑸웾 ?덉긽:
    Whisper base       : ~150 MB
    Whisper large-v3   : ~3.1 GB
    Qwen2-VL 2B        : ~4.5 GB
    XTTS v2            : ~1.9 GB
    Wav2Lip (?섎룞)     : ~500 MB (GitHub?먯꽌 吏곸젒 ?ㅼ슫)
    ??????????????????????????????
    ?⑷퀎 (large ?쒖쇅)  : ~7 GB

?섎뱶 怨듦컙 沅뚯옣: 15 GB ?댁긽
"""

import os
import sys
import time
import argparse
from pathlib import Path

# ?? 寃쎈줈 ?ㅼ젙 ????????????????????????????????????????????????????
BASE    = Path("D:/CCUT 1.0.3/ccut_backend")
MODELS  = BASE / "ai_models"
STORAGE = BASE / "storage"

VOICE_SAMPLES = STORAGE / "voice_samples"
QDRANT_DB     = STORAGE / "qdrant_db"
EXPORTS       = STORAGE / "exports" / "global"

for d in [MODELS, VOICE_SAMPLES, QDRANT_DB, EXPORTS]:
    d.mkdir(parents=True, exist_ok=True)

# ?? ?좏떥 ?????????????????????????????????????????????????????????
def banner(emoji: str, title: str):
    print(f"\n{'?'*55}")
    print(f"  {emoji}  {title}")
    print(f"{'?'*55}")

def ok(msg: str):  print(f"  ?? {msg}")
def warn(msg: str): print(f"  ?좑툘   {msg}")
def info(msg: str): print(f"  ?뱄툘   {msg}")
def err(msg: str):  print(f"  ?? {msg}")

def check_import(pkg: str) -> bool:
    import importlib
    try:
        importlib.import_module(pkg)
        return True
    except ImportError:
        return False

# ?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧
#  ?몔  EAR  ?? Whisper (OpenAI)
# ?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧
def setup_ear(size: str = "base"):
    banner("?몔", f"[Ear] Whisper '{size}' ?ㅼ슫濡쒕뱶")

    if not check_import("whisper"):
        err("openai-whisper 誘몄꽕移???pip install openai-whisper")
        return False

    import whisper
    whisper_dir = MODELS / "whisper"
    whisper_dir.mkdir(exist_ok=True)

    info(f"?ㅼ슫濡쒕뱶 寃쎈줈: {whisper_dir}")
    try:
        model = whisper.load_model(size, download_root=str(whisper_dir))
        ok(f"Whisper '{size}' 濡쒕뱶 ?꾨즺 (?뚮씪誘명꽣: {sum(p.numel() for p in model.parameters()) / 1e6:.0f}M)")
        return True
    except Exception as e:
        err(f"Whisper ?ㅼ슫濡쒕뱶 ?ㅽ뙣: {e}")
        return False


# ?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧
#  ?몓  EYE  ?? Qwen2-VL + CLIP
# ?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧
def setup_eye(model_size: str = "2B"):
    banner("?몓", f"[Eye] Qwen2-VL {model_size} ?ㅼ슫濡쒕뱶")

    model_id = f"Qwen/Qwen2-VL-{model_size}-Instruct"
    cache_dir = str(MODELS / "qwen2-vl")
    Path(cache_dir).mkdir(exist_ok=True)

    if not check_import("transformers"):
        err("transformers 誘몄꽕移???pip install transformers accelerate")
        return False

    try:
        from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

        info(f"Processor ?ㅼ슫濡쒕뱶 以?.. ({model_id})")
        AutoProcessor.from_pretrained(model_id, cache_dir=cache_dir)
        ok("Processor ?꾨즺")

        info(f"紐⑤뜽 媛以묒튂 ?ㅼ슫濡쒕뱶 以?.. (??{4.5 if '2B' in model_size else 15}GB ?덉긽)")
        Qwen2VLForConditionalGeneration.from_pretrained(
            model_id,
            cache_dir=cache_dir,
            torch_dtype="auto",
            device_map="auto"
        )
        ok(f"Qwen2-VL {model_size} ?ㅼ슫濡쒕뱶 ?꾨즺 ??{cache_dir}")
        return True
    except Exception as e:
        err(f"Qwen2-VL ?ㅼ슫濡쒕뱶 ?ㅽ뙣: {e}")
        warn("?섎룞 ?ㅼ슫濡쒕뱶: https://huggingface.co/Qwen/Qwen2-VL-2B-Instruct")
        return False


def setup_clip():
    banner("?뼹", "[Eye] OpenCLIP (ViT-B/32) ?ㅼ슫濡쒕뱶")

    if not check_import("open_clip"):
        err("open-clip-torch 誘몄꽕移???pip install open-clip-torch")
        return False

    try:
        import open_clip
        info("ViT-B-32 / openai ?꾨━?몃젅???ㅼ슫濡쒕뱶 以?..")
        model, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32",
            pretrained="openai",
            cache_dir=str(MODELS / "clip")
        )
        ok(f"CLIP ViT-B/32 ?ㅼ슫濡쒕뱶 ?꾨즺 ??{MODELS / 'clip'}")
        return True
    except Exception as e:
        err(f"CLIP ?ㅼ슫濡쒕뱶 ?ㅽ뙣: {e}")
        return False


# ?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧
#  ?럺  VOICE  ?? Coqui XTTS v2
# ?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧
def setup_voice():
    banner("?럺", "[Voice] Coqui XTTS v2 ?ㅼ슫濡쒕뱶")

    if not check_import("TTS"):
        err("TTS 誘몄꽕移???pip install TTS")
        warn("二쇱쓽: torch 踰꾩쟾 ?명솚???뺤씤 ?꾩슂 (torch>=2.1)")
        return False

    try:
        import torch
        from TTS.api import TTS

        device = "cuda" if torch.cuda.is_available() else "cpu"
        info(f"?붾컮?댁뒪: {device} | Coqui XTTS v2 ?ㅼ슫濡쒕뱶 以?(~1.9GB)...")

        tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
        ok(f"XTTS v2 ?ㅼ슫濡쒕뱶 ?꾨즺 (device: {device})")

        # 李몄“ ?뚯꽦 ?섑뵆 ?덈궡
        sample_path = VOICE_SAMPLES / "director_voice.wav"
        if not sample_path.exists():
            warn(f"援?옣??李몄“ ?뚯꽦 ?놁쓬 ??{sample_path}")
            info("10珥??댁긽???⑥씪 ?붿옄 WAV ?뚯씪????寃쎈줈??蹂듭궗?섎㈃ 蹂댁씠???대줈???쒖꽦?붾맗?덈떎.")
        else:
            ok(f"李몄“ ?뚯꽦 諛쒓껄: {sample_path}")
        return True
    except Exception as e:
        err(f"XTTS v2 ?ㅼ슫濡쒕뱶 ?ㅽ뙣: {e}")
        return False


# ?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧
#  ?렞  BRAIN  ?? Ollama + Llama 3.1 ?곹깭 ?뺤씤
# ?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧
def setup_brain():
    banner("?렞", "[Brain] Ollama + Llama 3.1 ?곹깭 ?뺤씤")

    ollama_running = _check_ollama_port()
    if ollama_running:
        try:
            import requests
            r = requests.get("http://localhost:11434/api/tags", timeout=2)
            models = [m["name"] for m in r.json().get("models", [])]
            ok(f"Ollama ?곌껐 ?깃났. ?ㅼ튂??紐⑤뜽: {models}")
            if any("llama3.1" in m for m in models):
                ok("Llama 3.1 以鍮??꾨즺 ??)
            else:
                warn("Llama 3.1 誘몃떎?대줈??)
                info("?곕??먯뿉???ㅽ뻾: ollama pull llama3.1  (??4.7GB)")
        except Exception:
            ok("Ollama ?ы듃 ?대┝ (API ?묐떟 ?놁쓬)")
    else:
        warn("Ollama ?쒕쾭 誘멸???)
        info("1. https://ollama.ai ?먯꽌 Ollama ?ㅼ튂")
        info("2. ollama serve")
        info("3. ollama pull llama3.1")
        info("??Ollama ?놁씠??CCUT? 洹쒖튃 湲곕컲 ?꾨왂 ?쒗뵆由우쑝濡??숈옉?⑸땲??")

    return True


def _check_ollama_port() -> bool:
    """?뚯폆?쇰줈 Ollama ?ы듃(11434) ?대┝ ?щ? ?뺤씤 (釉붾줈???놁쓬)."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", 11434), timeout=0.5):
            return True
    except Exception:
        return False


# ?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧
#  ?몖  FACE  ?? Wav2Lip (?섎룞 ?ㅼ튂 ?덈궡)
# ?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧
def setup_face():
    banner("?몖", "[Face] Wav2Lip ?ㅼ튂 ?덈궡")

    ckpt_path       = MODELS / "wav2lip_gan.pth"
    face_det_path   = MODELS / "s3fd-619a316812.pth"
    wav2lip_dir     = BASE / "Wav2Lip"

    if ckpt_path.exists() and face_det_path.exists():
        ok(f"Wav2Lip 泥댄겕?ъ씤??諛쒓껄: {ckpt_path}")
        ok(f"S3FD ?쇨뎬?먯? 紐⑤뜽 諛쒓껄: {face_det_path}")
        ok("Wav2Lip ?ㅼ쟾 紐⑤뱶 ?쒖꽦??媛??")
    else:
        warn("Wav2Lip 紐⑤뜽 ?놁쓬 (FFmpeg ?대갚 紐⑤뱶濡??숈옉 以?")
        print()
        info("???섎룞 ?ㅼ튂 媛?대뱶 ??)
        print(f"""
  1. 由ы룷吏?좊━ ?대줎:
     git clone https://github.com/Rudrabha/Wav2Lip {wav2lip_dir}

  2. 紐⑤뜽 ?ㅼ슫濡쒕뱶 (Google Drive):
     wav2lip_gan.pth     ??{ckpt_path}
     s3fd-619a316812.pth ??{face_det_path}

     ?ㅼ슫濡쒕뱶 留곹겕: https://github.com/Rudrabha/Wav2Lip#getting-the-weights

  3. ?섏〈???ㅼ튂:
     pip install opencv-python-headless mediapipe batch-face-detection

  4. ?꾨즺 ??/global/status ?먯꽌 mode: WAV2LIP ?뺤씤
        """)

    return True


# ?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧
#  ?뾼  MEMORY  ?? Qdrant + Sentence Transformers
# ?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧
def setup_memory():
    banner("?뾼", "[Memory] Qdrant + Sentence Transformers 珥덇린??)

    missing = []
    if not check_import("qdrant_client"):
        missing.append("qdrant-client")
    if not check_import("sentence_transformers"):
        missing.append("sentence-transformers")

    if missing:
        err(f"誘몄꽕移??⑦궎吏: {', '.join(missing)}")
        info(f"pip install {' '.join(missing)}")
        return False

    try:
        from sentence_transformers import SentenceTransformer
        from qdrant_client import QdrantClient

        info("Sentence-BERT 紐⑤뜽 珥덇린??以?..")
        model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        ok(f"Sentence-BERT 以鍮??꾨즺 (dim={model.get_sentence_embedding_dimension()})")

        info(f"Qdrant ?뚯씪 湲곕컲 DB 珥덇린??以?.. ({QDRANT_DB})")
        client = QdrantClient(path=str(QDRANT_DB))
        ok(f"Qdrant DB 珥덇린???꾨즺 ??{QDRANT_DB}")
        return True
    except Exception as e:
        err(f"Memory 珥덇린???ㅽ뙣: {e}")
        return False


# ?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧
#  ?뱤  CHECK  ?? ?꾩껜 ?ㅼ튂 ?꾪솴 由ы룷??
# ?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧
def check_all():
    banner("?뱤", "CCUT 1.0.6 濡쒖뺄 AI ?ㅼ튂 ?꾪솴 由ы룷??)

    results = []

    def chk(label: str, condition: bool, hint: str = ""):
        sym = "?? if condition else "??
        results.append(condition)
        msg = f"  {sym}  {label}"
        if not condition and hint:
            msg += f"\n       ??{hint}"
        print(msg)

    print()

    # ?⑦궎吏
    print("  [?⑦궎吏]")
    chk("openai-whisper",          check_import("whisper"),             "pip install openai-whisper")
    chk("transformers (Qwen)",     check_import("transformers"),        "pip install transformers accelerate")
    chk("open-clip-torch",         check_import("open_clip"),           "pip install open-clip-torch")
    chk("TTS (XTTS v2)",           check_import("TTS"),                 "pip install TTS")
    chk("sentence-transformers",   check_import("sentence_transformers"), "pip install sentence-transformers")
    chk("qdrant-client",           check_import("qdrant_client"),       "pip install qdrant-client")
    chk("opencv-python",           check_import("cv2"),                 "pip install opencv-python-headless")

    print()
    # 紐⑤뜽 ?뚯씪
    print("  [紐⑤뜽 ?뚯씪]")
    whisper_base = any((MODELS / "whisper").glob("*base*")) if (MODELS / "whisper").exists() else False
    chk("Whisper base",        whisper_base,                        "python setup_local_ai.py --ear")
    chk("Wav2Lip GAN",         (MODELS / "wav2lip_gan.pth").exists(), "媛?대뱶: python setup_local_ai.py --face")
    chk("S3FD face detector",  (MODELS / "s3fd-619a316812.pth").exists(), "")
    chk("director_voice.wav",  (VOICE_SAMPLES / "director_voice.wav").exists(), f"{VOICE_SAMPLES} ??10珥??댁긽 WAV 諛곗튂")

    print()
    # Ollama ???뚯폆?쇰줈 鍮좊Ⅴ寃??ы듃 ?뺤씤
    print("  [Ollama LLM]")
    ollama_up = _check_ollama_port()
    chk("Ollama ?쒕쾭", ollama_up, "https://ollama.ai ?ㅼ튂 ??ollama serve")
    if ollama_up:
        try:
            import requests
            r = requests.get("http://localhost:11434/api/tags", timeout=1)
            models_found = [m["name"] for m in r.json().get("models", [])]
            chk("Llama 3.1", any("llama3.1" in m for m in models_found), "ollama pull llama3.1")
        except Exception:
            chk("Llama 3.1", False, "ollama pull llama3.1")
    else:
        chk("Llama 3.1", False, "ollama pull llama3.1")

    print()
    score = sum(results)
    total = len(results)
    pct   = int(score / total * 100)
    print(f"  AI ?낅┰???먯닔: {score}/{total} ({pct}%)")
    if pct == 100:
        print("  ?룇 ?꾩쟾 濡쒖뺄 ?먯쑉 ?ㅽ뒠?붿삤 ?ъ꽦!")
    elif pct >= 70:
        print("  ?윞 ?듭떖 湲곕뒫 媛??以? ?섎㉧吏 ?ㅼ튂 沅뚯옣.")
    else:
        print("  ?뵶 湲곕낯 湲곕뒫留??묐룞 以? setup_local_ai.py ?ㅽ뻾 沅뚯옣.")


# ?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧
#  MAIN
# ?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧?먥븧
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CCUT 1.0.6 濡쒖뺄 AI ?섍꼍 援ъ텞")
    parser.add_argument("--ear",    action="store_true", help="Whisper ?ㅼ슫濡쒕뱶")
    parser.add_argument("--eye",    action="store_true", help="Qwen2-VL + CLIP ?ㅼ슫濡쒕뱶")
    parser.add_argument("--voice",  action="store_true", help="XTTS v2 ?ㅼ슫濡쒕뱶")
    parser.add_argument("--brain",  action="store_true", help="Ollama ?곹깭 ?뺤씤")
    parser.add_argument("--face",   action="store_true", help="Wav2Lip ?덈궡")
    parser.add_argument("--memory", action="store_true", help="Qdrant 珥덇린??)
    parser.add_argument("--check",  action="store_true", help="?꾩껜 ?ㅼ튂 ?꾪솴 由ы룷??)
    parser.add_argument("--size",   default="base",      help="Whisper 紐⑤뜽 ?ш린 (base/large-v3)")
    parser.add_argument("--qwen",   default="2B",         help="Qwen2-VL ?ш린 (2B/7B)")
    args = parser.parse_args()

    run_all = not any([
        args.ear, args.eye, args.voice, args.brain,
        args.face, args.memory, args.check
    ])

    print()
    print("  ?? CCUT 1.0.6 Pure Local AI Studio ???섍꼍 援ъ텞湲?)
    print(f"  ???寃쎈줈: {MODELS}")

    t0 = time.time()

    if args.check:
        check_all()
    else:
        if run_all or args.ear:    setup_ear(args.size)
        if run_all or args.eye:    setup_eye(args.qwen); setup_clip()
        if run_all or args.voice:  setup_voice()
        if run_all or args.brain:  setup_brain()
        if run_all or args.face:   setup_face()
        if run_all or args.memory: setup_memory()

        if run_all:
            print(f"\n{'??*55}")
            print(f"  ???꾩껜 援ъ텞 ?꾨즺 ({time.time()-t0:.0f}s)")
            print("  ?댁젣 ?명꽣?룹쓣 ?딆뼱??CCUT? 硫덉텛吏 ?딆뒿?덈떎.")
            print(f"{'??*55}\n")
            check_all()

