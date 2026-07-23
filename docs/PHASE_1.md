# Fase 1 — Ingesta e inspección de originales

Estado: implementación y validación real controlada completadas el 23 de julio
de 2026. La composición nacional no estaba disponible durante la validación.

## Fuentes verificadas

La especificación oficial consultada el 23 de julio de 2026 es OpenAPI 3.0.1,
versión de API 2.0:

- especificación: <https://opendata.aemet.es/AEMET_OpenData_specification.json>
- servidor: `https://opendata.aemet.es/opendata`
- Murcia: `GET /api/red/radar/regional/mu`
- nacional: `GET /api/red/radar/nacional`
- autenticación: cabecera `api_key`

La especificación declara 10 minutos para regionales y 30 minutos para la
composición nacional. Estas cadencias se registran como información de catálogo,
no se usan para fabricar `productTime`.

## Inventario regional provisional

Esta lista procede del parámetro `radar` de la especificación oficial. La
comprobación real hizo una única llamada inicial por código, con un segundo de
pausa y sin descargar los GIF.

| Código | Radar | OpenAPI | Llamada real 2026-07-23 |
| --- | --- | --- | --- |
| `am` | Almería | publicado | disponible, estado 200 |
| `sa` | Asturias | publicado | disponible, estado 200 |
| `pm` | Illes Balears | publicado | disponible, estado 200 |
| `ba` | Barcelona | publicado | disponible, estado 200 |
| `cc` | Cáceres | publicado | disponible, estado 200 |
| `co` | A Coruña | publicado | no disponible, estado 404 |
| `ma` | Madrid | publicado | disponible, estado 200 |
| `ml` | Málaga | publicado | disponible, estado 200 |
| `mu` | Murcia | publicado | disponible, estado 200 |
| `vd` | Palencia | publicado | disponible, estado 200 |
| `ca` | Las Palmas | publicado | disponible, estado 200 |
| `se` | Sevilla | publicado | disponible, estado 200 |
| `va` | Valencia | publicado | no disponible, estado 404 |
| `ss` | Vizcaya | publicado | no disponible, estado 404 |
| `za` | Zaragoza | publicado | disponible, estado 200 |

Solo Murcia y nacional forman parte de la ingesta de esta fase. El catálogo no
habilita el resto de radares en producción. Una indisponibilidad puntual tampoco
elimina un código del inventario.

## Manejo de la API key

La clave no se pasa como argumento de la CLI. Para desarrollo:

```bash
cp .env.example .env
chmod 600 .env
```

Después se edita `.env` localmente. La CLI carga el archivo sin sobrescribir una
variable ya exportada. `.env`, `data/` y los caches están ignorados por Git.

El cliente:

1. envía la clave solo a la llamada inicial como cabecera;
2. valida que `datos` y `metadatos` sean URLs HTTPS de
   `opendata.aemet.es`;
3. descarga inmediatamente `datos` sin reenviar la clave;
4. no sigue redirecciones ni conserva las URLs efímeras;
5. limita el tamaño descargado y exige que Pillow detecte un GIF válido;
6. usa mensajes de error propios que no incluyen peticiones ni cabeceras.

## Ejecución

```bash
make fetch-once
```

Equivalentes:

```bash
.venv/bin/aemet-radar fetch-once
.venv/bin/aemet-radar fetch-once --product regional-mu
.venv/bin/aemet-radar fetch-once --product national
```

La comprobación provisional de códigos se ejecuta por separado:

```bash
make check-inventory
```

Realiza solo la primera llamada de cada código, espera un segundo entre ellas y
no sigue ni descarga las URLs de datos.

No hay reintentos ni scheduler en esta fase. Cada producto genera como máximo
una consulta inicial, una descarga de datos y una consulta de metadatos. Los
reintentos y la ejecución periódica pertenecen a la Fase 2.

## Archivo e informes

```text
data/
├── raw/
│   └── <producto>/<AAAA>/<MM>/<DD>/
│       ├── <sha256>.gif
│       └── <sha256>.json
└── reports/phase-1/
    └── <hora-de-obtención>.json
```

El informe adyacente registra:

- producto, endpoint estable, cadencia y `retrievedAt`;
- estado y cabeceras HTTP permitidas;
- metadatos públicos de AEMET;
- MIME declarado y detectado;
- tamaño, dimensiones, modo, fotogramas y paleta completa;
- SHA-256;
- evidencias y estado de `productTime`;
- rutas locales relativas.

El informe comparativo se genera al consultar ambos productos. No contiene API
key ni URLs efímeras.

## Investigación de `productTime`

El orden de búsqueda es:

1. cabecera `Last-Modified`;
2. texto determinista en metadatos internos del GIF;
3. timestamp reconocible en el nombre del recurso;
4. estado `unresolved`.

`Last-Modified` se marca como candidata de confianza media hasta compararla con
la hora impresa en muestras reales. No se usa OCR general y no se redondea
`retrievedAt` según la cadencia.

## Validación automatizada

Las fixtures son GIF sintéticos sin contenido de AEMET. Las pruebas cubren:

- éxito e inspección;
- deduplicación;
- timeout;
- HTTP 401, 429 y 503;
- JSON inicial inválido;
- URL de descarga no permitida;
- fallo de la URL efímera;
- contenido vacío, HTML o no-GIF;
- ausencia de la API key en errores e informes.

## Resultado de la validación real

### Murcia

Se archivaron dos respuestas válidas obtenidas alrededor de las 15:24–15:26 UTC:

| Propiedad | Resultado |
| --- | --- |
| HTTP inicial y datos | 200 |
| MIME declarado | `image/gif;charset=ISO-8859-15` |
| MIME detectado | `image/gif` |
| Formato | GIF89a |
| Dimensiones | 480 × 530 |
| Modo | `P` |
| Fotogramas | 1 |
| Paleta | RGB, 64 entradas |
| Tamaños observados | 11 319 y 11 186 bytes |
| Metadatos internos | `background=0`, `duration=0`, `version=GIF89a` |
| `productTime` | sin resolver |

Las dos respuestas tuvieron hash distinto, por lo que representan originales
distintos a efectos de archivo. La prueba automatizada con contenido idéntico
confirma que la segunda ejecución no crea otro GIF ni otro informe.

El endpoint de metadatos respondió `text/plain;charset=ISO-8859-15`, aunque el
contenido era JSON. Tras decodificar según el charset se observaron
`unidad_generadora`, descripción, periodicidad, formato, copyright y nota legal
coherentes con `SPEC.md`.

No se observó `Last-Modified`, timestamp en metadatos internos ni timestamp
reconocible en el nombre efímero. La cabecera `Date` coincide con la consulta y
no se interpreta como hora del producto.

### Composición nacional

El endpoint oficial respondió HTTP 200 con estado AEMET 404 en dos consultas
controladas. No se descargó ni inventó ningún original nacional. El informe
comparativo local conserva el éxito de Murcia y el error tipado
`api_status_error` de nacional.

Esta indisponibilidad puede ser temporal. No justifica cambiar el endpoint
publicado ni fingir propiedades del producto nacional; deberá repetirse una
consulta controlada antes de una fase que dependa de su contenido.

### Inventario

La comprobación de pasarela encontró 12 de 15 códigos regionales disponibles.
`co`, `va` y `ss` devolvieron estado AEMET 404. El resultado detallado se guarda
localmente bajo `data/reports/phase-1/` y no contiene URLs efímeras ni la API
key.

Los GIF reales y sus informes completos permanecen en `data/`, ignorado por
Git. Este documento conserva únicamente propiedades y conclusiones no
sensibles.
