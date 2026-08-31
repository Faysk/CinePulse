from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from cinepulse.media_stage_adapter import MediaStageAdapter, MediaUnitContract
from cinepulse.stage_checkpoint import StageCheckpointStore


def require(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"required tool missing: {name}")
    return path


def main() -> int:
    ffmpeg = require("ffmpeg")
    ffprobe = require("ffprobe")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "source.mkv"
        command = [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=2",
            "-an", "-c:v", "ffv1", "-pix_fmt", "yuv420p", "-frames:v", "60", str(source),
        ]
        if subprocess.run(command, check=False).returncode:
            raise RuntimeError("failed to create recovery media fixture")

        checkpoint = StageCheckpointStore(
            root / "checkpoint.json",
            job_id="integration-job",
            attempt_id="attempt-1",
            stage="rife",
            policy_fingerprint="integration-v1",
        )
        crashed = {"done": False}
        produced = {"count": 0}

        def fault(point: str, _unit: str) -> None:
            if point == "after_promote" and not crashed["done"]:
                crashed["done"] = True
                raise RuntimeError("injected after promote")

        def producer(partial: Path) -> None:
            produced["count"] += 1
            result = subprocess.run(
                [
                    ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
                    "-map", "0:v:0", "-an", "-c:v", "ffv1", "-pix_fmt", "yuv420p",
                    "-frames:v", "60", "-f", "matroska", str(partial),
                ],
                check=False,
            )
            if result.returncode:
                raise RuntimeError("fixture producer failed")

        final = root / "segment_00001.mkv"
        contract = MediaUnitContract(
            width=320,
            height=180,
            fps=30.0,
            codec="ffv1",
            pix_fmt="yuv420p",
            exact_frames=60,
        )
        adapter = MediaStageAdapter(checkpoint, ffprobe=ffprobe, fault_hook=fault)
        try:
            adapter.execute_media_unit(
                unit_id="segment-1", ordinal=1, final=final, producer=producer, contract=contract,
            )
        except RuntimeError as exc:
            if "injected after promote" not in str(exc):
                raise
        if not final.is_file():
            raise RuntimeError("promoted media was lost after injected crash")
        resumed = MediaStageAdapter(checkpoint, ffprobe=ffprobe)
        resumed.execute_media_unit(
            unit_id="segment-1", ordinal=1, final=final, producer=producer, contract=contract,
        )
        if produced["count"] != 1:
            raise RuntimeError(f"resume reproduced committed media: producer calls={produced['count']}")
        if checkpoint.committed_count() != 1:
            raise RuntimeError("checkpoint did not reconcile promoted media")
        print("RECOVERY_MEDIA_INTEGRATION_OK producer_calls=1 committed=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
