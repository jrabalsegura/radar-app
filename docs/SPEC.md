# SPEC.md — Radar AEMET interactivo

> **Documento de contexto global y fuente principal de verdad del proyecto.**
>
> Codex debe leer este documento completo antes de trabajar en cualquier fase. Las decisiones nuevas que cambien el alcance, la arquitectura o el comportamiento se registrarán también en `docs/DECISIONS.md`.
>
> Estado: borrador inicial
> Producto: aplicación web personal de visualización de radar AEMET
> Idioma de la interfaz: español
> Zona horaria de presentación: `Europe/Madrid`

---

## 1. Visión

Construir una aplicación web rápida, minimalista e instalable como PWA para visualizar la reflectividad de los radares meteorológicos de AEMET sobre un mapa interactivo basado en MapLibre.

La aplicación debe permitir comprender de un vistazo:

- dónde está lloviendo;
- cómo se ha desplazado la precipitación durante las últimas tres horas;
- qué fotograma se está viendo y a qué hora corresponde;
- qué radar regional o composición nacional está seleccionado.

La inspiración funcional es LiteRadar: abrir la aplicación y llegar inmediatamente al radar, sin publicidad, sin cuentas de usuario y sin convertir el producto en una aplicación meteorológica generalista.

---

## 2. Principios del producto

1. **Radar primero.** El mapa y la precipitación ocupan casi toda la pantalla.
2. **Rapidez.** La carga inicial y el cambio entre fotogramas deben sentirse inmediatos.
3. **Simplicidad.** No se añadirán predicciones, noticias, widgets meteorológicos ni funciones ajenas al radar durante el MVP.
4. **Información honesta.** Debe distinguirse claramente entre datos observados por AEMET y cualquier procesamiento realizado por la aplicación.
5. **Tolerancia a fallos.** Si AEMET no responde, la aplicación seguirá mostrando los últimos fotogramas válidos e indicará que están desactualizados.
6. **Privacidad.** No habrá cuentas, seguimiento publicitario ni almacenamiento remoto de la ubicación del usuario.
7. **Desarrollo incremental.** Cada fase tendrá criterios de aceptación y no se iniciará la siguiente hasta que la anterior esté validada.

---

## 3. Fuente de datos

### 3.1 AEMET OpenData

La aplicación utilizará los productos públicos de radar de AEMET OpenData:

- composición nacional;
- imágenes de los radares regionales;
- periodicidad declarada para los radares regionales: cada 10 minutos.

La primera llamada autenticada devuelve un JSON similar a:

```json
{
  "descripcion": "exito",
  "estado": 200,
  "datos": "https://opendata.aemet.es/opendata/sh/XXXXXXXX",
  "metadatos": "https://opendata.aemet.es/opendata/sh/YYYYYYYY"
}
```

El worker debe descargar inmediatamente el recurso de `datos`. No debe guardar esa URL efímera como si fuera el dato definitivo.

Los metadatos observados para radar regional indican:

```json
{
  "unidad_generadora": "Teledetección Terrestre",
  "descripcion": "PPI (Z) de cada radar regional",
  "periodicidad": "cada 10 minutos",
  "formato": "image/gif",
  "copyright": "© AEMET. Autorizado el uso de la información y su reproducción citando a AEMET como autora de la misma.",
  "notaLegal": "https://www.aemet.es/es/nota_legal"
}
```

### 3.2 Condiciones de reutilización

La interfaz debe mostrar de forma visible:

- `Datos de radar: AEMET`;
- hora del producto o, cuando no pueda determinarse, hora de obtención;
- enlace a la nota legal;
- atribución del proveedor del mapa base.

La reflectividad no debe alterarse de forma que cambie su significado meteorológico. El procesamiento debe limitarse a separar la capa radar de los elementos gráficos fijos, georreferenciarla, añadir transparencia y optimizar su transporte.

---

## 4. Problema técnico central

AEMET entrega una imagen gráfica ya compuesta, no una cuadrícula georreferenciada de reflectividad.

La imagen regional observada contiene, en un mismo raster:

- ecos de reflectividad;
- fondo negro;
- círculo de cobertura;
- límites administrativos amarillos;
- logotipo y texto;
- escala de reflectividad;
- fecha y hora impresas;
- zonas grises fuera de cobertura.

Para poder mostrar solo la reflectividad sobre MapLibre será necesario construir un procesador reproducible que:

1. conserve los colores que representan reflectividad;
2. elimine fondo, límites, logotipos, leyenda y texto;
3. asigne transparencia al resto;
4. georreferencie la capa;
5. produzca una imagen o conjunto de teselas que MapLibre pueda representar correctamente.

La técnica exacta de separación no se considera cerrada hasta completar el spike técnico. La hipótesis inicial combina:

- recorte fijo por producto;
- máscara estática por radar para elementos cartográficos;
- identificación de la paleta de reflectividad;
- máscara circular de cobertura;
- comparación temporal de varios fotogramas;
- reglas específicas para colores ambiguos, especialmente el amarillo usado también por límites administrativos;
- validación visual mediante imágenes de depuración.

No se utilizará OCR general como dependencia central. La hora del producto se intentará obtener, en este orden, mediante cabeceras HTTP, metadatos del GIF, nombre del recurso, cadencia conocida o lectura determinista de la zona de timestamp si fuese imprescindible.

---

## 5. Alcance funcional

### 5.1 Funciones obligatorias del MVP

#### Mapa

- Mapa interactivo con MapLibre.
- Zoom, desplazamiento y ajuste automático al radar seleccionado.
- Mapa base configurable mediante variable de entorno.
- Botón para centrar en la ubicación actual.
- Control de opacidad de la capa radar.
- Atribuciones siempre visibles.

#### Fuentes de radar

- Composición nacional.
- Todos los radares regionales que exponga AEMET y que hayan sido configurados y validados.
- Selector explícito de fuente.
- Opción futura de selección automática según ubicación, sin ocultar qué radar está activo.

#### Historial

- Visualización de las últimas **tres horas**.
- Para productos regionales con cadencia de 10 minutos, objetivo de 19 posiciones contando ambos extremos cuando estén disponibles.
- El backend conservará margen adicional para soportar retrasos y reconstrucción del manifiesto; la interfaz mostrará tres horas.
- Ausencias de fotogramas representadas como huecos, no como datos inventados.

#### Controles temporales

- Botón reproducir/pausar.
- Barra temporal deslizable.
- Botones individuales para seleccionar cada imagen de reflectividad.
- Cada botón mostrará la hora local, por ejemplo `12:10`.
- Indicación diferenciada del fotograma más reciente.
- Velocidad de reproducción configurable al menos entre lenta, normal y rápida.
- Pausa breve en el último fotograma antes de reiniciar el bucle.
- Teclas de flecha para avanzar o retroceder un fotograma en escritorio.

#### Estado del dato

- Hora del fotograma.
- Antigüedad del último dato.
- Estado: actualizado, retrasado, sin datos o error de procesamiento.
- El fallo de AEMET no debe borrar los fotogramas ya publicados.
- El frontend no debe mostrar como reciente una imagen antigua.

#### PWA y responsive

- Interfaz utilizable en móvil y escritorio.
- Instalación como PWA.
- Pantalla completa.
- Caché de la aplicación y del último manifiesto válido.
- No se exige uso completamente offline en el MVP.

### 5.2 Fuera del MVP

- Cuentas de usuario.
- Publicidad.
- Predicción meteorológica convencional.
- Nowcasting o cálculo de hora estimada de llegada de lluvia.
- Alertas push.
- Capas de rayos, viento o satélite.
- Aplicaciones nativas.
- Edición manual de mapas desde la interfaz.
- Exposición pública de la API key de AEMET.

Estas funciones solo se plantearán después del MVP y mediante nuevas decisiones registradas.

---

## 6. Diseño de interfaz

### 6.1 Pantalla principal

La aplicación será de una sola pantalla:

```text
┌──────────────────────────────────────────────────────────────┐
│ Radar: Murcia ▾   Nacional/Regional   Estado: actualizado   │
│                                                              │
│                                                              │
│                   MAPA MAPLIBRE                              │
│              + CAPA DE REFLECTIVIDAD                         │
│                                                              │
│                                                   [ubicación] │
│                                                   [opacidad]  │
├──────────────────────────────────────────────────────────────┤
│ 11:20 · hace 4 min                              [−3 h … ahora]│
│ [▶] ─────────────────────●────────────────────────── [1×]     │
│ [09:20] [09:30] [09:40] … [11:10] [11:20]                    │
└──────────────────────────────────────────────────────────────┘
```

En móvil, el panel temporal ocupará la zona inferior y podrá compactarse, pero los botones de fotograma deberán seguir siendo utilizables mediante desplazamiento horizontal.

### 6.2 Selector de radar

Agrupación propuesta:

- `Composición nacional`
- `Radares regionales`
  - nombre legible;
  - código interno AEMET;
  - indicador de estado;
  - hora del último fotograma.

La lista concreta de radares se obtendrá y validará durante el spike; no se codificarán nombres sin comprobar su endpoint.

### 6.3 Animación

Los datos observados son discretos. La aplicación no inventará reflectividad entre dos observaciones.

La sensación de fluidez se conseguirá mediante:

- precarga de todos los fotogramas del bucle;
- transición corta de opacidad entre el fotograma actual y el siguiente;
- renderizado a la tasa de refresco del navegador;
- pausa configurable en el fotograma más reciente.

Una interpolación meteorológica real entre imágenes queda fuera del MVP.

---

## 7. Arquitectura

### 7.1 Componentes

```text
AEMET OpenData
      │
      ▼
Worker Python
  ├── consulta endpoints
  ├── descarga GIF
  ├── deduplica
  ├── conserva original
  ├── procesa reflectividad
  ├── georreferencia
  ├── publica derivados
  └── genera manifiestos JSON
      │
      ▼
Volumen persistente
  ├── raw/
  ├── processed/
  ├── masks/
  ├── manifests/
  └── debug/
      │
      ▼
Nginx
  ├── frontend estático
  ├── manifiestos
  └── imágenes/teselas
      │
      ▼
React + TypeScript + MapLibre
```

No se introducirá base de datos en el MVP salvo que el desarrollo demuestre una necesidad real. El estado operativo puede resolverse con archivos y manifiestos atómicos.

### 7.2 Tecnologías propuestas

#### Frontend

- React.
- TypeScript estricto.
- Vite.
- MapLibre GL JS.
- PWA mediante plugin de Vite.
- Pruebas unitarias con Vitest.
- Pruebas de interfaz principales con Playwright.

#### Worker

- Python 3.12 o versión estable disponible en el entorno.
- `httpx` para HTTP.
- Pillow para inspección y manipulación básica.
- NumPy para máscaras.
- `pyproj`, Rasterio o GDAL cuando sea necesario para georreferenciación y reproyección.
- Pytest para pruebas.
- Tipado con mypy o pyright.
- Ruff para formato y lint.

#### Operación

- Podman.
- Quadlet/systemd.
- Nginx como servidor y proxy.
- Variables de entorno y secretos fuera del repositorio.
- Despliegue final por `ssh remote`.

---

## 8. Estructura prevista del repositorio

```text
aemet-radar/
├── README.md
├── .gitignore
├── .editorconfig
├── .env.example
├── compose.yaml                  # solo desarrollo si resulta útil
├── docs/
│   ├── SPEC.md
│   ├── ROADMAP.md
│   ├── DECISIONS.md
│   ├── DEPLOY.md
│   └── OPERATIONS.md
├── apps/
│   ├── web/
│   │   ├── src/
│   │   ├── public/
│   │   └── tests/
│   └── worker/
│       ├── src/aemet_radar/
│       ├── tests/
│       └── pyproject.toml
├── config/
│   ├── radars.yaml
│   ├── palettes/
│   └── control-points/
├── samples/
│   ├── README.md
│   └── .gitkeep
├── scripts/
├── deploy/
│   ├── containers/
│   ├── quadlet/
│   └── nginx/
└── data/                         # ignorado por Git
```

Las muestras originales de AEMET no se versionarán masivamente. Solo se conservarán fixtures mínimos y autorizados, documentando su origen.

---

## 9. Modelo de datos basado en manifiestos

### 9.1 Definición de radar

```json
{
  "id": "regional-mu",
  "kind": "regional",
  "label": "Murcia",
  "aemetCode": "mu",
  "endpoint": "/api/red/radar/regional/mu",
  "enabled": true,
  "processor": "regional-v1",
  "georeference": {
    "method": "pending-calibration"
  }
}
```

### 9.2 Fotograma interno

```json
{
  "id": "regional-mu_20260723T112000Z",
  "radarId": "regional-mu",
  "productTime": "2026-07-23T11:20:00Z",
  "retrievedAt": "2026-07-23T11:23:15Z",
  "sourceHash": "sha256:...",
  "rawFile": "raw/regional-mu/2026/07/23/112000.gif",
  "overlayFile": "processed/regional-mu/2026/07/23/112000.webp",
  "status": "ready",
  "processingVersion": "regional-v1"
}
```

### 9.3 Manifiesto público por radar

```json
{
  "schemaVersion": 1,
  "radar": {
    "id": "regional-mu",
    "label": "Murcia",
    "kind": "regional"
  },
  "generatedAt": "2026-07-23T11:24:00Z",
  "latestProductTime": "2026-07-23T11:20:00Z",
  "frames": [
    {
      "productTime": "2026-07-23T11:10:00Z",
      "url": "/radar/regional-mu/20260723T111000Z.webp",
      "coordinates": [
        [-3.0, 40.0],
        [0.5, 40.0],
        [0.5, 36.5],
        [-3.0, 36.5]
      ]
    }
  ]
}
```

Las coordenadas del ejemplo son ficticias y nunca deben pasar a producción. Cada producto se calibrará y validará.

### 9.4 Publicación atómica

El worker escribirá primero un archivo temporal y lo renombrará al finalizar:

```text
manifest.json.tmp → manifest.json
```

Así, el frontend nunca leerá un manifiesto incompleto.

---

## 10. Ingesta y retención

### 10.1 Frecuencia de consulta

El worker consultará con una frecuencia superior a la de publicación, pero sin abusar de la API. La frecuencia inicial se configurará mediante variable de entorno y se ajustará tras observar la cadencia real.

### 10.2 Deduplicación

Cada descarga se identificará mediante SHA-256 del contenido original.

Si el hash coincide con el último fotograma del mismo radar:

- no se reprocesará;
- se actualizará la métrica de consulta;
- no se creará un fotograma duplicado.

### 10.3 Conservación

- Interfaz: últimas 3 horas.
- Almacenamiento inicial: 24 horas para facilitar diagnóstico.
- Retención configurable.
- Los originales y derivados se eliminarán de forma coordinada.
- Nunca se eliminará el último fotograma válido de un radar debido a un fallo temporal de AEMET.

---

## 11. Procesamiento de reflectividad

### 11.1 Salidas por fotograma

Durante el desarrollo, el procesador generará:

1. `raw.gif`: original.
2. `normalized.png`: raster normalizado.
3. `crop.png`: zona útil.
4. `classified.png`: píxeles clasificados como reflectividad.
5. `mask.png`: máscara alfa.
6. `overlay.png` o `overlay.webp`: salida transparente.
7. `preview.png`: composición sobre un mapa de prueba.
8. `report.json`: estadísticas y versión del procesamiento.

En producción solo serán públicos los derivados necesarios.

### 11.2 Máscara estática

Cada radar podrá tener una máscara versionada:

```text
config/masks/regional-mu-v1.png
```

La máscara eliminará:

- límites administrativos;
- logotipo;
- textos;
- leyenda;
- elementos que permanecen fijos.

La generación de una máscara deberá ser reproducible desde varias muestras y revisable visualmente. No se aceptará una edición manual opaca sin documentación.

### 11.3 Paleta

La paleta de reflectividad se guardará como configuración versionada.

El procesador no debe basarse únicamente en “todo píxel no negro”, porque incluiría elementos cartográficos y tipográficos.

Para cada color se definirá:

- valor o intervalo aproximado de dBZ cuando pueda determinarse;
- si es válido como reflectividad;
- tolerancia frente a pequeñas variaciones;
- tratamiento de colores ambiguos.

### 11.4 Georreferenciación

Para radares regionales se evaluará primero un modelo de proyección azimutal centrado en cada radar:

- centro geográfico del radar;
- centro y radio del círculo en píxeles;
- alcance físico del producto;
- orientación;
- proyección de salida.

La salida preferida será reproyectada a una referencia compatible con el mapa, evitando que MapLibre tenga que adivinar la proyección.

Métodos posibles, por orden de preferencia:

1. definición geométrica verificable a partir del centro, alcance y proyección;
2. georreferenciación mediante puntos de control y transformación documentada;
3. ajuste por cuatro esquinas solo si el error medido es aceptable.

La composición nacional tendrá su propia estrategia y no debe forzarse a utilizar el procesador regional.

### 11.5 Validación

Cada radar se considerará calibrado cuando:

- las fronteras visibles en una imagen de depuración coincidan razonablemente con el mapa base;
- el error se mida en varios puntos de control;
- la reflectividad no aparezca desplazada al hacer zoom;
- no queden logotipos, leyendas o líneas administrativas visibles;
- no se eliminen áreas meteorológicamente significativas de forma sistemática.

---

## 12. API pública estática

El frontend consumirá como mínimo:

```text
/radar/index.json
/radar/{radar-id}/manifest.json
/radar/{radar-id}/{timestamp}.webp
/status/health.json
```

`index.json` incluirá radares disponibles y estado. Los manifiestos no expondrán la API key ni URLs privadas de descarga.

---

## 13. Seguridad y secretos

- `AEMET_API_KEY` solo estará en el worker.
- Nunca se incluirá en JavaScript, logs públicos, commits o imágenes.
- `.env` estará ignorado.
- `.env.example` contendrá nombres y ejemplos no secretos.
- El frontend no llamará directamente a AEMET.
- Se establecerán timeouts, reintentos limitados y backoff.
- Los datos descargados se validarán por tamaño y tipo antes de procesarlos.
- El servidor web no permitirá listar directorios.

---

## 14. Rendimiento

Objetivos iniciales:

- interfaz interactiva rápidamente incluso si los fotogramas siguen cargando;
- precarga progresiva, priorizando el más reciente;
- cambio inmediato entre fotogramas ya descargados;
- imágenes optimizadas sin degradar la clasificación de colores;
- manifiestos pequeños y cacheables;
- nombres versionados o hash para caché larga;
- no descargar fotogramas de otros radares hasta que el usuario los seleccione;
- en móvil, limitar memoria y liberar texturas antiguas al cambiar de radar.

La elección entre una imagen completa georreferenciada, WebP con alfa, teselas raster o una capa WebGL personalizada se tomará con mediciones, no por anticipación.

---

## 15. Accesibilidad

- Controles utilizables con teclado.
- Etiquetas accesibles en botones.
- Estado de reproducción anunciado.
- No depender solo del color para indicar errores o fotograma activo.
- Contraste suficiente en controles superpuestos.
- Respetar `prefers-reduced-motion`, desactivando transiciones intensas.

---

## 16. Observabilidad y operación

El worker generará logs estructurados con:

- radar;
- endpoint;
- código HTTP;
- duración;
- hash;
- nuevo/duplicado;
- hora detectada;
- resultado del procesamiento;
- versión del procesador;
- error resumido sin secretos.

`health.json` mostrará, por radar:

- última consulta;
- último éxito;
- último fotograma;
- antigüedad;
- número de fotogramas publicables;
- estado del procesador.

Debe documentarse en `OPERATIONS.md`:

- cómo comprobar el servicio;
- cómo forzar una ingesta;
- cómo regenerar un fotograma;
- cómo reconstruir manifiestos;
- cómo rotar la API key;
- cómo añadir o deshabilitar un radar;
- cómo recuperar la última versión estable.

---

## 17. Estrategia de pruebas

### Worker

- respuestas AEMET simuladas;
- deduplicación;
- validación de tipo de archivo;
- cálculo de hash;
- tratamiento de timeouts y errores;
- clasificación de paleta;
- aplicación de máscaras;
- publicación atómica;
- retención;
- golden tests de imágenes pequeñas;
- pruebas de georreferenciación con puntos conocidos.

### Frontend

- lectura de manifiestos;
- selección de radar;
- selección por slider;
- botones individuales;
- reproducción, pausa y bucle;
- huecos temporales;
- estado retrasado;
- navegación por teclado;
- diseño móvil.

### Integración

- fixture de tres horas;
- worker genera manifiesto;
- Nginx sirve recursos;
- navegador reproduce todos los fotogramas;
- un fallo simulado de AEMET conserva el último bucle válido.

---

## 18. Criterios globales de finalización del MVP

El MVP estará terminado cuando:

1. la composición nacional y los radares regionales validados sean seleccionables;
2. la reflectividad se muestre sobre MapLibre sin el mapa gráfico original de AEMET;
3. se puedan recorrer las últimas tres horas con slider y botones individuales;
4. la reproducción sea fluida y no invente observaciones;
5. la hora y antigüedad sean claras;
6. la aplicación funcione correctamente en móvil y escritorio;
7. pueda instalarse como PWA;
8. la API key permanezca únicamente en backend;
9. la aplicación sobreviva a fallos temporales de AEMET;
10. existan pruebas, documentación operativa y despliegue reproducible con Podman/Quadlet;
11. se muestre la atribución correspondiente a AEMET y al mapa base.

---

## 19. Preguntas abiertas que deben resolverse experimentalmente

- Lista y códigos exactos de radares regionales operativos.
- Dimensiones y paleta real de cada producto.
- Cabeceras y metadatos disponibles en los GIF.
- Forma fiable de obtener la hora del producto.
- Centro geográfico, alcance y proyección de cada radar.
- Si todos los radares regionales comparten plantilla y geometría.
- Formato y geometría de la composición nacional.
- Calidad de WebP sin pérdida frente a PNG.
- Error de georreferenciación aceptable.
- Mejor técnica de renderizado para transiciones con MapLibre.
- Proveedor definitivo del mapa base y sus condiciones de uso.

Estas preguntas no deben resolverse mediante suposiciones. Cada respuesta se documentará en `DECISIONS.md` con muestras, mediciones o referencias.
