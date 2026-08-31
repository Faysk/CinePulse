"""Fast structural quality checks for the short FFV1 Matroska segments.

The recovery job stores every frame as an intra-coded FFV1 packet.  Reading the
EBML block sizes lets us detect the deterministic all-black failure produced by
the old 8K RIFE invocation without decoding hundreds of gigabytes of pixels.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


# FFmpeg FFV1 level 3, yuv420p, 7680x4320 encodes a limited-range solid-black
# frame to this exact packet size.  The value was cross-checked against decoded
# signalstats before it became a recovery gate.
SOLID_BLACK_PACKET_SIZE_8K_YUV420P_FFV1 = 511_495

_MASTER_ELEMENT_IDS = {
    0x1A45DFA3,  # EBML
    0x18538067,  # Segment
    0x114D9B74,  # SeekHead
    0x1549A966,  # Info
    0x1654AE6B,  # Tracks
    0xAE,        # TrackEntry
    0xE0,        # Video
    0xE1,        # Audio
    0x1F43B675,  # Cluster
    0x1C53BB6B,  # Cues
    0xBB,        # CuePoint
    0xB7,        # CueTrackPositions
    0x1941A469,  # Attachments
    0x1043A770,  # Chapters
    0x45B9,      # EditionEntry
    0x1254C367,  # Tags
    0x7373,      # Tag
    0x63C0,      # Targets
    0x67C8,      # SimpleTag
}


@dataclass(frozen=True)
class MatroskaSegmentQuality:
    packet_count: int
    solid_black_frames: int


def _read_vint(handle, *, keep_marker: bool = False) -> tuple[int | None, int | None]:
    byte = handle.read(1)
    if not byte:
        return None, None
    first = byte[0]
    mask = 0x80
    length = 1
    while length <= 8 and not (first & mask):
        mask >>= 1
        length += 1
    if length > 8:
        raise ValueError("Invalid EBML variable-length integer")
    value = first if keep_marker else first & (mask - 1)
    remaining = handle.read(length - 1)
    if len(remaining) != length - 1:
        raise EOFError("Truncated EBML variable-length integer")
    for item in remaining:
        value = (value << 8) | item
    if not keep_marker and value == (1 << (7 * length)) - 1:
        return value, None
    return value, length


def matroska_video_packet_sizes(path: Path) -> list[int]:
    """Return SimpleBlock/Block payload sizes while seeking over frame data."""

    sizes: list[int] = []
    with path.open("rb") as handle:
        file_end = os.fstat(handle.fileno()).st_size

        def walk(end: int) -> None:
            while handle.tell() < end:
                start = handle.tell()
                element_id, _id_length = _read_vint(handle, keep_marker=True)
                if element_id is None:
                    break
                size, size_length = _read_vint(handle)
                if size_length is None:
                    size = end - handle.tell()
                assert size is not None
                data_start = handle.tell()
                element_end = min(data_start + size, end)
                if element_id in _MASTER_ELEMENT_IDS:
                    walk(element_end)
                    handle.seek(element_end)
                elif element_id in (0xA3, 0xA1):  # SimpleBlock / Block
                    _track_number, track_length = _read_vint(handle)
                    if track_length is None:
                        raise ValueError(f"Invalid Matroska block track number in {path}")
                    # Track vint + signed 16-bit relative timecode + flags.
                    sizes.append(size - track_length - 3)
                    handle.seek(element_end)
                else:
                    handle.seek(element_end)
                if handle.tell() <= start:
                    raise RuntimeError(f"Matroska parser made no progress in {path}")

        walk(file_end)
    return sizes


def inspect_matroska_segment(path: Path) -> MatroskaSegmentQuality:
    sizes = matroska_video_packet_sizes(path)
    return MatroskaSegmentQuality(
        packet_count=len(sizes),
        solid_black_frames=sizes.count(SOLID_BLACK_PACKET_SIZE_8K_YUV420P_FFV1),
    )
