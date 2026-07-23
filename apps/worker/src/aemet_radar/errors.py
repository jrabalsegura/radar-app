"""Errores seguros para la ingesta de AEMET."""

from __future__ import annotations


class AemetRadarError(Exception):
    """Error esperado que se puede mostrar sin filtrar secretos."""

    code = "aemet_radar_error"


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


class AemetResponseError(AemetRadarError):
    """La respuesta de la pasarela de AEMET no cumple el contrato."""

    code = "response_error"


class DownloadValidationError(AemetRadarError):
    """El recurso descargado no es un GIF aceptable."""

    code = "download_validation_error"
