import os
import uuid

class VectorEngine:
    def __init__(self):
        self.mode = "simulation"
        self.collection_name = "ccut_fragments"
        print(f"Vector Engine Initialized [MODE: {self.mode}]")

    def is_ready(self):
        return False

    def upsert_fragment(self, fragment_id, transcript, metadata=None):
        print(f"[VECTOR] Upsert: {fragment_id}")

    def search(self, query, top_k=5):
        return []

    def status(self):
        return {"ready": False, "mode": "simulation"}

vector_engine = VectorEngine()
