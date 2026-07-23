"""Productos de radar incluidos en el spike y catálogo provisional oficial."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProductKind(StrEnum):
    REGIONAL = "regional"
    NATIONAL = "national"


@dataclass(frozen=True, slots=True)
class RadarProduct:
    id: str
    label: str
    kind: ProductKind
    endpoint: str
    cadence_minutes: int
    aemet_code: str | None = None


@dataclass(frozen=True, slots=True)
class RegionalRadar:
    code: str
    label: str


MURCIA = RadarProduct(
    id="regional-mu",
    label="Murcia",
    kind=ProductKind.REGIONAL,
    endpoint="/api/red/radar/regional/mu",
    cadence_minutes=10,
    aemet_code="mu",
)

NATIONAL = RadarProduct(
    id="national",
    label="Composición nacional",
    kind=ProductKind.NATIONAL,
    endpoint="/api/red/radar/nacional",
    cadence_minutes=30,
)

SPIKE_PRODUCTS: dict[str, RadarProduct] = {
    MURCIA.id: MURCIA,
    NATIONAL.id: NATIONAL,
}

# Catálogo publicado en AEMET_OpenData_specification.json. La disponibilidad
# observada se documenta por separado y no habilita radares.
PROVISIONAL_REGIONAL_RADARS: tuple[RegionalRadar, ...] = (
    RegionalRadar("am", "Almería"),
    RegionalRadar("sa", "Asturias"),
    RegionalRadar("pm", "Illes Balears"),
    RegionalRadar("ba", "Barcelona"),
    RegionalRadar("cc", "Cáceres"),
    RegionalRadar("co", "A Coruña"),
    RegionalRadar("ma", "Madrid"),
    RegionalRadar("ml", "Málaga"),
    RegionalRadar("mu", "Murcia"),
    RegionalRadar("vd", "Palencia"),
    RegionalRadar("ca", "Las Palmas"),
    RegionalRadar("se", "Sevilla"),
    RegionalRadar("va", "Valencia"),
    RegionalRadar("ss", "Vizcaya"),
    RegionalRadar("za", "Zaragoza"),
)

PROVISIONAL_REGIONAL_PRODUCTS: tuple[RadarProduct, ...] = tuple(
    RadarProduct(
        id=f"regional-{radar.code}",
        label=radar.label,
        kind=ProductKind.REGIONAL,
        endpoint=f"/api/red/radar/regional/{radar.code}",
        cadence_minutes=10,
        aemet_code=radar.code,
    )
    for radar in PROVISIONAL_REGIONAL_RADARS
)
