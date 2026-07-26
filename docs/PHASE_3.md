# Fase 3 — Extracción de reflectividad de Murcia

Estado: implementación y validación real controlada completadas el 24 de julio
de 2026.

## Alcance implementado

La fase añade el procesador `regional-v1` exclusivamente para `regional-mu`.
La herramienta:

1. valida que la entrada sea un GIF indexado compatible;
2. normaliza el original a RGB;
3. recorta la zona gráfica útil;
4. enumera y visualiza los índices de paleta usados;
5. clasifica las once clases observadas en la leyenda;
6. aplica una máscara estática versionada;
7. produce una capa RGBA transparente;
8. genera imágenes de depuración y un informe JSON.

No se ha añadido georreferenciación, mapa, reproyección, procesamiento nacional,
generalización a otros radares ni publicación automática en los manifiestos.

## Evidencia observada

Se analizaron 20 originales reales distintos de Murcia obtenidos el 23 y 24 de
julio de 2026. Los hashes concretos quedan registrados en
`config/masks/regional-mu-v1.json`, sin versionar masivamente los GIF.

Las 20 muestras coincidieron en:

- tamaño `480×530`;
- un único fotograma;
- modo indexado `P`;
- SHA-256 de paleta
  `1e4b3365a9efb2dabf275759f475d0bfdc34ef6452e46d3a714d866f24581cd6`.

Los primeros `480×480` píxeles contienen el círculo de cobertura. Las 50 filas
inferiores contienen leyenda, fecha, hora y texto técnico, por lo que el recorte
versionado es:

```json
{"left": 0, "top": 0, "width": 480, "height": 480}
```

Las transiciones entre gris exterior y negro interior de varias filas simétricas
determinan una cobertura circular en píxeles con centro `(240, 240)` y radio
`250`. Esta geometría genera `coverage-mask.png` y se aplica además de la
clasificación de color; no son coordenadas geográficas.

El fondo negro, el exterior gris, el texto blanco y la mayor parte del logotipo
no usan índices clasificados y quedan transparentes directamente.

## Paleta

La configuración está en `config/palettes/regional-mu-v1.json`.

| dBZ de leyenda | Índice GIF | RGB | Tratamiento |
| ---: | ---: | --- | --- |
| 12 | 16 | `0, 0, 252` | inequívoco |
| 18 | 23 | `0, 148, 252` | inequívoco |
| 24 | 26 | `0, 252, 252` | inequívoco |
| 30 | 6 | `67, 131, 35` | inequívoco |
| 36 | 7 | `0, 192, 0` | inequívoco |
| 42 | 8 | `0, 255, 0` | inequívoco |
| 48 | 10 | `255, 255, 0` | ambiguo |
| 54 | 9 | `255, 187, 0` | inequívoco |
| 60 | 4 | `255, 127, 0` | inequívoco |
| 66 | 3 | `255, 0, 0` | inequívoco |
| 72 | 5 | `200, 0, 90` | inequívoco |

Los valores se describen como marcas de la leyenda observada, no como una
reconstrucción de una cuadrícula meteorológica continua.

La coincidencia es exacta. Si cambia un RGB, la geometría o el modo, el
procesador falla con `reflectivity_processing_error` en vez de arriesgar una
clasificación silenciosamente incorrecta.

## Máscara estática y amarillo

El amarillo puro representa tanto la clase rotulada como 48 dBZ como los
límites administrativos. No se descarta globalmente: hacerlo perdería ecos
intensos.

`ambiguous-temporal-invariance-v2` genera una máscara binaria con esta regla:

1. usa al menos tres GIF distintos;
2. recorta cada muestra con la configuración;
3. examina solo clases de reflectividad marcadas como ambiguas;
4. excluye una posición si todas las muestras contienen allí el mismo índice
   ambiguo;
5. nunca convierte clases inequívocas, fondos negros o grises invariantes en
   exclusiones.

Con las 20 referencias se excluyeron exactamente 3.611 píxeles, todos amarillos
y pertenecientes a fronteras fijas. No se excluyó ninguna clase inequívoca. La
máscara se versiona como `config/masks/regional-mu-v1.png`; blanco significa
elegible y negro significa elemento fijo descartado. Su informe adyacente
incluye algoritmo, semántica, hashes y horas de las fuentes, ventana de
observación, hash de configuración y hash de la propia máscara.

La máscara no contiene coordenadas geográficas y no intenta resolver la
proyección.

## Salidas reproducibles

`analyze-reflectivity` escribe:

| Archivo | Contenido |
| --- | --- |
| `normalized.png` | original normalizado a RGB, `480×530` |
| `crop.png` | zona útil, `480×480` |
| `palette.png` | índices usados, RGB y decisión de clasificación |
| `classified.png` | todas las coincidencias de paleta antes de máscara |
| `static-mask.png` | copia de la máscara versionada aplicada |
| `coverage-mask.png` | círculo de cobertura parametrizado |
| `mask.png` | alfa final de reflectividad |
| `overlay.png` | capa RGBA transparente |
| `preview.png` | capa sobre damero para revisión visual |
| `report.json` | configuración, hashes, estadísticas y limitaciones |

El informe contabiliza por clase píxeles encontrados, conservados y descartados.
No contiene API keys, URLs efímeras ni rutas absolutas de la fuente.

## Comandos

Después de instalar o actualizar el worker:

```bash
make worker-install
```

Regenerar todas las salidas de una muestra:

```bash
.venv/bin/aemet-radar analyze-reflectivity \
  data/raw/regional-mu/AAAA/MM/DD/<sha256>.gif \
  --output-dir data/debug/phase-3/regional-mu/<sha256-corto>
```

Equivalente abreviado:

```bash
make analyze-reflectivity SAMPLE=data/raw/regional-mu/AAAA/MM/DD/<sha256>.gif
```

Regenerar deliberadamente las máscaras regionales con tres o más muestras
separadas al menos dos horas:

```bash
.venv/bin/aemet-radar build-radar-masks \
  --sample-root data/phase6-samples \
  --sample-root data/mask-samples \
  --sample-root data/manual-phase2
```

La máscara versionada no debe sustituirse usando únicamente imágenes
consecutivas o meteorológicamente similares. Cualquier regeneración exige
revisar el nuevo PNG, el informe y los golden tests antes de hacer commit.

Los golden fixtures se regeneran de forma independiente mediante:

```bash
.venv/bin/python scripts/generate_phase3_test_fixtures.py
```

## Validación automatizada

Los tests pequeños y sintéticos cubren:

- golden RGBA y golden alfa de `6×5` píxeles;
- conservación de un amarillo permitido;
- descarte de dos amarillos fijos;
- descarte por máscara de una clase inequívoca;
- descarte explícito de una clase fuera del círculo de cobertura;
- igualdad byte a byte entre dos ejecuciones;
- generación de máscara independiente del orden de muestras;
- mínimo de tres hashes distintos;
- rechazo de una paleta incompatible;
- integridad de la máscara real y su informe;
- ejecución de la CLI sin API key.

## Validación real

La muestra lluviosa
`bfa5d550869625df7c99dd21c74a9b15a31908a6720055921549698119ba3038`
produjo:

| Métrica | Píxeles |
| --- | ---: |
| clasificados antes de máscara | 7.314 |
| descartados por máscara | 3.611 |
| reflectividad final | 3.703 |
| amarillos clasificados | 3.636 |
| amarillos fijos descartados | 3.611 |
| amarillos variables conservados | 25 |

La revisión repetible de `classified.png`, `coverage-mask.png`, `overlay.png` y
`preview.png` confirmó que desaparecen fronteras, logotipo, textos, leyenda y
exterior del círculo, mientras permanecen los ecos visibles azules, cianes,
verdes y amarillos.

Las otras 19 muestras se procesaron con la misma plantilla. Según la situación
observada conservaron entre 51 y 3.345 píxeles de reflectividad, sin errores de
formato o paleta.

## Limitaciones conocidas

- La evidencia comprende 20 muestras de dos días; conviene ampliar la revisión
  con episodios intensos y estaciones distintas antes de generalizar.
- Un eco que mantuviera exactamente posición e índice en todas las muestras
  usadas para regenerar la máscara podría quedar descartado. Los hashes
  registrados permiten auditar esa selección.
- Si AEMET mantiene dimensiones y paleta pero mueve una frontera, la máscara
  actual podría dejar amarillo cartográfico. La plantilla deberá revisarse.
- Solo se conservan los colores exactos de los once bloques de leyenda. No se
  interpretan colores intermedios del logotipo o antialiasing como
  reflectividad.
- `overlay.png` sigue en coordenadas de píxel del producto. La calibración y
  georreferenciación pertenecen exclusivamente a la Fase 4.
- El ciclo periódico todavía publica originales. Integrar derivados
  georreferenciados en manifiestos se hará después de validar la Fase 4.
