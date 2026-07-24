import hashlib
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from aemet_radar.errors import DownloadValidationError
from aemet_radar.inspection import inspect_gif, resolve_product_time


def test_inspects_palette_and_internal_metadata(
    make_synthetic_gif: Callable[[bytes], bytes],
) -> None:
    report = inspect_gif(
        make_synthetic_gif(b"sanitized fixture"),
        "image/gif; charset=binary",
    )

    assert report.actual_mime_type == "image/gif"
    assert (report.width, report.height) == (3, 2)
    assert report.mode == "P"
    assert report.used_palette_indexes == (0, 1, 2)
    assert len(report.palette_entries) >= 4
    assert report.internal_metadata["comment"] == "sanitized fixture"


@pytest.mark.parametrize("content", [b"", b"not-a-gif", b"<html>error</html>"])
def test_rejects_invalid_content(content: bytes) -> None:
    with pytest.raises(DownloadValidationError) as captured:
        inspect_gif(content, "text/html")

    assert captured.value.safe_details() == {
        "sizeBytes": len(content),
        "sha256": f"sha256:{hashlib.sha256(content).hexdigest()}",
        "declaredContentType": "text/html",
    }


def test_last_modified_has_priority_as_product_time_candidate() -> None:
    retrieved_at = datetime(2026, 7, 23, 12, 37, tzinfo=UTC)

    result = resolve_product_time(
        headers={"last-modified": "Thu, 23 Jul 2026 12:30:00 GMT"},
        internal_metadata={"comment": "20260723T122000Z"},
        resource_name="20260723T121000Z.gif",
        retrieved_at=retrieved_at,
        cadence_minutes=10,
    )

    assert result.status == "candidate"
    assert result.source == "http:last-modified"
    assert result.value == "2026-07-23T12:30:00Z"


def test_product_time_remains_unresolved_without_evidence() -> None:
    retrieved_at = datetime(2026, 7, 23, 12, 37, tzinfo=UTC)

    result = resolve_product_time(
        headers={},
        internal_metadata={"comment": "no timestamp here"},
        resource_name="ephemeral-hash",
        retrieved_at=retrieved_at,
        cadence_minutes=10,
    )

    assert result.status == "unresolved"
    assert result.value is None
    assert result.evidence[-1]["source"] == "retrieval"
