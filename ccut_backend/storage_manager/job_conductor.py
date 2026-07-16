"""[STORAGE-1 ST-2] Job Conductor 최소 골격.

상주 데몬 아님 — 순수 자료구조 + 함수. 프로세스가 뜨는 동안만 메모리에 존재.
janitor가 첫 등록 고객(dry-run 스캔을 job으로 등록해 진행상황/취소를 추적).
"""
import time
import uuid
from dataclasses import dataclass, field


class Stage:
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class Job:
    job_id: str
    kind: str
    stage: str = Stage.QUEUED
    heartbeat: float = field(default_factory=time.time)
    cancel_requested: bool = False
    result: dict = field(default_factory=dict)
    error: str = None
    created_at: float = field(default_factory=time.time)


class JobConductor:
    """인메모리 job 큐. 스레드/프로세스 상주 없음 — 호출자가 직접 tick/heartbeat 갱신."""

    def __init__(self):
        self._jobs: dict[str, Job] = {}

    def enqueue(self, kind: str) -> Job:
        job = Job(job_id=str(uuid.uuid4()), kind=kind)
        self._jobs[job.job_id] = job
        return job

    def heartbeat(self, job_id: str):
        job = self._jobs.get(job_id)
        if job is not None:
            job.heartbeat = time.time()

    def set_stage(self, job_id: str, stage: str):
        job = self._jobs.get(job_id)
        if job is not None:
            job.stage = stage
            job.heartbeat = time.time()

    def set_result(self, job_id: str, result: dict):
        job = self._jobs.get(job_id)
        if job is not None:
            job.result = result

    def set_error(self, job_id: str, error: str):
        job = self._jobs.get(job_id)
        if job is not None:
            job.stage = Stage.FAILED
            job.error = error
            job.heartbeat = time.time()

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job.cancel_requested = True
        return True

    def is_cancel_requested(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        return bool(job and job.cancel_requested)

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[Job]:
        return list(self._jobs.values())


# 모듈 레벨 공유 인스턴스(프로세스 수명 동안만 유효, 데몬 아님).
default_conductor = JobConductor()
