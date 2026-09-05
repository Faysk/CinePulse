from pathlib import Path

path = Path("tests/test_restoration_temporal_export.py")
text = path.read_text(encoding="utf-8")
old = '''        expected_frames = (2 * policy.radius + 1) + 1
        self.assertEqual(
            geometry.estimated_temporal_working_set(policy),
            geometry.frame_bytes * expected_frames,
        )
'''
new = '''        expected_frames = (2 * policy.radius + 1) + 3
        self.assertEqual(
            geometry.estimated_temporal_working_set(policy),
            geometry.frame_bytes * expected_frames,
        )
'''
if text.count(old) != 1:
    raise SystemExit(f"temporal working-set test anchor mismatch: {text.count(old)}")
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8", newline="\n")
