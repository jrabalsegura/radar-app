# Radar AEMET

Base de una aplicación web personal para visualizar productos de radar de AEMET. El
repositorio sigue el desarrollo incremental definido en
[`docs/ROADMAP.md`](docs/ROADMAP.md); la fuente principal de verdad es
[`docs/SPEC.md`](docs/SPEC.md).

La Fase 9 completa el MVP con un despliegue reproducible y operable. El worker
Python y el frontend estático viven en contenedores separados sin privilegios,
comparten un volumen persistente con permisos restrictivos y tienen checks de
salud, logs acotados, backups y rollback. Docker Compose permite una prueba
prolongada en el Mac; producción usa Podman/Quadlet detrás de nginx y HTTPS en
`radar.joserabalsegura.com`.

El visor sigue siendo una PWA responsive e instalable: conserva el último
manifiesto válido, funciona tras perder la conexión, muestra siempre la
antigüedad del dato y ofrece pantalla completa, geolocalización local,
preferencias y accesibilidad. La composición nacional de Península y Baleares
y los 15 radares regionales son productos independientes.

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
make preview-live  # build de producción con los datos locales del worker
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
make test-e2e      # flujos principales en Chrome de escritorio y móvil
make container-up  # build y despliegue local en http://127.0.0.1:8080
make container-check # smoke test y comprobación de aislamiento de la key
make container-down # detiene contenedores sin borrar data/
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
npm --prefix apps/web run test:e2e
npm --prefix apps/web run build
.venv/bin/pytest
.venv/bin/ruff check .
```

### Prueba local como despliegue estático

Para probar el artefacto de producción con los datos reales de `data/`, primero
publica al menos un ciclo del worker y después usa el objetivo reproducible:

```bash
make poll-once
make preview-live
```

La aplicación queda en `http://127.0.0.1:4173/`. Para elegir otro puerto:

```bash
make preview-live LIVE_PREVIEW_PORT=4180
```

`preview-live` ejecuta y valida el build antes de copiarlo, enlaza
`data/radar/` y `data/status/` dentro de un staging ignorado por Git y solo
entonces inicia el servidor estático. No copies `apps/web/dist/` después de
interrumpir `npm run build`: un `dist` parcial puede no contener `index.html` y
`http.server` mostrará un listado de directorio en lugar de la aplicación.

El worker continuo y el servidor web se ejecutan en terminales distintas:

```bash
# terminal 1
make run-worker

# terminal 2
make preview-live
```

El contenedor reproduce además el servidor y los encabezados HTTP reales. La
guía de prueba prolongada, producción y actualizaciones está en
[`docs/DEPLOY.md`](docs/DEPLOY.md).

## Estructura

```text
apps/web/          frontend React + TypeScript + Vite
apps/worker/       paquete Python del worker
config/            configuración futura versionada
data/              datos locales ignorados por Git
deploy/            Containerfiles, Quadlet, nginx, backups y smoke tests
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
La caché resiliente, la PWA, los controles locales, las métricas y las pruebas
de navegador se describen en [`docs/PHASE_8.md`](docs/PHASE_8.md).
La arquitectura de contenedores, seguridad, persistencia, HTTPS, backups y
rollback está en [`docs/PHASE_9.md`](docs/PHASE_9.md); el despliegue completo y
la operación diaria están en [`docs/DEPLOY.md`](docs/DEPLOY.md) y
[`docs/OPERATIONS.md`](docs/OPERATIONS.md).

## Estrategia Git

`main` debe permanecer estable. Cada fase se desarrolla en una rama
`phase/<numero>-<descripcion>`, se valida con `make check` y se integra mediante
una revisión que confirme los criterios de aceptación. Los commits deben ser
pequeños, coherentes y no mezclar trabajo de fases posteriores.

Las decisiones que cambien arquitectura, alcance o comportamiento se registran
como ADR en `docs/DECISIONS.md`; no se reescribe la historia de decisiones.

No debe añadirse una coordenada, radar, proyección o cadencia a producción solo
porque parezca razonable: debe verificarse y documentarse.
