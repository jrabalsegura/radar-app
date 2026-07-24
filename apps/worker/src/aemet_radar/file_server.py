"""Servidor HTTP local y sin listado de directorios para inspeccionar la publicación."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from os import PathLike
from pathlib import Path


class NoDirectoryListingHandler(SimpleHTTPRequestHandler):
    """Sirve archivos conocidos pero no expone índices automáticos."""

    def list_directory(self, path: str | PathLike[str]) -> BytesIO | None:
        self.send_error(404, "No existe un índice para este directorio.")
        return None


def serve_files(data_dir: Path, *, host: str = "127.0.0.1", port: int = 8000) -> None:
    if not 0 <= port <= 65_535:
        raise ValueError("El puerto debe estar entre 0 y 65535.")
    root = data_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    handler = partial(NoDirectoryListingHandler, directory=str(root))
    server = ThreadingHTTPServer((host, port), handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()
