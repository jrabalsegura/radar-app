# Fase 6 — Red regional configurable

## Resultado

La aplicación incorpora los 15 productos regionales publicados en la
especificación OpenAPI de AEMET. Todos permanecen en el catálogo, tienen
manifiesto y aparecen en el selector, incluso cuando AEMET no entrega una
imagen. Un radar sin datos muestra su emplazamiento y un estado explícito; no
hereda fotogramas de otro radar y continúa formando parte de cada ciclo de
consulta.

La revisión del 27 de julio de 2026 migró la ingesta regional a la API web del
visor oficial. Una única cronología aporta 24 observaciones PPI por
emplazamiento, ordenadas cada 10 minutos entre `último - 3 h 50 min` y el
último dato. OpenData y el pipeline GIF se conservan como fallback.

Fuentes oficiales:

- [AEMET OpenData OpenAPI](https://opendata.aemet.es/AEMET_OpenData_specification.json),
  para los códigos de los endpoints;
- [visor de radares de AEMET](https://www.aemet.es/es/eltiempo/observacion/radar.html),
  para la cronología PPI, imágenes, límites, emplazamientos y coordenadas;
- [ayuda de radar de AEMET](https://www.aemet.es/es/eltiempo/observacion/radar/ayuda),
  para alcance, resolución y naturaleza del producto.

## Fuente primaria PPI y fallback

El worker obtiene una sola vez por ciclo:

```text
GET /es/api-eltiempo/radar/timeline/PPI/PB
```

La respuesta observada contiene 432 entradas: 18 emplazamientos por 24 horas
de producto. La app utiliza los 15 radares de su catálogo OpenAPI. Para cada
entrada valida el nombre `SSSYYMMDDHHMMSS.PPI.Z_005_240.png`, la fecha
ISO-8601 con zona y su coincidencia exacta en UTC; después descarga:

```text
GET /es/api-eltiempo/radar/imagen-radar/PPI/<fichero>
GET /es/api-eltiempo/radar/bounds-radar/PPI/<fichero>
```

El PNG válido es RGBA y solo contiene fondo, transparencia y la paleta exacta
de reflectividad. Un radar seco sigue siendo una observación válida. Texto,
colores desconocidos o “Producto no disponible” activan OpenData como
respaldo. Los límites oficiales se reordenan al contrato NW, NE, SE, SW de
MapLibre; el PPI no usa las máscaras o proyecciones del GIF.

La API web del visor no requiere key. `AEMET_API_KEY` continúa siendo necesaria
para el fallback OpenData. Ninguna de las dos rutas, ni la key, se escribe en
informes o logs.

## Inventario verificado

La comprobación completa del 27 de julio de 2026 obtuvo 24 PPI válidos para
doce productos. Málaga entregó tres PPI válidos y 21 láminas no disponibles;
Las Palmas recurrió al GIF OpenData y Valencia quedó sin datos. A Coruña y
Vizcaya, antes ausentes en OpenData, publicaron las 24 observaciones:

| API | Producto | Emplazamiento | Validación de muestra |
| --- | --- | --- | --- |
| `am` | Almería | NJR, Níjar | verificada |
| `sa` | Asturias | SLS, Salas | verificada |
| `pm` | Illes Balears | LLM, Llucmajor | verificada |
| `ba` | Barcelona | GLD, Gelida | verificada |
| `cc` | Cáceres | SFT, Sierra de Fuentes | verificada |
| `co` | A Coruña | CCD, Cerceda | 24 PPI |
| `ma` | Madrid | TJV, Torrejón de Velasco | verificada |
| `ml` | Málaga | AHR, Alhaurín el Grande | verificada |
| `mu` | Murcia | FTN, Fortuna | ocho puntos de control |
| `vd` | Palencia | LID | verificada |
| `ca` | Las Palmas | CAN, Canarias | fallback GIF |
| `se` | Sevilla | CLG, El Castillo de las Guardas | verificada |
| `va` | Valencia | VAL | sin datos |
| `ss` | Vizcaya | SSE, Maruri-Jatabe | 24 PPI |
| `za` | Zaragoza | PDG, Perdiguera | verificada |

El visor oficial también representa emplazamientos sin producto regional
OpenData configurado. No se añaden al selector hasta definir su identidad,
operación y alcance dentro del proyecto.

## Catálogo y estrategias

`config/radars.yaml` es la única fuente de configuración regional. Cada entrada
declara:

- código API, código y nombre de emplazamiento;
- centro WGS84, alcance, zoom y cadencia;
- perfil estricto de plantilla y paleta;
- política para clases de color ambiguas;
- máscara estática opcional;
- calibración específica opcional;
- estado de validación de la muestra.

El worker carga y valida el YAML al arrancar. Rechaza un catálogo que no tenga
exactamente los 15 códigos, identificadores duplicados, coordenadas imposibles
o ficheros de estrategia inexistentes.

El bloque siguiente documenta el pipeline GIF que ahora actúa como fallback.
Los 12 GIF disponibles compartieron en la muestra controlada dimensiones
`480×530`, modo indexado y la misma paleta de 64 entradas. El perfil
`regional-safe-v1` comprueba esos datos para cada descarga: un cambio de
plantilla o paleta falla de forma explícita y no se publica por semejanza.

Cada radar usa su propia máscara binaria en su cuadrícula original. La
calibración `ambiguous-temporal-invariance-v2` solo excluye píxeles de una clase
marcada como ambigua que permanezcan idénticos en todas las muestras; nunca
convierte en máscara un eco no ambiguo aunque permanezca inmóvil. Cada informe
conserva hashes, horas y ventana de observación.

La generación en lote deduplica por contenido y exige al menos tres originales
distintos separados dos horas. Murcia conserva veinte muestras y más de dos
días de observación. Como excepción estrecha, `build-reviewed-dry-mask` admite
un único GIF cuando se coteja con el PNG PPI del visor oficial para el mismo
radar y hora. La herramienta exige que esa referencia RGBA tenga transparencia
y un único color visible; rechaza ecos, texto y avisos de producto no
disponible.

```bash
.venv/bin/aemet-radar build-radar-masks \
  --sample-root data/phase6-samples \
  --sample-root data/mask-samples \
  --sample-root data/manual-phase2
```

La ejecución controlada del 26 y 27 de julio dejó 12 máscaras específicas
activas: Almería, Asturias, Illes Balears, Barcelona, Cáceres, Madrid, Málaga,
Murcia, Palencia, Las Palmas, Sevilla y Zaragoza. Once proceden de varias
muestras temporales; Málaga usa la excepción seca revisada:

```bash
.venv/bin/aemet-radar build-reviewed-dry-mask \
  data/mask-samples/raw/regional-ml/2026/07/26/ddeda4d5f83b45bc5553921858a66713bdb3af91247b66208a2d59cea5f0b831.gif \
  docs/evidence/phase-6/official-viewer/AHR260726105000.PPI.Z_005_240.png \
  --product regional-ml \
  --observed-at 2026-07-26T10:50:00Z \
  --dry-reference-url https://www.aemet.es/es/api-eltiempo/radar/imagen-radar/PPI/AHR260726105000.PPI.Z_005_240.png
```

El PPI de Málaga de las 10:50 UTC contiene únicamente transparencia y el color
RGBA `[239, 242, 249, 179]`. El GIF de la misma hora aporta las posiciones
exactas de sus 3.207 píxeles amarillos fijos; el informe conserva ambos hashes.

A Coruña y Vizcaya conservan el modo GIF conservador para el fallback porque
OpenData responde 404, pero sus PPI se publican directamente: no necesitan
máscara. Valencia sigue sin PPI utilizable ni GIF. Las capturas, hashes y
diagnóstico previo se conservan como evidencia histórica en
`docs/evidence/phase-6/official-viewer/`.

El worker interpreta el estado AEMET 404 como `no-data`, no como un fallo: hace
un único intento, mantiene el manifiesto y la retención, limpia `lastError` y
vuelve a consultar el producto en el siguiente ciclo. Los productos sin datos
no degradan un ciclo cuyos demás radares estén actuales.

## Georreferenciación y validación

En el fallback GIF, cada radar usa una proyección azimutal equidistante propia centrada en las
coordenadas oficiales. La rejilla regional se reproyecta a EPSG:3857 con vecino
más próximo y cada fotograma publica sus cuatro esquinas en
`imageCoordinates`. MapLibre nunca reutiliza las coordenadas de Murcia.

La herramienta sin API key:

```bash
make validate-radar PRODUCT=regional-am SAMPLE=ruta/a/muestra.gif
```

genera:

```text
data/debug/phase-6/<radar>/
├── reflectivity/
├── georeferenced/
├── calibration/
├── calibration-boundaries.png
└── validation.json
```

Valida plantilla, paleta, extracción y proyección, y produce una capa de límites
para comparación visual con el visor oficial. Las muestras de los 12 productos
disponibles superaron este proceso. Murcia conserva adicionalmente su
calibración cuantitativa de ocho puntos de control.

## Publicación y frontend

Una reconstrucción sin argumentos procesa los 15 radares:

```bash
.venv/bin/aemet-radar rebuild-manifests
```

Cada uno obtiene `/radar/<id>/manifest.json`. El índice añade centro, cobertura,
estado de validación, disponibilidad y último fotograma. `health.json` mantiene
un estado operativo independiente: `current`, `delayed`, `no-data` o `error`.

El frontend primero carga el índice y el estado. Solo solicita el manifiesto y
precarga las imágenes del radar seleccionado. Al cambiar:

- detiene la reproducción y descarta el timeline anterior;
- centra un mapa nuevo en el emplazamiento;
- carga exclusivamente el manifiesto elegido;
- no presenta una capa hasta recibir un fotograma de ese mismo producto.

Los manifiestos vacíos son válidos. Muestran “Sin imágenes disponibles ahora”,
mantienen el selector y no renderizan controles de reproducción.

## Ingesta escalonada

Por defecto se consulta un producto por vez con una pausa de un segundo entre
productos, nunca después del último. Se configura mediante:

```text
AEMET_PRODUCT_DELAY_SECONDS=1
```

Los reintentos limitados y el backoff siguen aplicándose por producto. Un fallo
no detiene la actualización de los demás ni reemplaza su última publicación
válida.

## Añadir un futuro radar

Cuando OpenAPI publique un código nuevo:

1. verificar el endpoint y las coordenadas en fuentes oficiales;
2. añadir la entrada y el producto al catálogo versionado;
3. capturar al menos una muestra real sin versionar el GIF;
4. ejecutar `validate-radar` y revisar ambas previsualizaciones;
5. crear perfil, máscara o calibración específicos si el contrato visual
   difiere;
6. actualizar el contrato que valida el número de entradas y la muestra pública.

El procesamiento, publicación, selector y mapa no requieren ramas condicionales
por radar.

## Validación realizada

- 15 manifiestos independientes;
- 13 radares con cronología PPI primaria y Las Palmas con fallback GIF;
- 24 observaciones PPI ordenadas para A Coruña, Vizcaya, Murcia y otros nueve
  productos;
- ventana exacta de 230 minutos y hasta 24 observaciones reales;
- 12 máscaras propias activas y tres políticas conservadoras;
- cinco imágenes oficiales del visor conservadas con SHA-256;
- un manifiesto vacío y seleccionable;
- cambio de producto sin mezcla de rutas ni fotogramas;
- ajuste de centro, zoom, cobertura y esquinas por radar;
- precarga limitada al timeline seleccionado;
- pausa configurada entre consultas;
- pruebas de cronología, fechas, límites, paleta PPI, radar seco, fallback,
  idempotencia y 24 observaciones con el mismo hash;
- pruebas de catálogo, perfil compartido y geometría de Almería;
- lint, formato, tipado, tests y build de producción.
