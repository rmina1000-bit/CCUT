import os
import sys
import argparse
from pathlib import Path

# Add backend to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "ccut_backend"))

# Set database path to production
DB_PATH = r"D:\CCUT1.0.4\ccut_backend\ccut_app.db"
os.environ["CCUT_DATABASE_URL"] = f"sqlite:///{DB_PATH}"

from learning.youtube_robot import YouTubeRobotLearner
from learning.learning_models import UserEditDecisionTable
from database import SessionLocal

def main():
    parser = argparse.ArgumentParser(description="CCUT 1.0.4 YouTube Robot Learner CLI")
    parser.add_argument("--query", type=str, default="travel vlog", help="YouTube search query keyword")
    parser.add_argument("--limit", type=int, default=3, help="Max videos to download/analyze (default: 3)")
    parser.add_argument("--media", action="store_true", help="Download preview media snippets and run physical scene/volume cuts")
    args = parser.parse_args()

    print("==============================================================")
    print(" CCUT 1.0.4 YOUTUBE ROBOT LEARNER START")
    print("==============================================================")
    print(f"Target Query : {args.query}")
    print(f"Limit        : {args.limit} videos")
    print(f"Media Mode   : {'Enabled (will fetch worst 15s snippets)' if args.media else 'Disabled (Surrogate mode)'}")
    print("==============================================================")

    res = YouTubeRobotLearner.execute_learning_step(
        query=args.query,
        limit=args.limit,
        force_media=args.media
    )

    results = res.get("results", [])
    print("\n==============================================================")
    print(" LEARNING EXECUTION SUMMARY")
    print("==============================================================")
    print(f"Total Videos Analyzed: {len(results)}")
    for idx, r in enumerate(results):
        print(f"\n({idx+1}/{len(results)}) Video ID: {r['video_id']}")
        print(f" - URL: {r['url']}")
        print(f" - Scene cuts: {r['analysis'].get('scene_cuts')} (Avg pacing: {r['analysis'].get('avg_scene_duration')}s)")
        print(f" - Audio Peak: {r['analysis'].get('max_volume_db')} dB")
        print(f" - Activated patterns: {r['activated_patterns']}")

    print("\nLearning process completed successfully.")
    print("==============================================================")

if __name__ == "__main__":
    main()
