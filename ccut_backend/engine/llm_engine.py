import os

class LLMEngine:
    def __init__(self):
        self.mode = "simulation"
        print("LLM Engine Initialized (Simulation)")

    def is_ready(self): return False
    def generate_strategy(self, query, fragments_ctx):
        return f"AI Perspective for {query}"

llm_pd = LLMEngine()
