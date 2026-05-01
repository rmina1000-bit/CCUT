import uuid

class ExportEngine:
    """
    [STEP 7] Export Engine (v3.2.1)
    Proposal JSON을 기반으로 Render 가능한 Export Input 형식을 생성합니다.
    절대경로 노출을 배제하고 클립 순서와 타임스탬프를 정규화합니다.
    """
    def __init__(self, bams):
        self.bams = bams

    def create_export_input(self, proposal_id: str, custom_clips=None):
        # 1. Proposal 로드
        proposal = self.bams.get_single_proposal(proposal_id)
        # Fallback for client-side proposals (A/B)
        if not proposal and proposal_id in ["A", "B"]:
            proposal = {"source_id": "UNKNOWN", "mode": proposal_id, "sequence": []}

        if not proposal:
            print(f"[EXPORT] Proposal {proposal_id} not found.")
            return None

        source_id = proposal.get("source_id", "UNKNOWN")
        
        # 2. Clips 생성 (custom_clips 가 있으면 우선 사용)
        sequence = custom_clips if custom_clips is not None else proposal.get("sequence", [])
        clips = []
        total_dur = 0.0
        
        for i, frag in enumerate(sequence):
            # Semantic Fragment 구조에서 필수 필드 추출
            clip = {
                "fragment_id": frag.get("fragment_id"),
                "start": frag.get("start"),
                "end": frag.get("end"),
                "duration": frag.get("structural", {}).get("duration", 0),
                "order": i
            }
            clips.append(clip)
            total_dur += clip["duration"]

        # 3. Export Input 객체 구성
        export_data = {
            "export_id": f"EXP_{uuid.uuid4().hex[:6].upper()}_{source_id}",
            "source_id": source_id,
            "proposal_id": proposal_id,
            "mode": proposal["mode"],
            "clips": clips,
            "total_duration": round(total_dur, 2),
            "status": "EXPORT_INPUT_READY"
        }

        # 4. DB 저장
        self.bams.save_export_input(export_data)
        
        print(f"[EXPORT] Export Input {export_data['export_id']} generated from {proposal_id}")
        return export_data
