import os

class VisionEngine:
    def __init__(self):
        self._clip_ready = False
        self._vl_ready = False
        print("Vision Engine Initialized (Simulation)")

    def is_clip_ready(self): return False
    def is_vl_ready(self): return False
    def status(self): return {"clip": False, "vl": False}
    def describe_scene(self, image_path, force_vl=False):
        return f"Scene description for {os.path.basename(image_path)}"

vision_engine = VisionEngine()
