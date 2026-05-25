from abc import ABC, abstractmethod
from typing import Dict, Any, List

class BaseExternalVideoAdapter(ABC):
    """
    [Phase 2] External Video AI API Integration Contract Base
    All third-party video generation/edit adapters must implement this class.
    """
    
    @abstractmethod
    def __init__(self, api_key: str, base_url: str = None):
        self.api_key = api_key
        self.base_url = base_url

    @abstractmethod
    def generate_video_from_prompt(self, prompt: str, aspect_ratio: str = "16:9", duration: float = 4.0, **kwargs) -> Dict[str, Any]:
        """
        Generates a new video based on a text prompt.
        Returns a dictionary containing generation job information:
        {
            "job_id": str,
            "status": str,  # 'pending', 'processing', 'completed', 'failed'
            "output_url": str (optional),
            "raw_response": dict
        }
        """
        pass

    @abstractmethod
    def extend_video(self, video_url: str, prompt: str = None, duration: float = 4.0, **kwargs) -> Dict[str, Any]:
        """
        Extends an existing video clip.
        """
        pass

    @abstractmethod
    def check_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Queries the current status of a generation/edit job.
        """
        pass
