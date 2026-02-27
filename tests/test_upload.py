from pathlib import Path

from ccut_core.ingestion.upload_handler import handle_upload


def test_handle_upload_creates_expected_artifacts(tmp_path: Path):
    src = tmp_path / "video.mp4"
    src.write_bytes(b"fake video")

    storage = tmp_path / "storage"
    result = handle_upload(src, storage)
    aoid = result["aoid"]

    assert (storage / "archive" / aoid / "video.mp4").exists()
    assert (storage / "archive" / aoid / "metadata.json").exists()
    assert (storage / "drafts" / aoid / "draft_v1.json").exists()
    assert (storage / "decisions" / aoid / "decision_log.json").exists()
