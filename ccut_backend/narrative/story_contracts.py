from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class SourceRole:
    source_id: str
    label: Optional[str] = None
    role: str = "support"
    character: str = "undetermined"
    reason: str = ""

@dataclass
class CandidateFragment:
    fragment_id: str
    source_id: str
    role: str = "candidate"
    reason: str = ""
    score_basis: Dict[str, Any] = field(default_factory=dict)

@dataclass
class StorylineStep:
    step: int
    phase: str
    description: str
    source_ids: List[str] = field(default_factory=list)
    candidate_fragments: List[str] = field(default_factory=list)

@dataclass
class StorylineOption:
    option_id: str
    template_id: str
    title: str
    summary: str
    steps: List[StorylineStep] = field(default_factory=list)

@dataclass
class ProposalConstraint:
    target_length: Optional[float] = None
    must_include_fragments: List[str] = field(default_factory=list)
    avoid_fragments: List[str] = field(default_factory=list)
    preferred_sources: List[str] = field(default_factory=list)
    avoid_sources: List[str] = field(default_factory=list)
    tone: Optional[str] = None

@dataclass
class StoryTrace:
    source_role_reason: List[str] = field(default_factory=list)
    template_reason: List[str] = field(default_factory=list)
    candidate_reason: List[str] = field(default_factory=list)
    excluded_source_reason: List[str] = field(default_factory=list)

@dataclass
class StoryPlan:
    story_plan_id: str
    project_id: str
    source_ids: List[str]
    project_summary: str = ""
    source_roles: List[SourceRole] = field(default_factory=list)
    candidate_fragments: List[CandidateFragment] = field(default_factory=list)
    storyline_options: List[StorylineOption] = field(default_factory=list)
    selected_storyline_id: Optional[str] = None
    user_feedback: List[str] = field(default_factory=list)
    final_storyline: List[StorylineStep] = field(default_factory=list)
    proposal_constraints: ProposalConstraint = field(default_factory=ProposalConstraint)
    quality_warnings: List[str] = field(default_factory=list)
    trace: StoryTrace = field(default_factory=StoryTrace)
