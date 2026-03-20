import sys
import json
import os

# Add CCUT root to path so ccut_core can be imported
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ccut_core.fragment_generator.fragment_generator import generate_fragments

video_path = r"d:\CCUT 1.0.1\20230209_114423.mp4"
output_path = r"d:\CCUT 1.0.1\ui\mock\mock_fragments.json"

def main():
    if not os.path.exists(video_path):
        print(f"File not found: {video_path}")
        sys.exit(1)

    print("Beginning scene and audio detection. This might take a minute depending on video length...")
    fragments = generate_fragments(video_path)

    # enrich with duration to match UI expectations
    for frag in fragments:
        frag["duration"] = round(frag["end"] - frag["start"], 3)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(fragments, f, indent=2)

    print(f"SUCCESS: Generated {len(fragments)} real fragments to {output_path}")

if __name__ == "__main__":
    main()
