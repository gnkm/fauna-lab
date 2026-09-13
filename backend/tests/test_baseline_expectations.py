"""Function-level baseline inference vs fixtures (VER-F-BASE-001 / REQ-F-BASE-010).

The HTTP inference API is F011. This module checks preprocessing + fold-in
against `baseline_expectations.json` using ONNX Runtime directly.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
import pytest
from faunalab.ml.baseline import inspect_baseline_assets
from faunalab.ml.fold import fold_logits
from faunalab.ml.preprocess import preprocess_image
from PIL import Image

REPO_ASSETS = Path(__file__).resolve().parents[2] / "assets"
CONFIDENCE_TOLERANCE = 0.02


@pytest.fixture(scope="module")
def baseline_session() -> tuple[ort.InferenceSession, dict[str, tuple[int, ...]]]:
    inspection = inspect_baseline_assets(REPO_ASSETS)
    assert inspection.ok
    assert inspection.model_path is not None
    assert inspection.class_map is not None
    session = ort.InferenceSession(
        str(inspection.model_path),
        providers=["CPUExecutionProvider"],
    )
    return session, inspection.class_map


def test_ver_f_base_001_expectations_match(
    baseline_session: tuple[ort.InferenceSession, dict[str, tuple[int, ...]]],
) -> None:
    session, class_map = baseline_session
    input_name = session.get_inputs()[0].name
    output_names = [item.name for item in session.get_outputs()]
    assert "logits" in output_names
    payload = json.loads(
        (REPO_ASSETS / "fixtures" / "baseline_expectations.json").read_text(
            encoding="utf-8"
        )
    )
    mismatches: list[str] = []
    for item in payload["items"]:
        path = REPO_ASSETS / "fixtures" / item["file"]
        with Image.open(path) as image:
            image.load()
            tensor = preprocess_image(image)[None, ...]
        raw_logits = session.run(["logits"], {input_name: tensor})[0]
        logits = np.asarray(raw_logits)[0]
        result = fold_logits(np.asarray(logits), class_map)
        top_ok = result.top_class_id == item["expected_top_class_id"]
        conf_ok = (
            abs(result.top_confidence - float(item["expected_top_confidence"]))
            <= CONFIDENCE_TOLERANCE
        )
        if not top_ok or not conf_ok:
            mismatches.append(
                f"{item['file']}: got {result.top_class_id} "
                f"{result.top_confidence:.4f}, expected "
                f"{item['expected_top_class_id']} "
                f"{item['expected_top_confidence']}"
            )
    assert mismatches == []
