from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from cinepulse.matroska_quality import matroska_video_packet_sizes


def _size_vint(value: int) -> bytes:
    for length in range(1, 9):
        if value < (1 << (7 * length)) - 1:
            encoded = value | (1 << (7 * length))
            return encoded.to_bytes(length, "big")
    raise ValueError(value)


def _element(element_id: bytes, payload: bytes) -> bytes:
    return element_id + _size_vint(len(payload)) + payload


class MatroskaQualityTests(unittest.TestCase):
    def test_reads_block_payload_sizes_without_decoding(self) -> None:
        first_payload = b"a" * 17
        second_payload = b"b" * 31
        first_block = b"\x81\x00\x00\x80" + first_payload
        second_block = b"\x81\x00\x01\x80" + second_payload
        cluster = _element(b"\x1f\x43\xb6\x75", _element(b"\xa3", first_block) + _element(b"\xa3", second_block))
        segment = _element(b"\x18\x53\x80\x67", cluster)
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "sample.mkv"
            path.write_bytes(segment)
            self.assertEqual(matroska_video_packet_sizes(path), [17, 31])


if __name__ == "__main__":
    unittest.main()
