# Radar AEMET

Base de una aplicación web personal para visualizar productos de radar de AEMET. El
repositorio sigue el desarrollo incremental definido en
[`docs/ROADMAP.md`](docs/ROADMAP.md); la fuente principal de verdad es
[`docs/SPEC.md`](docs/SPEC.md).

La Fase 3 incorpora el procesador versionado `regional-v1`, que extrae una capa
RGBA transparente del radar de Murcia mediante paleta exacta y máscara estática
reproducible. Todavía no georreferencia la capa ni la representa en un mapa.

## Requisitos

- Node.js 22.12 o posterior y npm 10 o posterior.
- Python 3.12 o posterior.
- GNU Make (opcional, pero recomendado para usar los comandos uniformes).

## Instalación reproducible

```bash
make install
```

El frontend se instala con `npm ci` y su `package-lock.json`. El entorno de
desarrollo Python se crea en `.venv`, usa las versiones exactas de
`apps/worker/requirements-dev.lock` e instala el worker como paquete local.

Sin Make, los comandos equivalentes son:

```bash
npm --prefix apps/web ci
python3 -m venv .venv
.venv/bin/python -m pip install --requirement apps/worker/requirements-dev.lock
.venv/bin/python -m pip install --force-reinstall --no-deps --no-build-isolation apps/worker
```

Para ejecutar una consulta real, crea un archivo local con permisos restringidos:

```bash
cp .env.example .env
chmod 600 .env
```

Edita `.env` y sustituye únicamente `AEMET_API_KEY`. No pegues la clave en
comandos, incidencias, commits ni conversaciones. `.env` está excluido de Git y
la CLI no sobrescribe una variable ya exportada.

## Desarrollo y validación

```bash
make dev-web       # servidor Vite local
make fetch-once    # una consulta de Murcia y nacional; carga .env
make check-inventory # comprueba códigos sin descargar sus GIF
make poll-once     # ciclo completo: ingesta, retención y publicación
make run-worker    # scheduler continuo
make rebuild-manifests # reconstruye la publicación solo desde disco
make serve-files   # inspección local en http://127.0.0.1:8000
make analyze-reflectivity SAMPLE=ruta/original.gif # depuración completa de Murcia
make check         # lint, formato, tipado, tests y build
make format        # aplica los formateadores
```

Para usar directamente `pytest`, `ruff` o la CLI en una terminal nueva:

```bash
source .venv/bin/activate
pytest
ruff check .
aemet-radar fetch-once --product regional-mu
aemet-radar run --cycles 1
aemet-radar rebuild-manifests
aemet-radar analyze-reflectivity ruta/al/original.gif
deactivate
```

Los criterios de aceptación también se pueden comprobar por separado:

```bash
npm --prefix apps/web test
npm --prefix apps/web run build
.venv/bin/pytest
.venv/bin/ruff check .
```

## Estructura

```text
apps/web/          frontend React + TypeScript + Vite
apps/worker/       paquete Python del worker
config/            configuración futura versionada
data/              datos locales ignorados por Git
deploy/            reservado para la Fase 9
docs/              especificación, decisiones y roadmap
samples/           muestras mínimas y documentadas
scripts/           utilidades reproducibles futuras
```

Los originales se guardan en
`data/raw/<producto>/<AAAA>/<MM>/<DD>/<sha256>.gif`; cada GIF tiene un informe
JSON adyacente. Las URLs efímeras de AEMET y la API key no se almacenan. Si el
hash ya existe para el producto, la ejecución informa `duplicate` y no crea otra
copia.

La publicación estática se genera en:

```text
data/radar/index.json
data/radar/<producto>/manifest.json
data/status/health.json
```

El manifiesto conserva solo la ventana pública de dos horas anclada en el
último fotograma disponible, mientras el archivo mantiene inicialmente 24
horas. `productTime` se usa únicamente si existe evidencia; en caso contrario
se usa `retrievedAt` y se declara como `timeSource: "retrievedAt"`. Los huecos
se enumeran sin crear fotogramas artificiales.

Para Murcia, `analyze-reflectivity` valida la plantilla `480×530`, recorta la
zona `480×480`, clasifica las once clases de la leyenda y aplica
`config/masks/regional-mu-v1.png`. Genera `normalized.png`, `crop.png`,
`palette.png`, `classified.png`, máscaras estática, de cobertura y alfa,
`overlay.png`, `preview.png` y `report.json` bajo `data/debug/`. El amarillo
compartido con las fronteras solo se conserva fuera de la máscara estática. La
metodología y la validación real se documentan en
[`docs/PHASE_3.md`](docs/PHASE_3.md).

## Estrategia Git

`main` debe permanecer estable. Cada fase se desarrolla en una rama
`phase/<numero>-<descripcion>`, se valida con `make check` y se integra mediante
una revisión que confirme los criterios de aceptación. Los commits deben ser
pequeños, coherentes y no mezclar trabajo de fases posteriores.

Las decisiones que cambien arquitectura, alcance o comportamiento se registran
como ADR en `docs/DECISIONS.md`; no se reescribe la historia de decisiones.

No debe añadirse una coordenada, radar, proyección o cadencia a producción solo
porque parezca razonable: debe verificarse y documentarse.
