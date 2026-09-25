# Radar AEMET — guía para Claude Code

Visor personal de radar de AEMET en producción en <https://radar.joserabalsegura.com>.
Documentación, UI, mensajes de error y commits en **español**.

## Arquitectura

```text
AEMET (visor PPI/compo + OpenData fallback)
  -> worker Python (apps/worker)  escribe  data/raw, data/processed, data/radar, data/status
  -> nginx estático (apps/web + deploy/containers/nginx.conf)  sirve la SPA y data/ en solo lectura
```

- **Worker** (`aemet-radar run`): cada 5 min consulta 16 productos (nacional + 15
  regionales), archiva originales por hash, genera overlays georreferenciados y
  publica `radar/index.json`, `radar/<id>/manifest.json` y `status/health.json`.
  - `viewer_ingestion.py`: algoritmo común de ingesta de la cronología del visor;
    `hybrid_service.py` (regional PPI) y `national_service.py` (compo PB) solo
    aportan los detalles de cada fuente. `service.py` + `client.py` = OpenData.
  - `runner.py`: ciclo, reintentos, publicación, retención y health.
  - `timeline_processing.py` / `national_timeline_processing.py`: derivados
    publicables por fotograma. `reflectivity.py`, `georeferencing.py`: GIF de fallback.
  - `common.py`: helpers JSON/coordenadas compartidos; úsalo en vez de duplicar.
- **Web** (`apps/web`): React 19 + Vite + MapLibre. PWA con `public/sw.js`.
  `useRadarData.ts` carga catálogo/manifiestos con caché resiliente; `App.tsx`
  controla reproductor y opciones; `RadarMap.tsx` alterna dos capas imagen.
- `config/radars.yaml`: catálogo de radares (fuente de verdad de emplazamientos).
- `apps/web/public/radar` y `public/status`: muestra real versionada para
  desarrollo y tests (no se incluye en la imagen web).

## Comandos

```bash
make install            # npm ci + .venv con requirements-dev.lock
make check              # lint + formato + tipos + tests + build (antes de cada commit)
make format             # prettier + ruff format
.venv/bin/pytest apps/worker/tests/test_runner.py -q    # un test concreto
npm --prefix apps/web test -- src/App.test.tsx          # un test web concreto
make test-e2e           # Playwright (Chrome escritorio y móvil)
make dev-web            # Vite con la muestra de public/
make docker-test        # build + arranque + smoke test con Docker Desktop en :8080
make container-logs / container-status / container-down
```

`make docker-test` es la prueba local obligatoria antes de subir a GitHub: usa
las mismas imágenes y nginx que producción, con `./data` y `.env` locales.

## Reglas del proyecto

- `AEMET_API_KEY` solo existe en `.env` (local) o `/etc/aemet-radar/worker.env`
  (servidor). Nunca la leas, imprimas, pases por argumentos ni la comitees. El
  contenedor web no debe recibirla.
- No añadas coordenadas, radares, proyecciones ni cadencias sin evidencia
  verificable y documentada (ADR en `docs/DECISIONS.md`).
- La ventana pública es fija: 230 minutos (`temporal.HISTORY_MINUTES`).
- Las URLs de derivados son inmutables y versionadas. Si cambias el algoritmo de
  un procesador, cambia `REGIONAL_PROCESSING_REVISION` o
  `NATIONAL_PUBLICATION_REVISION`; si cambias la lógica de `sw.js`, cambia su `VERSION`.
- Escrituras en `data/` siempre con `storage.atomic_write_*`. Un solo worker
  escribe en `data/` a la vez.
- Nunca presentes una estimación como observación oficial ni generes
  fotogramas intermedios; los huecos se muestran como huecos.
- Python: mypy estricto, ruff (100 columnas). TypeScript estricto, prettier.
- Cambios de comportamiento con test. Tras refactors del worker, comprueba que
  `rebuild-manifests` produce la misma publicación sobre una copia de `data/`.

## Git y despliegue

- Ramas `claude/<descripcion>` desde `origin/main`; PR a `main`. La CI
  (Frontend, Worker, Container images) debe estar verde antes de integrar.
- Despliegue manual por `ssh remote` con Podman/Quadlet: sigue
  [docs/PRUEBAS_Y_DESPLIEGUE.md](docs/PRUEBAS_Y_DESPLIEGUE.md). No sobrescribas
  el virtual host de nginx modificado por Certbot en el servidor.
- `data/` y `.env` están excluidos de Git; no los añadas.
