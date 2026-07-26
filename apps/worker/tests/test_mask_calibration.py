from __future__ import annotations

import json
from pathlib import Path

from aemet_radar.mask_calibration import discover_mask_samples


def test_mask_sample_inventory_deduplicates_and_measures_span(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first = _write_sample(
        first_root,
        "regional-am",
        "one",
        b"first",
        "2026-07-26T18:00:00Z",
    )
    _write_sample(
        second_root,
        "regional-am",
        "duplicate",
        first.read_bytes(),
        "2026-07-26T18:05:00Z",
    )
    _write_sample(
        second_root,
        "regional-am",
        "two",
        b"second",
        "2026-07-26T20:30:00Z",
    )

    inventory = discover_mask_samples("regional-am", (first_root, second_root))

    assert len(inventory.samples) == 2
    assert inventory.span_hours == 2.5
    assert sorted(inventory.source_evidence.values()) == [
        "2026-07-26T18:00:00Z",
        "2026-07-26T20:30:00Z",
    ]


def test_mask_sample_inventory_requires_dates_for_span(tmp_path: Path) -> None:
    root = tmp_path / "samples"
    _write_sample(root, "regional-am", "one", b"first", None)
    _write_sample(root, "regional-am", "two", b"second", "2026-07-26T20:30:00Z")

    inventory = discover_mask_samples("regional-am", (root,))

    assert inventory.span_hours is None
    assert len(inventory.source_evidence) == 1


def _write_sample(
    root: Path,
    product_id: str,
    name: str,
    content: bytes,
    retrieved_at: str | None,
) -> Path:
    path = root / "raw" / product_id / "2026" / "07" / "26" / f"{name}.gif"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    report: dict[str, object] = {}
    if retrieved_at is not None:
        report["retrievedAt"] = retrieved_at
    path.with_suffix(".json").write_text(json.dumps(report), encoding="utf-8")
    return path
