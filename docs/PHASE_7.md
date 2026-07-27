# Fase 7 — Composición nacional

## Resultado

La composición nacional es un producto independiente, `national`, desde la
ingesta hasta el selector. Usa el procesador `national-v1`, sus propias
configuraciones de paleta, máscara y georreferenciación, y un manifiesto que no
mezcla fotogramas regionales.

La fuente primaria es la API web del visor oficial de AEMET, sin API key:

```text
GET /es/api-eltiempo/radar/timeline/compo/PB
GET /es/api-eltiempo/radar/imagen-radar/compo/<fichero>
GET /es/api-eltiempo/radar/bounds-radar/compo/<fichero>
```

La cronología observada el 27 de julio de 2026 contiene 24 horas a una cadencia
exacta de 10 minutos. La aplicación selecciona las 24 observaciones reales del
último intervalo inclusivo de 3 horas y 50 minutos. El nombre
`radwAAAAMMDDHHMM_3857.png` aporta la hora UTC y debe coincidir exactamente con
`Fecha`, que incluye zona horaria. Una repetición de la misma observación no
crea un original nuevo; dos horas distintas siguen siendo observaciones
distintas aunque sus píxeles coincidan.

OpenData `/api/red/radar/nacional` permanece como fallback de ingesta. Su GIF se
archiva, pero no se publica como capa mientras no supere un procesador nacional
específico: el sistema prefiere un hueco explícito a presentar una geometría no
validada.

## Formato y máscara nacional

El producto válido observado es un PNG indexado de `962×1079`, 4 bits y
proyección declarada en el nombre como EPSG:3857. Su paleta contiene:

- tres representaciones de fondo, transparencia o ausencia de dato;
- once RGB exactos de reflectividad;
- alfa 178 en las entradas visibles de origen.

Los índices de paleta no son estables entre fotogramas, por lo que la
clasificación usa RGB y alfa exactos. Un PNG de 8 bits observado durante una
indisponibilidad contenía manchas negras semitransparentes y no la composición;
la validación lo rechaza como `no-data`.

La máscara nacional no es una silueta espacial fija. Se genera para cada
fotograma con `exact-reflectivity-palette-v1`: vale 255 únicamente donde el RGB
pertenece a una clase de reflectividad validada y 0 en cualquier fondo,
transparencia o no-dato. Esto es deliberado porque la huella compuesta cambia
cuando un radar deja de contribuir; una máscara estática podría borrar ecos
futuros o sugerir cobertura inexistente.

Configuración versionada:

```text
config/palettes/national-v1.json
config/masks/national-v1.json
config/georeferencing/national-v1.json
```

Cada derivado conserva el hash del original y los hashes de las tres
configuraciones. Se publican:

```text
data/radar/national/frames/<sha256>/mask.png
data/radar/national/frames/<sha256>/overlay.png
data/radar/national/frames/<sha256>/national-processing.json
```

## Georreferenciación y cobertura

`bounds-radar` entrega las esquinas en orden SE, NE, NW, SW; el worker las
reordena a NW, NE, SE, SW para MapLibre. Los límites verificados son:

```text
NW [-16.08, 51.30]   NE [12.14, 51.30]
SW [-16.08, 27.22]   SE [12.14, 27.22]
```

Al proyectarlos en EPSG:3857 se obtiene un píxel de aproximadamente
`3265.53 × 3265.57 m`, coherente con el raster `962×1079`. La salida no se
reproyecta de nuevo ni recibe la geometría azimutal de los productos
regionales: MapLibre usa directamente el PNG transparente y las cuatro
esquinas oficiales.

La comparación visual sobre el mapa base conserva la posición de los ecos
respecto al producto oficial y el rectángulo de depuración coincide con esos
límites.

## Península, Baleares y Canarias

El visor identifica el producto como `Composicion radar`, región `Penbal` y
parámetro `compo/PB`: cubre Península y Baleares. Al seleccionar Canarias en el
visor oficial, este cambia al producto regional PPI de Las Palmas; no existe una
segunda lámina `compo` canaria en el contrato observado.

Por ello el índice nacional declara:

```json
{
  "regionCode": "PB",
  "coverageLabel": "Península y Baleares",
  "includesCanaryIslands": false
}
```

La interfaz lo explica junto al selector y mantiene el radar regional de Las
Palmas disponible. No se desplaza, duplica ni inventa una composición para
Canarias.

## Validación reproducible

Una muestra nacional guardada localmente se valida sin API key:

```bash
.venv/bin/aemet-radar validate-national original.png \
  --output-dir data/debug/phase-7/national
```

La evidencia mínima versionada en `docs/evidence/phase-7/national/` contiene el
PNG oficial, su máscara, el overlay transparente y el informe con hashes. La
muestra de las 11:50 UTC conserva 937 píxeles de reflectividad y descarta
1.037.061 píxeles de fondo o no-dato.

La prueba real controlada archivó 24 observaciones entre las 08:00 y las 11:50
UTC del 27 de julio de 2026. Una segunda ejecución sobre la misma cronología
devolvió `duplicate`, mantuvo 24 fotogramas, orden estricto, hashes únicos y
cero huecos.

El frontend publica una muestra completa y:

- agrupa la composición y los radares regionales en el selector;
- carga y precarga únicamente el manifiesto seleccionado;
- muestra hora de Madrid con cambio automático CET/CEST;
- reutiliza el mismo modelo explícito de huecos, sin interpolar observaciones;
- dibuja la cobertura nacional como rectángulo y no como radio o marcador de
  un emplazamiento regional.

## Limitaciones verificadas

- La API del visor es oficial y pública, pero no forma parte del OpenAPI de
  AEMET OpenData. El parser es estricto y cualquier deriva activa el fallback.
- La composición observada es exclusivamente Península y Baleares; Canarias
  se consulta en su producto regional.
- El GIF OpenData nacional queda archivado, pero no se presenta sin una
  geometría y extracción verificadas.
- La cobertura efectiva dentro del rectángulo depende de qué radares aporten
  datos en cada instante.

## Comprobaciones realizadas

- 24 observaciones reales a cadencia de 10 minutos;
- ventana inclusiva exacta de 230 minutos;
- idempotencia de una segunda ejecución;
- validación estricta de cronología, nombre, fecha, formato, paleta y límites;
- rechazo de una lámina de indisponibilidad de 8 bits;
- máscara dinámica y overlay con colores exactos;
- manifiesto, índice, health y selector independientes;
- ausencia de mezcla al cambiar entre Murcia y la composición;
- comparación visual con la referencia oficial y el mapa base;
- pruebas Python y frontend, lint, formato, tipado y build de producción.
