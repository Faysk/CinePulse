from __future__ import annotations

import argparse
import json
import re
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parent.parent


def _component(name: str, version: str, *, kind: str = "library", hashes: list[dict] | None = None, licenses: list[dict] | None = None, properties: list[dict] | None = None) -> dict:
    item = {"type": kind, "name": name, "version": str(version)}
    if hashes:
        item["hashes"] = hashes
    if licenses:
        item["licenses"] = licenses
    if properties:
        item["properties"] = properties
    return item


def build_sbom() -> dict:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    bootstrap = json.loads((ROOT / "installer" / "bootstrap-manifest.json").read_text(encoding="utf-8"))
    lock = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    numpy_match = re.search(r"numpy==([^\s\\]+)", lock)
    numpy_hash = re.search(r"sha256:([0-9a-f]{64})", lock)
    components: list[dict] = []
    if numpy_match:
        hashes = [{"alg": "SHA-256", "content": numpy_hash.group(1)}] if numpy_hash else None
        components.append(_component("numpy", numpy_match.group(1), hashes=hashes))
    components.append(_component("Python", bootstrap["python"]["version"], kind="application", properties=[{"name": "cinepulse:managed-runtime", "value": "true"}]))
    for key, label in (("uv", "uv"), ("ffmpeg", "FFmpeg"), ("real_esrgan", "Real-ESRGAN"), ("rife", "RIFE")):
        item = bootstrap[key]
        licenses = [{"license": {"id": item["license"]}}] if item.get("license") else None
        components.append(_component(label, item["version"], kind="application", hashes=[{"alg": "SHA-256", "content": item["sha256"]}], licenses=licenses))
    demucs = bootstrap["demucs"]
    components.extend([
        _component("Demucs", demucs["version"]),
        _component("PyTorch", demucs["torch_version"]),
        _component("torchaudio", demucs["torchaudio_version"]),
    ])
    for weight in demucs.get("weights", []):
        components.append(_component(f"Demucs weight {weight['file']}", demucs["version"], kind="file", hashes=[{"alg": "SHA-256", "content": weight["sha256"]}]))
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid5(NAMESPACE_URL, f'https://cinepulse.local/sbom/{project["version"]}')}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "component": {"type": "application", "name": project["name"], "version": project["version"]},
            "properties": [
                {"name": "cinepulse:scope", "value": "direct runtime, managed tools, model artifacts"},
                {"name": "cinepulse:transitive-demucs-lock", "value": "not-yet-complete"},
            ],
        },
        "components": components,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_sbom(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"CINEPULSE_SBOM_OK {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
