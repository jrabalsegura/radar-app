"""Errores seguros para la ingesta de AEMET."""

from __future__ import annotations


class AemetRadarError(Exception):
    """Error esperado que se puede mostrar sin filtrar secretos."""

    code = "aemet_radar_error"

    def safe_details(self) -> dict[str, object]:
        return {}


class ConfigurationError(AemetRadarError):
    """La configuración local no permite ejecutar el comando."""

    code = "configuration_error"


class AemetTransportError(AemetRadarError):
    """La conexión con AEMET no pudo completarse."""

    code = "transport_error"

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(f"No se pudo completar la petición de {stage}.")


class AemetHttpError(AemetRadarError):
    """AEMET respondió con un código HTTP no válido."""

    code = "http_error"

    def __init__(self, stage: str, status_code: int) -> None:
        self.stage = stage
        self.status_code = status_code
        super().__init__(f"AEMET respondió HTTP {status_code} durante {stage}.")


class AemetApiStatusError(AemetRadarError):
    """La pasarela respondió HTTP correctamente, pero declaró otro estado."""

    code = "api_status_error"

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"AEMET devolvió estado {status_code} en la respuesta inicial.")


def is_no_data_error(error: AemetRadarError) -> bool:
    """Indica que AEMET reconoce el producto, pero no tiene datos disponibles."""

    return isinstance(error, AemetApiStatusError) and error.status_code == 404


class AemetResponseError(AemetRadarError):
    """La respuesta de la pasarela de AEMET no cumple el contrato."""

    code = "response_error"


class DownloadValidationError(AemetRadarError):
    """El recurso descargado no es un GIF aceptable."""

    code = "download_validation_error"

    def __init__(
        self,
        message: str,
        *,
        size_bytes: int | None = None,
        sha256: str | None = None,
        declared_content_type: str | None = None,
    ) -> None:
        self.size_bytes = size_bytes
        self.sha256 = sha256
        self.declared_content_type = declared_content_type
        super().__init__(message)

    def safe_details(self) -> dict[str, object]:
        return {
            "sizeBytes": self.size_bytes,
            "sha256": f"sha256:{self.sha256}" if self.sha256 is not None else None,
            "declaredContentType": self.declared_content_type,
        }


class ReflectivityProcessingError(AemetRadarError):
    """La muestra o configuración no permite extraer reflectividad con seguridad."""

    code = "reflectivity_processing_error"

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        self.details = details or {}
        super().__init__(message)

    def safe_details(self) -> dict[str, object]:
        return self.details


class GeoreferencingError(AemetRadarError):
    """La capa o calibración no permite una georreferenciación segura."""

    code = "georeferencing_error"

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        self.details = details or {}
        super().__init__(message)

    def safe_details(self) -> dict[str, object]:
        return self.details
