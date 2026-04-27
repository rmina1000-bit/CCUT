import os

class SearchEngine:
    def __init__(self):
        self.mode = "simulation"
        print("Search Engine Initialized (Simulation)")

    def is_ready(self): return False
    def status(self): return {"mode": self.mode}
    def search_semantic(self, query, limit=5): return []

search_engine = SearchEngine()
