from __future__ import annotations

import unittest

from cinepulse.render_job import (
    InvalidJobTransition,
    ManifestError,
    RenderJobManifest,
    UnsupportedManifestSchema,
)


class RenderJobManifestTests(unittest.TestCase):
    def test_round_trip_is_deterministic(self) -> None:
        manifest = RenderJobManifest.new("job-1", source={"path_hint": "source.mp4"}, now=10.0)
        manifest = manifest.transition("preflight", now=11.0)
        manifest = manifest.with_render_plan("abc123", now=12.0)
        restored = RenderJobManifest.from_dict(manifest.to_dict())
        self.assertEqual(manifest, restored)
        self.assertEqual(2, restored.revision)
        self.assertEqual("abc123", restored.render_plan["fingerprint"])

    def test_future_schema_is_rejected(self) -> None:
        payload = RenderJobManifest.new("job-1", now=1.0).to_dict()
        payload["schema"] = 999
        with self.assertRaises(UnsupportedManifestSchema):
            RenderJobManifest.from_dict(payload)

    def test_invalid_transition_does_not_create_new_revision(self) -> None:
        manifest = RenderJobManifest.new("job-1", now=1.0)
        with self.assertRaises(InvalidJobTransition):
            manifest.transition("complete", now=2.0)
        self.assertEqual(0, manifest.revision)
        self.assertEqual("queued", manifest.state)

    def test_valid_lifecycle_reaches_complete(self) -> None:
        manifest = RenderJobManifest.new("job-1", now=1.0)
        manifest = manifest.transition("preflight", now=2.0)
        manifest = manifest.transition("running", now=3.0)
        manifest = manifest.transition("verifying", now=4.0)
        manifest = manifest.transition("complete", now=5.0)
        self.assertEqual("complete", manifest.state)
        self.assertEqual(4, manifest.revision)

    def test_phase_progress_rejects_overcommit(self) -> None:
        manifest = RenderJobManifest.new("job-1", now=1.0)
        with self.assertRaises(ManifestError):
            manifest.with_phase_progress(name="rife", units_total=10, units_committed=11)

    def test_error_is_structured_and_revisioned(self) -> None:
        manifest = RenderJobManifest.new("job-1", now=1.0)
        updated = manifest.with_error(code="RIFE-FAILED", message="boom", retryable=True, now=2.0)
        self.assertEqual(1, updated.revision)
        self.assertEqual("RIFE-FAILED", updated.last_error["code"])
        self.assertTrue(updated.last_error["retryable"])


if __name__ == "__main__":
    unittest.main()
