# Radar AEMET

Base de una aplicación web personal para visualizar productos de radar de AEMET. El
repositorio sigue el desarrollo incremental definido en
[`docs/ROADMAP.md`](docs/ROADMAP.md); la fuente principal de verdad es
[`docs/SPEC.md`](docs/SPEC.md).

La Fase 7 añade la composición nacional de Península y Baleares como producto
independiente a los 15 radares regionales. El selector ajusta automáticamente
mapa, cobertura, estado y timeline. Los productos temporalmente sin datos
permanecen visibles y se siguen consultando, sin mezclar ni reutilizar imágenes
de otra fuente.

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
make fetch-once    # composición nacional y 15 radares; carga .env
make check-inventory # comprueba códigos sin descargar sus GIF
make poll-once     # ciclo completo: ingesta, retención y publicación
make run-worker    # scheduler continuo
make rebuild-manifests # reconstruye la publicación solo desde disco
make serve-files   # inspección local en http://127.0.0.1:8000
make analyze-reflectivity SAMPLE=ruta/original.gif # depuración completa de Murcia
make validate-radar PRODUCT=regional-am SAMPLE=ruta/original.gif
make validate-national SAMPLE=ruta/original.png
make georeference-murcia OVERLAY=ruta/overlay.png # salida Web Mercator
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
aemet-radar georeference-murcia ruta/al/overlay.png
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

La fuente regional primaria es la cronología PPI pública del visor oficial de
AEMET: entrega 24 PNG con hora de producto y límites geográficos. OpenData
permanece como fallback y requiere `AEMET_API_KEY`.

La composición nacional usa la cronología pública `compo/PB` del mismo visor:
24 PNG indexados en EPSG:3857, cada 10 minutos, para Península y Baleares.
Canarias se representa mediante el radar regional de Las Palmas. La máscara
nacional se calcula por fotograma conservando solo los once RGB exactos de
reflectividad, ya que la huella de cobertura puede cambiar.

Los originales se guardan en
`data/raw/<producto>/<AAAA>/<MM>/<DD>/`: los PPI usan una clave de observación y
SHA-256 con extensión `.png`; el fallback conserva `.gif`. Cada imagen tiene un
informe JSON adyacente. Las URLs de AEMET y la API key no se almacenan. Repetir
la misma observación informa `duplicate`; dos horas oficiales distintas se
conservan aunque sus píxeles coincidan.

La publicación estática se genera en:

```text
data/radar/index.json
data/radar/<producto>/manifest.json
data/radar/<radar>/frames/<sha256>/overlay.png
data/status/health.json
```

El manifiesto conserva una ventana pública de 3 horas y 50 minutos anclada en el último
fotograma disponible, mientras el archivo mantiene inicialmente 24 horas. Cada
observación regional publicable incorpora un `imageUrl` y cuatro
`imageCoordinates` oficiales, generados una sola vez por hash. El PPI aporta
`productTime`; en el fallback solo se usa si existe evidencia y, en caso
contrario, se usa `retrievedAt` y se declara como
`timeSource: "retrievedAt"`. Los huecos se enumeran sin crear fotogramas
artificiales. La interfaz puede mantener visible el último fotograma real para
dar continuidad, pero conserva su hora original y marca el intervalo como
`Sin dato`. Con cadencia exacta de 10 minutos caben hasta 24 observaciones
contando ambos extremos.

El catálogo [`config/radars.yaml`](config/radars.yaml) declara los 15 endpoints,
emplazamientos, centros y estrategias. `validate-radar` comprueba una muestra
contra su perfil y genera previsualizaciones de reflectividad,
georreferenciación y límites. Los detalles y limitaciones están en
[`docs/PHASE_6.md`](docs/PHASE_6.md).

Para Murcia, `analyze-reflectivity` valida la plantilla `480×530`, recorta la
zona `480×480`, clasifica las once clases de la leyenda y aplica
`config/masks/regional-mu-v1.png`. Genera `normalized.png`, `crop.png`,
`palette.png`, `classified.png`, máscaras estática, de cobertura y alfa,
`overlay.png`, `preview.png` y `report.json` bajo `data/debug/`. El amarillo
compartido con las fronteras solo se conserva fuera de la máscara estática. La
metodología de extracción se documenta en
[`docs/PHASE_3.md`](docs/PHASE_3.md).

`georeference-murcia` valida
`config/georeferencing/regional-mu-v1.json`, transforma la rejilla azimutal
equidistante de 1 km a EPSG:3857, recorta el alcance nominal de 240 km y genera
`overlay-3857.png` más `georeferencing.json`. El remuestreo por vecino más
próximo no crea colores intermedios. El ciclo y `rebuild-manifests` encadenan
automáticamente ambos procesadores para cada hash nuevo regional.

La muestra real versionada del frontend publica 16 manifiestos bajo
`apps/web/public/radar/`: la composición nacional y trece radares reproducen
PNG del visor, Las Palmas conserva un GIF de fallback y Valencia permanece sin
datos. Los productos disponibles incluyen hasta 24 observaciones; Málaga
refleja honestamente los huecos de AEMET. Puede verse con `make dev-web`. La
calibración se documenta en [`docs/PHASE_4.md`](docs/PHASE_4.md) y la
reproducción en [`docs/PHASE_5.md`](docs/PHASE_5.md). El contrato nacional,
su máscara y su cobertura están en [`docs/PHASE_7.md`](docs/PHASE_7.md).

## Estrategia Git

`main` debe permanecer estable. Cada fase se desarrolla en una rama
`phase/<numero>-<descripcion>`, se valida con `make check` y se integra mediante
una revisión que confirme los criterios de aceptación. Los commits deben ser
pequeños, coherentes y no mezclar trabajo de fases posteriores.

Las decisiones que cambien arquitectura, alcance o comportamiento se registran
como ADR en `docs/DECISIONS.md`; no se reescribe la historia de decisiones.

No debe añadirse una coordenada, radar, proyección o cadencia a producción solo
porque parezca razonable: debe verificarse y documentarse.
