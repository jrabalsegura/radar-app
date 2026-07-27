from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest
from PIL import Image, ImageChops

from aemet_radar.errors import ReflectivityProcessingError
from aemet_radar.reflectivity import (
    REVIEWED_DRY_MASK_ALGORITHM,
    build_reviewed_dry_static_mask,
    build_static_mask,
    load_reflectivity_config,
    process_reflectivity_sample,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).parent / "fixtures" / "reflectivity"
PRODUCTION_CONFIG = REPOSITORY_ROOT / "config" / "palettes" / "regional-mu-v1.json"
PRODUCTION_MASK = REPOSITORY_ROOT / "config" / "masks" / "regional-mu-v1.png"
PRODUCTION_MASK_REPORT = REPOSITORY_ROOT / "config" / "masks" / "regional-mu-v1.json"
REGIONAL_MASK_COUNTS = {
    "regional-am": 2_436,
    "regional-sa": 4_431,
    "regional-pm": 1_740,
    "regional-ba": 3_677,
    "regional-cc": 3_996,
    "regional-ma": 6_112,
    "regional-mu": 3_611,
    "regional-vd": 6_715,
    "regional-ca": 1_083,
    "regional-se": 3_400,
    "regional-za": 5_705,
}


def test_small_golden_overlay_and_mask_are_deterministic(tmp_path: Path) -> None:
    first = process_reflectivity_sample(
        FIXTURES / "source.gif",
        config_path=FIXTURES / "config.json",
        static_mask_path=FIXTURES / "static-mask.png",
        output_dir=tmp_path / "first",
    )
    second = process_reflectivity_sample(
        FIXTURES / "source.gif",
        config_path=FIXTURES / "config.json",
        static_mask_path=FIXTURES / "static-mask.png",
        output_dir=tmp_path / "second",
    )

    _assert_same_image(first.output_dir / "overlay.png", FIXTURES / "expected-overlay.png")
    _assert_same_image(first.output_dir / "mask.png", FIXTURES / "expected-mask.png")
    assert (first.output_dir / "overlay.png").read_bytes() == (
        second.output_dir / "overlay.png"
    ).read_bytes()
    assert first.report_path.read_bytes() == second.report_path.read_bytes()
    statistics = dict(cast(dict[str, object], first.report["statistics"]))
    classes = statistics.pop("classes")
    assert statistics == {
        "sourcePixels": 30,
        "croppedPixels": 24,
        "classifiedPixelsBeforeStaticMask": 19,
        "reflectivityPixels": 15,
        "discardedByStaticMask": 3,
        "discardedOutsideCoverage": 1,
        "discardedByAmbiguousPolicy": 0,
        "unclassifiedPixels": 5,
        "transparentPixels": 9,
    }
    assert isinstance(classes, list)
    ambiguities = cast(dict[str, object], first.report["ambiguities"])
    yellow_payload = cast(dict[str, object], ambiguities["yellow"])
    yellow = cast(dict[str, object], yellow_payload["result"])
    assert yellow["classifiedPixels"] == 4
    assert yellow["keptPixels"] == 2
    assert yellow["discardedByStaticMask"] == 2
    outputs = cast(dict[str, object], first.report["outputs"])
    assert set(outputs) == {
        "normalized",
        "crop",
        "palette",
        "classified",
        "staticMask",
        "coverageMask",
        "mask",
        "overlay",
        "preview",
    }


def test_static_mask_generation_is_order_independent(tmp_path: Path) -> None:
    sample_paths = [
        _write_mask_sample(tmp_path / "one.gif", (10, 10, 8, 0, 0, 0)),
        _write_mask_sample(tmp_path / "two.gif", (10, 16, 8, 0, 0, 0)),
        _write_mask_sample(tmp_path / "three.gif", (10, 23, 8, 0, 0, 0)),
    ]

    first = build_static_mask(
        sample_paths,
        config_path=FIXTURES / "config.json",
        mask_path=tmp_path / "first.png",
    )
    second = build_static_mask(
        tuple(reversed(sample_paths)),
        config_path=FIXTURES / "config.json",
        mask_path=tmp_path / "second.png",
    )

    assert (tmp_path / "first.png").read_bytes() == (tmp_path / "second.png").read_bytes()
    assert first.report["sourceHashes"] == second.report["sourceHashes"]
    with Image.open(first.mask_path) as mask:
        data = mask.tobytes()
    assert data[0] == 0
    assert data[1] == 255
    assert data[2] == 255
    assert data.count(0) == 1
    assert first.report["excludedPixels"] == 1
    excluded_by_class = cast(list[dict[str, object]], first.report["excludedByClass"])
    assert [item["paletteIndex"] for item in excluded_by_class] == [10]


def test_static_mask_never_excludes_invariant_unambiguous_echoes(tmp_path: Path) -> None:
    samples = [
        _write_mask_sample(tmp_path / "one.gif", (8, 10, 0, 0, 0, 0)),
        _write_mask_sample(tmp_path / "two.gif", (8, 16, 0, 0, 0, 0)),
        _write_mask_sample(tmp_path / "three.gif", (8, 23, 0, 0, 0, 0)),
    ]

    result = build_static_mask(
        samples,
        config_path=FIXTURES / "config.json",
        mask_path=tmp_path / "mask.png",
    )

    with Image.open(result.mask_path) as mask:
        assert mask.tobytes().count(0) == 0
    assert result.report["excludedByClass"] == []


def test_static_mask_requires_three_distinct_samples(tmp_path: Path) -> None:
    first = _write_mask_sample(tmp_path / "one.gif", (10, 10, 8, 0, 0, 0))
    second = _write_mask_sample(tmp_path / "two.gif", (10, 16, 8, 0, 0, 0))

    with pytest.raises(ReflectivityProcessingError) as captured:
        build_static_mask(
            [first, second, first],
            config_path=FIXTURES / "config.json",
            mask_path=tmp_path / "mask.png",
        )

    assert captured.value.safe_details() == {"distinctSamples": 2}


def test_reviewed_dry_mask_requires_blank_official_reference(tmp_path: Path) -> None:
    dry_reference = tmp_path / "dry.png"
    image = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    image.putpixel((1, 1), (239, 242, 249, 179))
    image.save(dry_reference)

    result = build_reviewed_dry_static_mask(
        FIXTURES / "source.gif",
        dry_reference_path=dry_reference,
        dry_reference_url=(
            "https://www.aemet.es/es/api-eltiempo/radar/imagen-radar/PPI/"
            "AHR260726105000.PPI.Z_005_240.png"
        ),
        observed_at="2026-07-26T10:50:00Z",
        config_path=FIXTURES / "config.json",
        mask_path=tmp_path / "mask.png",
        product_id="regional-mu",
        expected_site_code="AHR",
    )

    with Image.open(result.mask_path) as mask:
        assert mask.mode == "L"
        assert set(mask.tobytes()) == {0, 255}
        assert mask.tobytes().count(0) == result.report["excludedPixels"]
    assert result.report["algorithm"] == REVIEWED_DRY_MASK_ALGORITHM
    assert result.report["distinctSamples"] == 1
    dry_report = cast(dict[str, object], result.report["dryReference"])
    assert dry_report["visibleColor"] == [239, 242, 249, 179]
    assert dry_report["visiblePixels"] == 1
    assert dry_report["transparentPixels"] == 15


def test_reviewed_dry_mask_rejects_reference_with_echoes(tmp_path: Path) -> None:
    dry_reference = tmp_path / "echoes.png"
    image = Image.new("RGBA", (4, 4), (239, 242, 249, 179))
    image.putpixel((1, 1), (0, 0, 252, 255))
    image.save(dry_reference)

    with pytest.raises(ReflectivityProcessingError) as captured:
        build_reviewed_dry_static_mask(
            FIXTURES / "source.gif",
            dry_reference_path=dry_reference,
            dry_reference_url=(
                "https://www.aemet.es/es/api-eltiempo/radar/imagen-radar/PPI/"
                "CCD260727071000.PPI.Z_005_240.png"
            ),
            observed_at="2026-07-27T07:10:00Z",
            config_path=FIXTURES / "config.json",
            mask_path=tmp_path / "mask.png",
            product_id="regional-mu",
            expected_site_code="CCD",
        )

    assert captured.value.safe_details() == {
        "transparentPixels": 0,
        "visibleColors": 2,
    }


def test_reviewed_dry_mask_rejects_mismatched_site_or_time(tmp_path: Path) -> None:
    dry_reference = tmp_path / "dry.png"
    image = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    image.putpixel((1, 1), (239, 242, 249, 179))
    image.save(dry_reference)

    with pytest.raises(
        ReflectivityProcessingError,
        match="misma hora",
    ):
        build_reviewed_dry_static_mask(
            FIXTURES / "source.gif",
            dry_reference_path=dry_reference,
            dry_reference_url=(
                "https://www.aemet.es/es/api-eltiempo/radar/imagen-radar/PPI/"
                "AHR260726105000.PPI.Z_005_240.png"
            ),
            observed_at="2026-07-26T11:00:00Z",
            config_path=FIXTURES / "config.json",
            mask_path=tmp_path / "mask.png",
            product_id="regional-mu",
            expected_site_code="AHR",
        )


def test_palette_mismatch_fails_instead_of_silent_classification(tmp_path: Path) -> None:
    with Image.open(FIXTURES / "source.gif") as template:
        source = template.copy()
        palette = source.getpalette()
        assert palette is not None
        palette[16 * 3 : 16 * 3 + 3] = [1, 2, 3]
        source.putpalette(palette)
    bad_path = tmp_path / "bad.gif"
    source.save(bad_path, format="GIF", optimize=False)

    with pytest.raises(ReflectivityProcessingError) as captured:
        process_reflectivity_sample(
            bad_path,
            config_path=FIXTURES / "config.json",
            static_mask_path=FIXTURES / "static-mask.png",
            output_dir=tmp_path / "output",
        )

    assert captured.value.safe_details() == {
        "paletteIndex": 16,
        "expectedRgb": [0, 0, 252],
        "actualRgb": [1, 2, 3],
    }


def test_versioned_murcia_mask_matches_its_reproducibility_report() -> None:
    config = load_reflectivity_config(PRODUCTION_CONFIG)
    report = json.loads(PRODUCTION_MASK_REPORT.read_text(encoding="utf-8"))

    with Image.open(PRODUCTION_MASK) as mask:
        mask.load()
        assert mask.mode == "L"
        assert mask.size == (config.crop.width, config.crop.height)
        assert mask.tobytes().count(0) == 3_611

    digest = hashlib.sha256(PRODUCTION_MASK.read_bytes()).hexdigest()
    config_digest = hashlib.sha256(PRODUCTION_CONFIG.read_bytes()).hexdigest()
    assert report["maskSha256"] == f"sha256:{digest}"
    assert report["configurationSha256"] == f"sha256:{config_digest}"
    assert report["coverage"] == {
        "shape": "circle",
        "centerX": 240,
        "centerY": 240,
        "radius": 250,
    }
    assert report["distinctSamples"] == 20
    assert report["excludedPixels"] == 3_611
    assert len(report["sourceHashes"]) == 20
    assert report["excludedByClass"] == [
        {
            "ambiguous": True,
            "legendDbz": 48,
            "name": "dbz-48-yellow",
            "paletteIndex": 10,
            "pixels": 3_611,
            "rgb": [255, 255, 0],
        }
    ]


@pytest.mark.parametrize(("product_id", "excluded_pixels"), REGIONAL_MASK_COUNTS.items())
def test_versioned_regional_mask_matches_its_v2_report(
    product_id: str,
    excluded_pixels: int,
) -> None:
    mask_path = REPOSITORY_ROOT / "config" / "masks" / f"{product_id}-v1.png"
    report_path = mask_path.with_suffix(".json")
    report = json.loads(report_path.read_text(encoding="utf-8"))

    with Image.open(mask_path) as mask:
        mask.load()
        assert mask.mode == "L"
        assert mask.size == (480, 480)
        assert set(mask.tobytes()) == {0, 255}
        assert mask.tobytes().count(0) == excluded_pixels

    digest = hashlib.sha256(mask_path.read_bytes()).hexdigest()
    assert report["productId"] == product_id
    assert report["algorithm"] == "ambiguous-temporal-invariance-v2"
    assert report["maskSha256"] == f"sha256:{digest}"
    assert report["distinctSamples"] >= 3
    assert report["observationWindowHours"] >= 2
    assert len(report["sourceEvidence"]) == report["distinctSamples"]
    assert report["excludedPixels"] == excluded_pixels
    assert [item["paletteIndex"] for item in report["excludedByClass"]] == [10]


def test_versioned_malaga_mask_matches_reviewed_dry_reference() -> None:
    mask_path = REPOSITORY_ROOT / "config" / "masks" / "regional-ml-v1.png"
    report_path = mask_path.with_suffix(".json")
    reference_path = (
        REPOSITORY_ROOT
        / "docs"
        / "evidence"
        / "phase-6"
        / "official-viewer"
        / "AHR260726105000.PPI.Z_005_240.png"
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))

    with Image.open(mask_path) as mask:
        mask.load()
        assert mask.mode == "L"
        assert mask.size == (480, 480)
        assert set(mask.tobytes()) == {0, 255}
        assert mask.tobytes().count(0) == 3_207

    mask_digest = hashlib.sha256(mask_path.read_bytes()).hexdigest()
    reference_digest = hashlib.sha256(reference_path.read_bytes()).hexdigest()
    dry_reference = cast(dict[str, object], report["dryReference"])
    assert report["algorithm"] == REVIEWED_DRY_MASK_ALGORITHM
    assert report["maskSha256"] == f"sha256:{mask_digest}"
    assert report["distinctSamples"] == 1
    assert report["excludedPixels"] == 3_207
    assert dry_reference["sha256"] == f"sha256:{reference_digest}"
    assert dry_reference["visibleColor"] == [239, 242, 249, 179]
    assert dry_reference["observedAt"] == "2026-07-26T10:50:00Z"


def _write_mask_sample(path: Path, first_row: tuple[int, ...]) -> Path:
    with Image.open(FIXTURES / "source.gif") as template:
        image = template.copy()
    image.putdata((*first_row, *([0] * 24)))
    image.save(path, format="GIF", optimize=False)
    return path


def _assert_same_image(actual_path: Path, expected_path: Path) -> None:
    with Image.open(actual_path) as actual, Image.open(expected_path) as expected:
        actual.load()
        expected.load()
        assert actual.mode == expected.mode
        assert actual.size == expected.size
        assert ImageChops.difference(actual, expected).getbbox() is None
