from pydantic import BaseModel, Field
from typing import List, Dict, Any

class ReviewResult(BaseModel):
    """
    [STEP 11-A] ReviewResult
    Represents the evaluation output of a single synthetic reviewer.
    """
    persona_id: str = Field(description="The unique identifier of the reviewer persona.")
    name: str = Field(description="The display name of the reviewer.")
    cinematic_flow_score: float = Field(description="Score representing transition quality and aesthetic flow (0.0 to 1.0).")
    boredom_score: float = Field(description="Score representing how boring or stagnant the pacing is (0.0 to 1.0).")
    pacing_fatigue_score: float = Field(description="Score representing pacing fatigue or fast cut stress (0.0 to 1.0).")
    reaction_preservation_score: float = Field(description="Score representing how well emotional reaction shots are preserved (0.0 to 1.0).")
    scenery_overuse_score: float = Field(description="Score representing whether environmental/scenery shots are overused (0.0 to 1.0).")
    overall_rating: float = Field(description="Weighted overall score calculated from reviewer preferences (0.0 to 1.0).")
    critique: str = Field(description="Natural language critique explaining the evaluation and feedback.")

class ProposalSwarmAudit(BaseModel):
    """
    [STEP 11-A] ProposalSwarmAudit
    Represents the complete swarm audit results for a single proposal sequence.
    """
    proposal_id: str
    mode: str  # "A" or "B"
    average_overall_rating: float = Field(description="The average overall rating across all reviewers.")
    reviews: List[ReviewResult] = Field(default_list=list, description="The list of reviews from all swarm personas.")
    composite_metrics: Dict[str, float] = Field(description="Aggregated average scores for each evaluation axis.")
