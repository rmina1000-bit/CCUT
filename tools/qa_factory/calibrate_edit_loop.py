import os
import sys
import time
import json
import random
import hashlib
import argparse
from pathlib import Path

# Set database path to production before any imports
DB_PATH = r"D:\CCUT1.0.4\ccut_backend\ccut_app.db"
os.environ["CCUT_DATABASE_URL"] = f"sqlite:///{DB_PATH}"

PROJECT_ROOT = Path("D:/CCUT1.0.4").resolve()
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "ccut_backend"))

from database import SessionLocal, Base, engine
from archive.manager import bams
from archive.db_models import SourceTable, FragmentTable, EvidenceTable, SemanticFragmentTable, ProposalTable
from engine.proposal_engine import ProposalEngine
from engine.video_engine import video_engine
from ai.narrative.qwen_narrative_translator import QwenNarrativeTranslator

# -------------------------------------------------------------
# 1. Video Discovery and Ingestion
# -------------------------------------------------------------

def calculate_sha256(filepath: Path) -> str:
    """Calculate SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(8192), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def ingest_videos_from_downloads():
    print("[INGESTION] Scanning C:\\Users\\rmina\\Downloads for videos...")
    downloads_dir = Path("C:/Users/rmina/Downloads")
    if not downloads_dir.exists():
        print(f"[ERROR] Downloads directory {downloads_dir} does not exist.")
        return []
        
    mp4_files = list(downloads_dir.glob("*.mp4"))
    print(f"[INGESTION] Found {len(mp4_files)} .mp4 files.")
    
    db = SessionLocal()
    ingested_sources = []
    
    try:
        for idx, video_path in enumerate(mp4_files):
            print(f"\n[INGESTION] Processing ({idx+1}/{len(mp4_files)}): {video_path.name}")
            
            fingerprint = calculate_sha256(video_path)
            existing_src = db.query(SourceTable).filter_by(hash_value=fingerprint).first()
            if existing_src:
                print(f" -> Existing source found in DB: {existing_src.source_id}")
                frags = db.query(FragmentTable).filter_by(source_id=existing_src.source_id).all()
                sems = db.query(SemanticFragmentTable).filter_by(source_id=existing_src.source_id).all()
                if frags and sems:
                    ingested_sources.append(existing_src.source_id)
                    continue
                else:
                    source_id = existing_src.source_id
                    print(f" -> Source exists but fragments/semantics are missing. Re-populating...")
            else:
                source_id = f"SRC_{fingerprint[:8].upper()}"
            
            meta = video_engine.get_metadata(str(video_path))
            duration = meta.get("duration", 60.0)
            if duration <= 0:
                duration = 60.0
            
            if not existing_src:
                new_src = SourceTable(
                    source_id=source_id,
                    file_path=str(video_path.resolve()),
                    title=video_path.name,
                    duration=duration,
                    fps=meta.get("fps", 30.0),
                    hash_value=fingerprint
                )
                db.add(new_src)
                db.flush()
                print(f" -> Registered new Source: {source_id} (Duration: {duration:.2f}s)")
            
            db.query(FragmentTable).filter_by(source_id=source_id).delete()
            db.query(EvidenceTable).filter_by(source_id=source_id).delete()
            db.query(SemanticFragmentTable).filter_by(source_id=source_id).delete()
            db.flush()
            
            seg_len = 10.0
            num_frags = int(duration // seg_len)
            if num_frags < 5:
                num_frags = 5
            seg_len = duration / num_frags
            
            for f_idx in range(num_frags):
                frag_id = f"VF{f_idx + 1}_{source_id}"
                start = f_idx * seg_len
                end = (f_idx + 1) * seg_len
                
                new_frag = FragmentTable(
                    fragment_id=frag_id,
                    source_id=source_id,
                    start_time=start,
                    end_time=end,
                    duration=seg_len,
                    status="VIRTUAL",
                    intelligence={
                        "transcript": f"Dialogue segment {f_idx + 1}. Video {video_path.name}.",
                        "hook_score": 0.5
                    }
                )
                db.add(new_frag)
                
                new_ev = EvidenceTable(
                    fragment_id=frag_id,
                    source_id=source_id,
                    start=start,
                    end=end,
                    time_offset=start,
                    text=f"Subtitle {f_idx + 1}: Content from {start:.1f}s to {end:.1f}s.",
                    audio_energy=random.uniform(0.1, 0.8),
                    motion_score=random.uniform(0.1, 0.7),
                    confidence=1.0,
                    fallback_reason=None
                )
                db.add(new_ev)
                
                if f_idx == 0:
                    role = "hook"
                elif f_idx == num_frags - 1:
                    role = "payoff"
                else:
                    role = random.choice(["main", "reaction", "scenery", "main"])
                
                new_sem = SemanticFragmentTable(
                    id=frag_id,
                    fragment_id=frag_id,
                    source_id=source_id,
                    start=start,
                    end=end,
                    semantic_json={"topic": f"Topic_{f_idx}", "description": f"Segment {f_idx} description"},
                    structural_json={"role": role, "edit_value": random.uniform(0.4, 0.95)},
                    continuity_json={"tempo": "medium"},
                    confidence=1.0
                )
                db.add(new_sem)
            
            db.commit()
            print(f" -> Generated {num_frags} virtual fragments & semantics.")
            ingested_sources.append(source_id)
            
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Ingestion failed: {e}")
    finally:
        db.close()
        
    return ingested_sources

# -------------------------------------------------------------
# 2. Calibration and Simulation Loop
# -------------------------------------------------------------

INTENT_PROFILES = [
    {
        "name": "Documentary",
        "instruction_text": "Documentary direction tone with long slow breathing, emotion and reaction based.",
        "target_persona": "documentary_director"
    },
    {
        "name": "YouTube Vlog",
        "instruction_text": "YouTube travel vlog video with reduced scenery, fast cuts and dialogue.",
        "target_persona": "youtube_vlogger"
    },
    {
        "name": "Cinematic Film",
        "instruction_text": "Cinematic editing style focusing on dialogue rhythm and reaction cuts.",
        "target_persona": "cinematic_editor"
    }
]

def run_calibration_loop(sources, run_limit=3):
    print("\n" + "=" * 80)
    print(f" STARTING CALIBRATION RUNS (LIMIT: {run_limit}) (STEP 13)")
    print("=" * 80)
    
    if not sources:
        print("[ERROR] No sources available for calibration. Exiting.")
        return []
        
    from ai.perception.human_reality_score import HumanRealityScore
    from tools.human_swarm.critique_arena import CritiqueArena
    from engine.render_engine import render_engine
    import uuid
    import subprocess
    
    hrs_evaluator = HumanRealityScore()
    arena = CritiqueArena()
    
    stats = []
    converged_count = 0
    start_time = time.time()
    last_heartbeat_time = time.time()
    
    adj_factors = {
        "reaction_priority_multiplier_mod": 1.0,
        "reduce_scenery_ratio_mod": 1.0,
        "breathing_multiplier_mod": 1.0,
        "emotional_continuity_weight_mod": 1.0
    }
    
    original_translate = QwenNarrativeTranslator.translate_direction
    
    def patched_translate(self_translator, direction):
        res = original_translate(self_translator, direction)
        res["reaction_priority_multiplier"] *= adj_factors["reaction_priority_multiplier_mod"]
        res["reduce_scenery_ratio"] *= adj_factors["reduce_scenery_ratio_mod"]
        res["breathing_multiplier"] *= adj_factors["breathing_multiplier_mod"]
        res["emotional_continuity_weight"] *= adj_factors["emotional_continuity_weight_mod"]
        return res
        
    QwenNarrativeTranslator.translate_direction = patched_translate
    
    def probe_duration(file_path):
        try:
            cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, shell=False, timeout=15)
            if res.returncode == 0 and res.stdout.strip():
                return float(res.stdout.strip())
        except subprocess.TimeoutExpired:
            print(f"[TIMEOUT] ffprobe execution timed out for {file_path}")
        except Exception as e:
            print(f"[FFPROBE ERROR] {e}")
        return 0.0

    def run_playwright_test():
        try:
            cmd = ["npx.cmd", "playwright", "test", "e2e/browser_reality.spec.ts"]
            res = subprocess.run(cmd, cwd="D:/CCUT1.0.4/ccut_frontend", capture_output=True, text=True, shell=False, timeout=120)
            return res.returncode == 0
        except subprocess.TimeoutExpired:
            print("[TIMEOUT] Playwright test execution timed out (120s limit)")
        except Exception as e:
            print(f"[PLAYWRIGHT ERROR] {e}")
        return False
            
    db = SessionLocal()
    try:
        for run_idx in range(1, run_limit + 1):
            project_id = f"proj_calib_run_{run_idx}"
            
            num_sel = random.randint(1, min(len(sources), 4))
            selected_sources = random.sample(sources, num_sel)
            
            target_len = random.choice([5.0, 8.0, 12.0])
            profile = random.choice(INTENT_PROFILES)
            
            intent_data = {
                "instruction_text": profile["instruction_text"],
                "target_length": target_len,
                "coverage": "balanced_sources" if num_sel > 1 else None,
                "priority_axis": {"visual": 1.0, "speech": 1.0, "emotion": 1.0}
            }
            
            bams.save_user_intent(project_id, intent_data)
            
            fragments_pool = []
            for s_id in selected_sources:
                fragments_pool.extend(bams.get_semantic_fragments(s_id))
            
            adj_factors["reaction_priority_multiplier_mod"] = 1.0
            adj_factors["reduce_scenery_ratio_mod"] = 1.0
            adj_factors["breathing_multiplier_mod"] = 1.0
            adj_factors["emotional_continuity_weight_mod"] = 1.0
            
            converged = False
            iterations = 0
            max_iterations = 5
            hrs_report = None
            proposal_b = None
            arena_report = None
            
            render_success = False
            output_mp4_path = ""
            actual_duration = 0.0
            file_size_bytes = 0
            playwright_pass = False
            critical_error = ""
            
            print(f"\n[RUN {run_idx}/{run_limit}] Project: {project_id} | Profile: {profile['name']} | Sources: {selected_sources} | Target Length: {target_len}s")
            
            while iterations < max_iterations and not converged:
                iterations += 1
                
                # HEARTBEAT CHECK
                current_time = time.time()
                if current_time - last_heartbeat_time >= 30.0:
                    print(f"[HEARTBEAT] Elapsed: {current_time - start_time:.1f}s | Current Run Index: {run_idx}/{run_limit} | Iteration: {iterations} | Converged Count: {converged_count}")
                    last_heartbeat_time = current_time
                
                engine_inst = ProposalEngine(bams)
                proposals = engine_inst.generate_proposals_from_fragments(
                    project_id=project_id,
                    source_ids=selected_sources,
                    fragments=fragments_pool,
                    target_len=target_len,
                    story_context={"user_intent": intent_data}
                )
                
                if not proposals:
                    critical_error = "No proposals generated"
                    break
                    
                proposal_b = next((p for p in proposals if p["mode"] == "B"), None)
                if not proposal_b:
                    critical_error = "Proposal B not found"
                    break
                    
                from archive.db_models import ExportInputTable
                export_id = f"EXP_INP_{uuid.uuid4().hex[:8].upper()}"
                
                clips = []
                for order, f in enumerate(proposal_b["sequence"]):
                    clips.append({
                        "fragment_id": f.get("fragment_id"),
                        "source_id": f.get("source_id"),
                        "start": float(f.get("start", f.get("start_time", 0.0))),
                        "end": float(f.get("end", f.get("end_time", 0.0))),
                        "duration": float(f.get("duration", float(f.get("end", 0)) - float(f.get("start", 0)))),
                        "order": order
                    })
                
                new_export_input = ExportInputTable(
                    export_id=export_id,
                    source_id=selected_sources[0] if len(selected_sources) == 1 else None,
                    proposal_id=proposal_b["proposal_id"],
                    mode="B",
                    clips=clips,
                    total_duration=proposal_b["duration"],
                    status="EXPORT_INPUT_READY"
                )
                db.merge(new_export_input)
                db.commit()
                
                render_res = render_engine.render_from_export_input(export_id)
                
                if render_res.get("success"):
                    render_success = True
                    output_mp4_path = str(render_engine.export_dir / Path(render_res["output_url"]).name)
                    
                    if os.path.exists(output_mp4_path):
                        file_size_bytes = os.path.getsize(output_mp4_path)
                        actual_duration = probe_duration(output_mp4_path)
                    else:
                        render_success = False
                        critical_error = "Output file missing after render success"
                else:
                    render_success = False
                    critical_error = f"FFmpeg render failed: {render_res.get('message', 'Unknown')}"
                    
                playwright_pass = run_playwright_test()
                
                hrs_report = proposal_b.get("human_reality_score_data")
                if not hrs_report:
                    hrs_report = hrs_evaluator.evaluate_sequence(proposal_b["sequence"])
                    proposal_b["human_reality_score_data"] = hrs_report
                    
                actual_hrs = hrs_report["human_reality_score"]
                
                arena_report = arena.resolve_critique(proposal_b["sequence"], hrs_report)
                debates = arena_report["arena_debates"]
                suggested = arena_report["suggested_modifications"]
                
                print(f" -> Iteration {iterations}: HRS={actual_hrs:.4f} | Render={render_success} | FFprobe Dur={actual_duration:.2f}s | Playwright={playwright_pass}")
                
                if run_idx == 1:
                    if actual_hrs >= 0.72 and render_success and playwright_pass and actual_duration > 0.0:
                        converged = True
                        converged_count += 1
                        print(f" -> [CONVERGED] Calibration successful in {iterations} iterations!")
                    else:
                        if "reaction_priority_multiplier_mod" in suggested:
                            adj_factors["reaction_priority_multiplier_mod"] *= suggested["reaction_priority_multiplier_mod"]
                        if "reduce_scenery_ratio_mod" in suggested:
                            adj_factors["reduce_scenery_ratio_mod"] *= suggested["reduce_scenery_ratio_mod"]
                        if "breathing_multiplier_mod" in suggested:
                            adj_factors["breathing_multiplier_mod"] *= suggested["breathing_multiplier_mod"]
                        if "emotional_continuity_weight_mod" in suggested:
                            adj_factors["emotional_continuity_weight_mod"] *= suggested["emotional_continuity_weight_mod"]
                        for k in adj_factors:
                            adj_factors[k] = max(0.15, min(6.0, adj_factors[k]))
                else:
                    if iterations == max_iterations:
                        print(" -> [NOT CONVERGED] Max iterations reached.")
                    else:
                        if "reaction_priority_multiplier_mod" in suggested:
                            adj_factors["reaction_priority_multiplier_mod"] *= suggested["reaction_priority_multiplier_mod"]
                            
            if proposal_b:
                proposal_b["human_reality_score_data"] = hrs_report
                db_p = ProposalTable(
                    proposal_id=proposal_b["proposal_id"],
                    source_id=project_id,
                    mode="B",
                    sequence=proposal_b["sequence"],
                    duration=proposal_b["duration"],
                    proposal_reason={
                        "mode_reason": "calibrated_cinematic_layer",
                        "calib_iterations": iterations,
                        "calib_converged": converged,
                        "calib_factors": {k: round(v, 2) for k, v in adj_factors.items()},
                        "target_profile": profile["name"],
                        "human_reality_score": hrs_report["human_reality_score"],
                        "critique_debate": arena_report["arena_debates"],
                        "original_reason": proposal_b.get("proposal_reason", {}),
                        "render_success": render_success,
                        "output_mp4_path": output_mp4_path,
                        "actual_duration": actual_duration,
                        "file_size_bytes": file_size_bytes,
                        "playwright_pass": playwright_pass,
                        "critical_error": critical_error
                    },
                    confidence=0.95
                )
                db.merge(db_p)
                db.commit()
            
            stats.append({
                "run": run_idx,
                "project_id": project_id,
                "profile": profile["name"],
                "sources": selected_sources,
                "target_length": target_len,
                "converged": converged,
                "iterations": iterations,
                "human_reality_score": hrs_report["human_reality_score"] if hrs_report else 0.0,
                "visual_comfort": hrs_report["metrics"]["visual_comfort"] if hrs_report else 0.0,
                "auditory_comfort": hrs_report["metrics"]["auditory_comfort"] if hrs_report else 0.0,
                "immersion": hrs_report["metrics"]["immersion"] if hrs_report else 0.0,
                "factors": {k: round(v, 2) for k, v in adj_factors.items()},
                "render_success": render_success,
                "output_mp4_path": output_mp4_path,
                "actual_duration": actual_duration,
                "file_size_bytes": file_size_bytes,
                "playwright_pass": playwright_pass,
                "critical_error": critical_error
            })
            
    except Exception as e:
        print(f"[CRITICAL] Loop error: {e}")
    finally:
        db.close()
        QwenNarrativeTranslator.translate_direction = original_translate
        
    return stats

# -------------------------------------------------------------
# 3. Main Routine
# -------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3, help="Number of calibration runs to execute (default: 3)")
    args = parser.parse_args()
    
    start_time = time.time()
    
    ingested_sources = ingest_videos_from_downloads()
    if not ingested_sources:
        print("[WARN] Ingest from downloads yielded 0 sources. Checking DB for pre-existing sources...")
        db = SessionLocal()
        try:
            db_sources = db.query(SourceTable).all()
            valid_sources = []
            for src in db_sources:
                if os.path.exists(src.file_path):
                    valid_sources.append(src.source_id)
            ingested_sources = valid_sources
            print(f"[INGESTION] Found {len(ingested_sources)} pre-existing valid sources in DB.")
        except Exception as e:
            print(f"[ERROR] Failed to query existing sources from DB: {e}")
        finally:
            db.close()
            
    if not ingested_sources:
        print("[ERROR] No valid sources found. Exiting.")
        sys.exit(1)
        
    stats = run_calibration_loop(ingested_sources, run_limit=args.runs)
    
    total_runs = len(stats)
    converged_runs = sum(1 for s in stats if s["converged"])
    total_iterations = sum(s["iterations"] for s in stats)
    avg_hrs = sum(s["human_reality_score"] for s in stats) / total_runs if total_runs else 0.0
    avg_vis = sum(s["visual_comfort"] for s in stats) / total_runs if total_runs else 0.0
    avg_aud = sum(s["auditory_comfort"] for s in stats) / total_runs if total_runs else 0.0
    avg_imm = sum(s["immersion"] for s in stats) / total_runs if total_runs else 0.0
    
    duration = time.time() - start_time
    
    print("\n" + "=" * 80)
    print(" CALIBRATION RESULTS SUMMARY (SMOKE)")
    print("=" * 80)
    print(f"Total Runs: {total_runs}")
    print(f"Convergence Rate: {converged_runs}/{total_runs} ({converged_runs/total_runs*100:.1f}%)")
    print(f"Average Iterations: {total_iterations/total_runs:.2f}")
    print(f"Average HRS: {avg_hrs:.4f}")
    print(f"Average Visual Comfort: {avg_vis:.3f}")
    print(f"Average Auditory Comfort: {avg_aud:.3f}")
    print(f"Average Immersion: {avg_imm:.3f}")
    print(f"Total Execution Time: {duration:.2f}s")
    print("=" * 80)

if __name__ == "__main__":
    main()
