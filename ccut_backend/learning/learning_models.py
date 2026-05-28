import datetime
from sqlalchemy import Column, String, Float, Integer, JSON, DateTime, ForeignKey, Boolean
from database import Base, engine

class UserEditDecisionTable(Base):
    __tablename__ = "user_edit_decisions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    decision_id = Column(String, unique=True, index=True, nullable=False)
    project_id = Column(String, index=True, nullable=False)
    chosen_proposal_id = Column(String, nullable=True)
    rejected_proposal_id = Column(String, nullable=True)
    user_intent = Column(JSON, nullable=True) # {instruction_text, target_length}
    selected_fragments = Column(JSON, nullable=True) # [frag_id1, frag_id2, ...]
    rejected_fragments = Column(JSON, nullable=True)
    decision_type = Column(String, index=True, nullable=False) # "A_CHOSEN", "B_CHOSEN", "PBE_EDIT", "REPROPOSAL"
    delta_log = Column(JSON, nullable=True) # For PBE delta shifts [{fragment_id, delta_left, delta_right}]
    created_at = Column(DateTime, default=datetime.datetime.now)

class PreferencePairTable(Base):
    __tablename__ = "preference_pairs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    pair_id = Column(String, unique=True, index=True, nullable=False)
    project_id = Column(String, index=True, nullable=False)
    winner_proposal_id = Column(String, nullable=False)
    loser_proposal_id = Column(String, nullable=False)
    winner_sequence = Column(JSON, nullable=False) # List of clip sequences
    loser_sequence = Column(JSON, nullable=False)
    winner_metrics = Column(JSON, nullable=True) # HRS metrics
    loser_metrics = Column(JSON, nullable=True)
    reason_hint = Column(String, nullable=True) # "user_preference", "teacher_ai_eval"
    created_at = Column(DateTime, default=datetime.datetime.now)

class WeakLabelTable(Base):
    __tablename__ = "weak_labels"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    fragment_id = Column(String, index=True, nullable=False)
    source_id = Column(String, index=True, nullable=False)
    label_name = Column(String, index=True, nullable=False) # e.g. "hook_candidate", "boredom_risk"
    confidence = Column(Float, nullable=False, default=0.5)
    rule_source = Column(String, nullable=False) # "weak_rule_engine", "teacher_ai_prompt"
    created_at = Column(DateTime, default=datetime.datetime.now)

class EditingPatternMemoryTable(Base):
    __tablename__ = "editing_pattern_memory"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    pattern_id = Column(String, unique=True, index=True, nullable=False)
    pattern_type = Column(String, index=True, nullable=False) # e.g., "reaction_hold", "scenery_bridge"
    conditions = Column(JSON, nullable=True) # Trigger heuristics
    recommended_action = Column(JSON, nullable=True) # Mutators e.g. {reaction_priority_multiplier: 1.25}
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    avg_user_acceptance = Column(Float, default=0.5)
    avg_hrs_delta = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

class TemporalFlowMemoryTable(Base):
    __tablename__ = "temporal_flow_memory"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    flow_id = Column(String, unique=True, index=True, nullable=False)
    flow_sequence = Column(JSON, nullable=False) # e.g. ["hook", "setup", "tension", "pause", "payoff", "rehook"]
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    avg_user_acceptance = Column(Float, default=0.5)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

class HumanWatchSessionTable(Base):
    __tablename__ = "human_watch_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, unique=True, index=True, nullable=False)
    project_id = Column(String, index=True, nullable=False)
    viewer_id = Column(String, nullable=True)
    playback_actions = Column(JSON, nullable=False) # e.g. [{"time": 3.2, "action": "skip"}]
    retention_map = Column(JSON, nullable=False) # e.g. {"frag_1": 1.0, "frag_2": 0.0}
    created_at = Column(DateTime, default=datetime.datetime.now)

def init_learning_db():
    Base.metadata.create_all(bind=engine)
