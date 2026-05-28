from pydantic import BaseModel, Field
from typing import Optional

class NarrativeDirection(BaseModel):
    """
    [STEP 10-L-CONTRACT] NarrativeDirection
    Defines the creative, directing-level instructions from the External Narrative Director LLM.
    This contract focuses purely on narrative aesthetics and directing guidelines.
    No execution metadata (such as cut frames or ffmpeg options) is allowed here.
    """
    pacing_style: str = Field(
        default="medium",
        description="The rhythm of editing cuts. Allowed values: fast, medium, slow, slow_to_fast, fast_to_slow."
    )
    emotion_curve: str = Field(
        default="steady",
        description="The emotional flow across the video timeline. Allowed values: steady, dramatic, peak_at_end, calm, dynamic."
    )
    scenery_policy: str = Field(
        default="medium",
        description="How environmental/scenery clips should be utilized. Allowed values: establishing_only, high_coverage, low_coverage, medium."
    )
    reaction_policy: str = Field(
        default="standard",
        description="Handling of character reaction shots. Allowed values: emphasized, standard, minimized."
    )
    breathing_policy: str = Field(
        default="standard",
        description="Handling of silent/context gaps between beats. Allowed values: loose, tight, standard."
    )
    transition_style: str = Field(
        default="standard",
        description="Visual transition styles. Allowed values: jumpcut, crossfade, standard."
    )
    narrative_priority: str = Field(
        default="dialogue",
        description="Core focus of narrative flow. Allowed values: dialogue, action, emotion, scenery."
    )
