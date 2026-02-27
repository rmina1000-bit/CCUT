from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from ccut_core.archive.aoid import create_aoid


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def handle_upload(file_path: Path, storage_root: Path) -> dict[str, str]:
    aoid = create_aoid()
    archive_dir = storage_root / "archive" / aoid
    decision_dir = storage_root / "decisions" / aoid
    draft_dir = storage_root / "drafts" / aoid

    archive_dir.mkdir(parents=True, exist_ok=False)
    decision_dir.mkdir(parents=True, exist_ok=False)
    draft_dir.mkdir(parents=True, exist_ok=False)

    target_file = archive_dir / file_path.name
    shutil.copy2(file_path, target_file)
    source_hash = _sha256_file(target_file)

    (archive_dir / "metadata.json").write_text(
        '{\n  "aoid": "%s",\n  "source_video_hash": "%s"\n}\n' % (aoid, source_hash),
        encoding="utf-8",
    )
    (draft_dir / "draft_v1.json").write_text('{"segments": []}\n', encoding="utf-8")
    (decision_dir / "decision_log.json").write_text("[]", encoding="utf-8")

    return {"aoid": aoid, "source_video_hash": source_hash}
