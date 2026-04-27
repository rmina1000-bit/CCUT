import os

class VoiceEngine:
    def __init__(self):
        self.mode = "simulation"
        print("Voice Engine Initialized (Simulation)")

    def is_ready(self): return False
    def clone_and_speak(self, text, reference_audio_name, output_name, language):
        return "voice_output.wav"

voice_engine = VoiceEngine()
