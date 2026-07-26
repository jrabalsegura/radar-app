# Fase 4 — Georreferenciación de Murcia sobre MapLibre

Estado: implementación, calibración y validación visual completadas el 26 de
julio de 2026.

## Alcance implementado

La fase añade dos piezas limitadas a `regional-mu`:

1. el procesador `regional-georeference-v1`, que transforma el `overlay.png`
   transparente de la Fase 3 a una rejilla Web Mercator;
2. un frontend MapLibre mínimo que muestra una única muestra real con control
   de opacidad y referencias de depuración.

No se ha añadido timeline, animación, selección de radar, composición nacional,
PWA ni publicación automática de derivados en los manifiestos.

## Evidencia y geometría de origen

La configuración reproducible está en
`config/georeferencing/regional-mu-v1.json`. Se apoya en estas fuentes
primarias:

- el visor oficial de AEMET publica el radar `FTN` como
  **Murcia–Fortuna**, centrado en `38.26438295, -1.18970006`;
- la [ayuda oficial del radar][aemet-help] establece un círculo regional de
  240 km, WGS84 para los productos georreferenciados y GeoTIFF como formato de
  descarga;
- la [documentación técnica de radar][aemet-radar-pdf] describe imágenes
  regionales `480×480`, resolución de 1 km a largo alcance y la proyección
  azimutal equidistante como la adecuada para una rejilla centrada en un radar;
- el visor sirve fronteras provinciales derivadas del IGN mediante su
  [topología de nivel 8][aemet-boundaries].

La descarga GeoTIFF observada el 26 de julio confirmó `EPSG:4326`, píxeles de
`0,005°`, metadatos de escala dBZ y tres instantes recientes por radar. Esa
descarga es la representación georreferenciada de AEMET; no se usa como
sustituto del GIF que archiva el proyecto.

Se comparó la geometría fija ya aislada por la Fase 3 con las fronteras
oficiales. La transformación que explica los límites es:

```text
+proj=aeqd
+lat_0=38.26438295
+lon_0=-1.18970006
+datum=WGS84
+units=m
```

El producto está orientado al norte, usa 1.000 m por píxel y el centro del radar
corresponde al centro del píxel `(240, 240)`. Los enteros representan centros
de píxel; `x` crece al este e `y` al sur.

## Puntos de control y error

Los puntos son cruces de tres límites provinciales, no lugares ajustados a ojo.
Para cada coordenada se calculó su posición azimutal y se comparó con el centro
del píxel amarillo observado en el GIF.

| Control | Píxel observado | Error |
| --- | ---: | ---: |
| Albacete–Ciudad Real–Jaén | `103, 209` | 0,105 km |
| Albacete–Ciudad Real–Cuenca | `106, 122` | 0,158 km |
| Cuenca–Teruel–Valencia (norte) | `242, 46` | 0,215 km |
| Albacete–Granada–Murcia | `139, 266` | 0,218 km |
| Alicante–Albacete–Valencia | `263, 182` | 0,459 km |
| Almería–Granada–Murcia | `150, 278` | 0,502 km |
| Alicante–Albacete–Murcia | `254, 196` | 0,594 km |
| Castellón–Teruel–Valencia | `273, 60` | 0,700 km |

Resultados agregados:

| Métrica | Resultado |
| --- | ---: |
| Puntos | 8 |
| Error medio | 0,369 píxeles / 0,369 km |
| RMS | 0,424 píxeles |
| Error máximo | 0,700 píxeles / 0,700 km |
| Umbral automático | 1,000 píxel |

El error incluye la cuantización inevitable de elegir el centro de un píxel
entero. `load_georeferencing_config` vuelve a calcularlo y rechaza la
configuración si cualquier punto supera el umbral.

## Reproyección

`georeference-murcia`:

1. exige el PNG RGBA `480×480` de `regional-v1`;
2. calcula la extensión de todo el perímetro azimutal;
3. crea una rejilla rectangular `EPSG:3857` alineada a 1.000 m;
4. transforma el centro de cada píxel de destino a la rejilla original;
5. copia el vecino más próximo si está dentro de los 240 km;
6. deja transparente cualquier posición restante;
7. escribe el PNG y un informe determinista con hashes, esquinas y errores.

El vecino más próximo es deliberado: el conjunto de colores no transparentes de
la salida es un subconjunto exacto de los colores de entrada. No aparecen clases
intermedias por interpolación.

La muestra real versionada produce `630×618` píxeles y estas esquinas MapLibre,
en orden noroeste, noreste, sureste y suroeste:

```json
[
  [-4.02445247, 40.43255134],
  [1.63493382, 40.43255134],
  [1.63493382, 36.07539084],
  [-4.02445247, 36.07539084]
]
```

## Visor MapLibre

El frontend carga:

```text
apps/web/public/radar/regional-mu/overlay-3857.png
apps/web/public/radar/regional-mu/georeferencing.json
```

Incluye:

- una fuente `image` de MapLibre con el fotograma reproyectado;
- opacidad regulable;
- círculo geodésico nominal de 240 km;
- radar y ocho puntos de control anclados a coordenadas reales;
- métricas de calibración;
- atribución visible a AEMET y al proveedor cartográfico.

El estilo se configura con `VITE_MAP_STYLE_URL`. El valor de ejemplo usa
OpenFreeMap para que la depuración local funcione sin API key; no constituye una
elección irreversible de proveedor ni una garantía de servicio.

Arranque:

```bash
make dev-web
```

Abrir `http://127.0.0.1:5173/`.

## Reproducción desde un original

```bash
.venv/bin/aemet-radar analyze-reflectivity \
  data/raw/regional-mu/AAAA/MM/DD/<sha256>.gif \
  --output-dir data/debug/phase-3/regional-mu/<sha256-corto>

.venv/bin/aemet-radar georeference-murcia \
  data/debug/phase-3/regional-mu/<sha256-corto>/overlay.png \
  --output-dir data/debug/phase-4/regional-mu/<sha256-corto>
```

El segundo comando no requiere API key.

## Validación

Las pruebas automatizadas cubren:

- cálculo de los ocho controles y umbral subpíxel;
- rechazo de una calibración desplazada;
- reproyección determinista byte a byte;
- conservación exacta de clases RGBA;
- descarte de un píxel situado fuera del alcance;
- orden de las cuatro esquinas MapLibre;
- ejecución de la CLI sin API key;
- carga del contrato de fotograma en React;
- control de opacidad, depuración, métricas y error de carga.

La revisión en navegador se realizó en `1280×720` y `390×844`. Confirmó:

- fotograma, puntos y círculo en coordenadas reales;
- permanencia del ajuste al ampliar;
- respuesta de opacidad y alternancia de depuración;
- atribución AEMET/OpenFreeMap/OpenMapTiles/OpenStreetMap visible;
- ausencia de desbordamiento horizontal en móvil.

## Limitaciones conocidas

- La calibración usa ocho cruces del mapa fijo del producto; debe repetirse si
  AEMET cambia geometría, tamaño o centro.
- El error mide el ajuste del marco geográfico, no la incertidumbre física de
  la medición radar.
- La muestra del frontend es de depuración y no se actualiza todavía desde los
  manifiestos.
- OpenFreeMap es el estilo local por defecto y no ofrece SLA; producción deberá
  conservar el estilo configurable.
- Solo Murcia está calibrada. No se deben reutilizar sus parámetros para otro
  radar ni para el mosaico nacional.

[aemet-help]: https://www.aemet.es/es/eltiempo/observacion/radar/ayuda
[aemet-radar-pdf]: https://www.aemet.es/documentos/es/conocermas/recursos_en_linea/publicaciones_y_estudios/publicaciones/Fisica_del_caos_en_la_predicc_meteo/08_Radar_meteorologico_y_red_de_rayos.pdf
[aemet-boundaries]: https://www.aemet.es/es/api-eltiempo/lineas_limite/8/PB
