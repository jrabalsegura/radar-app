# CODEX_PROMPTS_POST_MVP.md — Fases posteriores al MVP

> Documento para continuar el desarrollo de la aplicación personal de radar AEMET una vez cerrado y estabilizado el MVP.
>
> Debe copiarse al repositorio como `docs/CODEX_PROMPTS_POST_MVP.md`.
>
> Las fases aquí definidas sustituyen la antigua “Fase 10 — Mejoras posteriores al MVP” genérica por varias fases pequeñas, verificables e independientes.

---

## 1. Objetivo post-MVP

Ampliar la aplicación sin perder sus principios originales:

- radar primero;
- interfaz rápida y minimalista;
- datos oficiales claramente diferenciados de los cálculos propios;
- ninguna API key en el navegador;
- ubicación procesada localmente siempre que sea posible;
- degradación elegante cuando una capa o cálculo no esté disponible;
- ninguna estimación presentada como observación oficial.

Las ampliaciones previstas son:

1. menú contextual de capas y opciones;
2. selección automática del radar según ubicación;
3. avisos oficiales AEMET sobre el mapa;
4. capa raster de rayos basada en la imagen oficial de AEMET;
5. nowcasting de precipitación claramente identificado como estimación propia;
6. cálculo aproximado de llegada de lluvia;
7. endurecimiento, evaluación y optimización conjunta.

Queda expresamente fuera del alcance de estas fases cualquier generación de imágenes entre observaciones para alterar la fluidez de la animación.

---

## 2. Decisiones funcionales importantes

### 2.1 Observaciones y estimaciones deben permanecer separadas

La aplicación manejará dos tipos principales de información:

#### Observaciones

Son productos derivados directamente de imágenes publicadas por AEMET:

```text
Observado · Datos AEMET
```

Incluyen:

- reflectividad regional;
- composición nacional;
- avisos oficiales;
- imagen oficial de rayos.

Aunque la aplicación procese, recorte, georreferencie o cambie el formato del producto, su origen seguirá siendo AEMET.

#### Nowcasting

Utiliza las observaciones más recientes para estimar hacia dónde podría desplazarse la precipitación en el futuro.

Ejemplo:

```text
12:10 observado
12:20 estimado
12:30 estimado
12:40 estimado
```

Debe identificarse siempre como:

```text
Estimación propia · no oficial de AEMET
```

No debe mezclarse visualmente con el histórico observado sin una separación clara en la línea temporal.

---

### 2.2 El nowcasting debe operar sobre reflectividad, no sobre colores RGBA

El cálculo no debe operar directamente sobre el PNG, GIF o WebP coloreado, porque eso puede:

- mezclar colores de la leyenda;
- crear tonos sin significado meteorológico;
- confundir transparencia con ausencia de precipitación;
- incorporar elementos gráficos residuales;
- dificultar la evaluación cuantitativa.

El pipeline debe conservar o reconstruir un campo escalar, por ejemplo:

```text
índice de paleta → valor aproximado de dBZ → cálculo → paleta visual
```

Si la conversión exacta a dBZ no está validada para un producto, se utilizará un índice ordinal documentado.

No se convertirá reflectividad a precipitación en `mm/h` sin una relación Z-R explícitamente seleccionada, justificada y validada.

---

### 2.3 La capa de rayos será sencilla y raster

La primera implementación utilizará directamente la imagen oficial disponible a través de AEMET.

No es necesario extraer cada descarga como punto individual, reconstruir coordenadas exactas ni crear un dataset vectorial.

La capa tendrá:

- toggle para mostrarla u ocultarla;
- georreferenciación;
- opacidad;
- hora del producto;
- antigüedad;
- atribución a AEMET;
- leyenda cuando el producto oficial la incluya o pueda reproducirse fielmente;
- estado actualizado, retrasado o error.

La aplicación no afirmará que permite seleccionar rayos individuales ni conocer la hora exacta de cada descarga si el producto oficial no lo proporciona.

Si la imagen ya codifica la antigüedad mediante colores, se conservará y explicará esa codificación. No se reinterpretarán los colores sin comprobar su significado.

---

### 2.4 Avisos oficiales AEMET

Los avisos se consumirán mediante CAP y se representarán como polígonos sobre MapLibre.

El pipeline deberá tratar correctamente:

- severidad;
- fenómeno;
- inicio y fin;
- descripción;
- instrucciones;
- uno o varios polígonos;
- idiomas;
- actualizaciones;
- expiraciones;
- referencias entre mensajes.

Un aviso oficial debe distinguirse tanto de la reflectividad como de cualquier estimación propia.

---

### 2.5 Ubicación y privacidad

La selección automática del radar y el cálculo de llegada aproximada utilizarán la ubicación solo tras una acción explícita.

Como regla general:

- las coordenadas se procesarán en el navegador;
- no se registrarán en logs;
- no se enviarán al servidor;
- podrá utilizarse un punto manual en el mapa;
- la selección manual de radar seguirá estando disponible;
- la denegación del permiso no limitará el uso normal de la aplicación.

---

## 3. Orden recomendado

```text
Fase 10  Infraestructura post-MVP y menú de capas
Fase 11  Selección automática de radar
Fase 12  Avisos oficiales CAP
Fase 13  Capa raster de rayos
Fase 14  Motor de nowcasting y evaluación
Fase 15  Integración del nowcasting
Fase 16  Llegada aproximada de lluvia
Fase 17  Integración, rendimiento y operación
```

Dependencias principales:

```text
Fase 10 ─┬─> Fase 11
         ├─> Fase 12
         └─> Fase 13

Fase 14 ─> Fase 15 ─> Fase 16

Todas ─────────────────> Fase 17
```

Las fases 11, 12 y 13 pueden desarrollarse en paralelo después de la Fase 10. Las fases 14, 15 y 16 deben mantenerse secuenciales.

---

# 4. Instrucción común para Codex

Pegar este bloque al principio de cada prompt.

```text
Estás trabajando en el repositorio ya existente de la aplicación personal de radar AEMET. El MVP ya está implementado y no debes sustituir su arquitectura sin una razón demostrable.

Antes de modificar nada:

1. Lee completos:
   - `docs/SPEC.md`;
   - `docs/ROADMAP.md`;
   - `docs/DECISIONS.md`;
   - `docs/OPERATIONS.md`, si existe;
   - `docs/DEPLOY.md`, si existe;
   - `docs/CODEX_PROMPTS_POST_MVP.md`.

2. Lee `README.md`, inspecciona la estructura real del repositorio y localiza:
   - el modelo actual de radar y fotograma;
   - los manifiestos;
   - el worker;
   - las capas MapLibre;
   - el sistema de estado;
   - las pruebas;
   - la configuración de despliegue.

3. Ejecuta:
   - `git status --short`;
   - los tests rápidos existentes;
   - el lint y el type checking aplicables.

4. Presenta antes de programar:
   - un resumen del estado real;
   - los componentes que reutilizarás;
   - los archivos que prevés modificar;
   - los riesgos de compatibilidad;
   - un plan corto y ordenado.

5. Implementa únicamente la fase solicitada y respeta sus exclusiones.

6. No incluyas:
   - API keys;
   - credenciales;
   - ubicaciones personales;
   - coordenadas ficticias en producción;
   - datos meteorológicos inventados;
   - dependencias grandes sin medición o justificación.

7. Mantén estas reglas:
   - las observaciones AEMET y los productos derivados deben distinguirse en datos y UI;
   - la ubicación del usuario se procesa localmente salvo necesidad justificada;
   - los errores no deben eliminar la última información válida;
   - toda tarea pesada del navegador debe ser cancelable y ejecutarse fuera del hilo principal;
   - toda salida derivada debe indicar versión del algoritmo, entradas y hora de generación;
   - cualquier dato cacheado debe invalidarse mediante hashes o versiones;
   - no implementes funciones de fases posteriores.

8. Si la documentación pública de AEMET o una dependencia puede haber cambiado, verifícala con fuentes oficiales antes de codificar. Registra el endpoint, formato y fecha de comprobación en `docs/DECISIONS.md`.

9. Para cambios de esquema:
   - versiona el esquema;
   - mantén compatibilidad o crea migración;
   - añade fixtures y pruebas;
   - no rompas silenciosamente manifiestos anteriores.

10. Para cualquier cálculo meteorológico propio:
    - añade pruebas retrospectivas;
    - conserva los observados sin modificar;
    - documenta las limitaciones;
    - no uses lenguaje de certeza si no existe evaluación;
    - permite declarar el cálculo no disponible.

Al terminar:

- ejecuta lint, tipado, tests y build;
- ejecuta los benchmarks o pruebas visuales exigidos por la fase;
- muestra los comandos y resultados;
- resume los archivos modificados;
- explica la validación manual paso a paso;
- enumera riesgos y limitaciones pendientes;
- actualiza `docs/DECISIONS.md` solo con decisiones realmente tomadas;
- propone un mensaje de commit;
- no realices despliegues destructivos ni avances a la fase siguiente;
- deja `git status --short` explicado.
```

---

# Fase 10 — Infraestructura post-MVP y menú contextual de capas

## Objetivo

Crear la infraestructura de interfaz y estado que utilizarán las nuevas capas y opciones, sin implementar todavía selección automática, avisos, rayos ni nowcasting.

## Alcance

- Menú contextual o panel inferior `Capas y opciones`.
- Registro tipado de capas.
- Toggles accesibles.
- Persistencia local de preferencias.
- Estados:
  - disponible;
  - cargando;
  - activo;
  - error;
  - no compatible;
  - deshabilitado por configuración.
- Leyenda y atribución por capa.
- Indicador de procedencia:
  - observación AEMET;
  - aviso oficial AEMET;
  - producto procesado;
  - estimación propia.
- Feature flags.
- Capacidad de desactivar una función desde configuración del servidor.
- Diseño responsive.
- Pruebas del menú y persistencia.
- Actualización de `SPEC.md` y `ROADMAP.md` con el alcance aprobado.

## Modelo propuesto

```ts
type LayerSourceKind =
  | "aemet-observation"
  | "aemet-warning"
  | "derived-observation"
  | "own-nowcast";

type OptionalLayerDefinition = {
  id: string;
  label: string;
  description: string;
  sourceKind: LayerSourceKind;
  attribution?: string;
  defaultEnabled: boolean;
  availability:
    | "available"
    | "loading"
    | "error"
    | "unsupported"
    | "disabled";
  legendId?: string;
};
```

La forma concreta debe adaptarse al código existente.

## Exclusiones

- No consultar CAP.
- No consultar rayos.
- No detectar automáticamente el radar.
- No generar futuro meteorológico.
- No mostrar toggles funcionales para características que todavía no existen.

## Criterios de aceptación

- El menú funciona en móvil y escritorio.
- Las preferencias se conservan localmente.
- Un toggle puede aparecer deshabilitado con una razón.
- Las capas oficiales y las estimaciones propias tienen etiquetas visuales distintas.
- No cambia el comportamiento del radar MVP.
- La arquitectura permite añadir nuevas capas sin duplicar lógica de MapLibre.
- Las funciones no disponibles pueden permanecer ocultas en producción.

## Prompt para Codex

```text
[PEGA AQUÍ LA INSTRUCCIÓN COMÚN]

Implementa únicamente la Fase 10: infraestructura post-MVP y menú contextual de capas.

Crea un sistema tipado y extensible para registrar capas opcionales y opciones de visualización. Añade un panel responsive `Capas y opciones`, toggles accesibles, persistencia local, estados de disponibilidad, leyendas y una diferenciación explícita entre observaciones AEMET, avisos oficiales, productos procesados y estimaciones propias.

Integra el sistema con la arquitectura real sin reescribir el mapa ni el reproductor del MVP. Añade feature flags y pruebas. Actualiza `docs/SPEC.md`, `docs/ROADMAP.md` y `docs/DECISIONS.md` solo con el diseño que quede implementado.

No conectes todavía selección automática, avisos, rayos ni nowcasting. No avances a la Fase 11.
```

---

# Fase 11 — Selección automática del radar según ubicación

## Objetivo

Seleccionar el radar regional más adecuado para la ubicación del usuario, manteniendo siempre control manual y fallback a la composición nacional.

## Comportamiento

1. Solicitar geolocalización solo tras una acción explícita.
2. Procesar la posición en el navegador.
3. Evaluar radares habilitados y actualizados.
4. Elegir un radar cuya cobertura validada incluya el punto.
5. En solapamientos, usar una función documentada que considere:
   - distancia al centro;
   - cobertura real;
   - frescura;
   - estado operativo.
6. Si ninguno es válido, seleccionar la composición nacional.
7. Mostrar:
   - `Radar seleccionado automáticamente: Madrid`;
   - una razón breve;
   - opción para cambiarlo.
8. Respetar la selección manual como override.
9. No cambiar repetidamente de radar durante la misma sesión.
10. No enviar ni registrar coordenadas personales.

## Configuración requerida

Cada radar debe disponer de una geometría de cobertura o información equivalente validada:

```json
{
  "radarId": "regional-ma",
  "coverage": {
    "type": "Polygon",
    "coordinates": []
  },
  "center": [-3.7, 40.4]
}
```

Las coordenadas del ejemplo no deben copiarse a producción sin validarlas.

No debe utilizarse únicamente la comunidad autónoma como cobertura, porque un radar puede cubrir varias comunidades y pueden existir solapamientos.

## Casos especiales

- permiso denegado;
- ubicación no disponible;
- ubicación fuera de España;
- ubicación en Canarias;
- varios radares con cobertura;
- radar más cercano sin datos recientes;
- selección manual previa;
- modo PWA sin permiso;
- usuario que revoca el permiso durante la sesión.

## Criterios de aceptación

- No hay geolocalización al cargar la aplicación.
- La ubicación no sale del navegador.
- El algoritmo es determinista y está probado.
- Existe fallback nacional.
- Una selección manual prevalece hasta que el usuario reactive el modo automático.
- El usuario sabe qué radar está seleccionado y por qué.
- La denegación del permiso no genera errores repetitivos.

## Prompt para Codex

```text
[PEGA AQUÍ LA INSTRUCCIÓN COMÚN]

Implementa únicamente la Fase 11: selección automática del radar según ubicación.

Reutiliza la configuración geográfica ya validada de los radares. Diseña un selector local y determinista que considere cobertura, distancia, frescura y estado del radar. Solicita permiso solo después de una acción explícita y no envíes ni persistas coordenadas personales.

Añade fallback a composición nacional, override manual persistente, explicación de la selección y pruebas para permisos, solapamientos, radar desactualizado, Canarias, exterior de cobertura y ausencia de ubicación.

No implementes avisos, rayos, nowcasting ni llegada de lluvia. No avances a la Fase 12.
```

---

# Fase 12 — Alertas oficiales AEMET mediante CAP

## Objetivo

Representar sobre MapLibre los avisos oficiales vigentes de AEMET con polígonos, colores, detalles y toggle.

## Fuente prevista

La fuente concreta debe verificarse contra la documentación oficial vigente antes de implementar.

El worker descargará la respuesta y el archivo CAP asociado, conservará el original y producirá un GeoJSON normalizado para el frontend.

## Pipeline

```text
AEMET OpenData
   ↓
paquete o documentos CAP
   ↓
XML CAP
   ↓
normalización de mensajes
   ↓
resolución de actualizaciones y expiraciones
   ↓
GeoJSON público
   ↓
MapLibre fill + line + panel de detalle
```

## Datos normalizados mínimos

```json
{
  "id": "cap-identifier",
  "source": "AEMET",
  "status": "Actual",
  "msgType": "Alert",
  "sent": "2026-07-28T08:00:00Z",
  "event": "Aviso de tormentas",
  "eventCode": "TO",
  "severity": "Severe",
  "level": "naranja",
  "certainty": "Likely",
  "effective": "...",
  "onset": "...",
  "expires": "...",
  "headline": "...",
  "description": "...",
  "instruction": "...",
  "areaDesc": "...",
  "geocode": "...",
  "geometry": {
    "type": "MultiPolygon",
    "coordinates": []
  }
}
```

## UI

- Toggle `Avisos AEMET`.
- Polígonos con nivel:
  - amarillo;
  - naranja;
  - rojo.
- Borde distinguible y relleno semitransparente.
- Panel de detalle:
  - fenómeno;
  - nivel;
  - zona;
  - vigencia;
  - probabilidad o certeza;
  - descripción;
  - instrucciones;
  - `Fuente: AEMET`.
- Leyenda.
- Estado de última actualización.
- Accesibilidad sin depender solo del color.
- Opción de cerrar el panel sin desactivar la capa.

## Reglas CAP importantes

- Parsear namespaces.
- Preferir el bloque en español cuando exista.
- Tratar mensajes de actualización y referencias.
- Excluir avisos expirados.
- No duplicar un mismo aviso por idiomas.
- Convertir correctamente el orden de coordenadas a GeoJSON.
- Conservar múltiples polígonos.
- Validar geometrías.
- No simplificar polígonos sin medir el error.
- Conservar el último conjunto válido si falla la actualización.

## Criterios de aceptación

- Los avisos vigentes aparecen una sola vez.
- Actualizaciones y expiraciones se reflejan correctamente.
- Los polígonos se alinean con el mapa.
- La fuente y vigencia son visibles.
- Un fallo de AEMET conserva el último conjunto válido, marcado como retrasado.
- El toggle no afecta al radar.
- Un XML inválido no reemplaza la última publicación correcta.

## Prompt para Codex

```text
[PEGA AQUÍ LA INSTRUCCIÓN COMÚN]

Implementa únicamente la Fase 12: alertas oficiales AEMET mediante CAP.

Verifica primero la documentación oficial y el formato real del producto CAP vigente. Implementa en el worker la descarga segura, conservación del original, extracción de XML, parseo con namespaces, selección del bloque en español, normalización, resolución de actualizaciones, referencias, expiraciones y mensajes duplicados.

Publica un GeoJSON versionado y un estado de salud. En el frontend añade una capa MapLibre con toggle, polígonos por nivel, leyenda y panel de detalle accesible. Convierte correctamente el orden de coordenadas a GeoJSON.

Prueba archivos con varios idiomas, MultiPolygon, actualizaciones, avisos expirados, geometrías inválidas y fallos temporales.

No implementes rayos, nowcasting ni llegada de lluvia. No avances a la Fase 13.
```

---

# Fase 13 — Capa raster de rayos

## Objetivo

Añadir al mapa una capa sencilla basada en la imagen oficial de rayos proporcionada por AEMET.

## Enfoque

No se intentará obtener un punto vectorial por descarga.

La aplicación tratará el producto como una imagen raster oficial:

```text
AEMET OpenData
      ↓
imagen de rayos
      ↓
validación y archivo
      ↓
recorte o limpieza mínima si es necesaria
      ↓
georreferenciación
      ↓
imagen optimizada
      ↓
MapLibre image/raster source
```

## Inspección inicial necesaria

Antes de integrarla, comprobar:

- endpoint oficial vigente;
- formato real;
- MIME;
- dimensiones;
- transparencia;
- paleta;
- timestamp;
- periodicidad observada;
- mapa, bordes, leyenda o textos incrustados;
- cobertura geográfica;
- proyección;
- si todos los fotogramas comparten geometría.

Esta inspección debe ser breve y orientada a integrar el raster, no a reconstruir datos individuales.

## Procesamiento

Preferencia:

1. conservar la imagen tal como la publica AEMET cuando resulte legible;
2. eliminar únicamente marcos, logos o leyendas si impiden superponerla;
3. no modificar los colores meteorológicos;
4. crear transparencia solo cuando sea segura;
5. georreferenciar mediante configuración versionada;
6. generar una previsualización de validación sobre el mapa.

Si el producto oficial ya incluye una base cartográfica que no puede eliminarse limpiamente, se podrá mostrar como una capa raster completa en una vista adecuada, siempre que la experiencia sea comprensible.

## Manifiesto sugerido

```json
{
  "schemaVersion": 1,
  "product": "aemet-lightning-map",
  "source": "AEMET",
  "official": true,
  "productTime": "2026-07-28T09:00:00Z",
  "retrievedAt": "2026-07-28T09:03:00Z",
  "imageUrl": "/layers/lightning/current.webp",
  "coordinates": [],
  "legend": {
    "kind": "embedded"
  },
  "status": "ready"
}
```

Las coordenadas se obtendrán mediante calibración y no se introducirán valores provisionales en producción.

## UI

- Toggle `Rayos`.
- Desactivado por defecto en la primera versión, salvo decisión de producto posterior.
- Control de opacidad opcional.
- Hora del producto.
- Texto de antigüedad.
- Estado:
  - actualizado;
  - retrasado;
  - sin datos;
  - error.
- Leyenda oficial o explicación breve del código de colores.
- Atribución:
  - `Datos de rayos: AEMET`.
- Información visible de la ventana temporal representada por la imagen.
- Sin popups por descarga individual.

## Caché y fallos

- Conservar el último producto válido.
- No reemplazarlo por una respuesta inválida.
- Hash para evitar reprocesar imágenes iguales.
- Caché del navegador con invalidación por URL versionada o hash.
- Mostrar claramente cuándo la capa está desactualizada.
- El fallo de esta capa nunca debe afectar al radar.

## Criterios de aceptación

- La imagen se alinea razonablemente con el mapa.
- El código de colores conserva el significado oficial.
- El usuario conoce la hora y ventana temporal del producto.
- El toggle funciona sin recargar el mapa.
- La capa puede activarse junto al radar y los avisos.
- No se anuncian posiciones o tiempos individuales que la fuente no proporciona.
- El último producto válido sobrevive a un fallo temporal.

## Prompt para Codex

```text
[PEGA AQUÍ LA INSTRUCCIÓN COMÚN]

Implementa únicamente la Fase 13: capa raster de rayos.

Verifica el endpoint oficial vigente de AEMET y descarga una muestra real. Inspecciona formato, dimensiones, paleta, timestamp, cobertura y geometría. Trata el producto como una imagen raster oficial: no intentes extraer rayos individuales ni crear un dataset vectorial.

Implementa en el worker:
- descarga segura;
- validación;
- hash y deduplicación;
- conservación del original;
- limpieza mínima solo cuando sea necesaria;
- georreferenciación versionada;
- optimización;
- manifiesto y health.

Integra en MapLibre una capa con toggle, opacidad opcional, hora, antigüedad, leyenda, atribución y estados de error. Conserva el último producto válido si AEMET falla.

Añade pruebas de contenido inválido, duplicados, timestamp ausente, producto retrasado y fallo temporal.

No implementes nowcasting ni llegada de lluvia. No avances a la Fase 14.
```

---

# Fase 14 — Motor de nowcasting y evaluación retrospectiva

## Objetivo

Construir un motor experimental de extrapolación de reflectividad y demostrar su utilidad mediante backtesting antes de exponerlo al usuario.

## Alcance inicial

- Solo radares regionales con cadencia y georreferenciación validadas.
- Utilizar varias observaciones recientes.
- Horizonte inicial prudente:
  - +10 minutos;
  - +20 minutos;
  - +30 minutos.
- Ampliar el horizonte solo si la evaluación lo justifica.
- Salida en campo escalar de reflectividad.
- No modificar ni reemplazar observaciones.
- No publicar todavía el resultado en la interfaz principal.

## Métodos candidatos

Empezar por métodos simples y explicables:

- persistencia como baseline;
- desplazamiento global como baseline;
- flujo óptico Lucas–Kanade;
- flujo óptico Farnebäck;
- advección semilagrangiana;
- extrapolación mediante una biblioteca meteorológica mantenida, si encaja con la arquitectura.

No introducir modelos de aprendizaje automático en esta fase.

## Backtesting

Usar secuencias históricas:

```text
t-30, t-20, t-10, t0 → estimar t+10, t+20, t+30
                                  ↓
                      comparar con observaciones reales
```

Casos:

- precipitación estratiforme;
- convección;
- crecimiento rápido;
- disipación;
- movimiento lento;
- ausencia de precipitación;
- huecos;
- bordes de cobertura;
- ecos espurios.

## Métricas

Evaluar por varios umbrales de reflectividad:

- FSS por escala espacial;
- CSI;
- precision y recall del área con precipitación;
- error del tiempo de llegada en puntos de prueba;
- comparación con persistencia;
- comparación con desplazamiento global;
- tiempo de ejecución;
- memoria;
- porcentaje de casos sin campo de movimiento fiable.

No declarar un nivel de confianza hasta disponer de resultados suficientes.

## Control de calidad

El motor debe poder devolver:

```json
{
  "status": "unavailable",
  "reason": "insufficient_motion_signal"
}
```

Razones posibles:

- menos de N observaciones;
- hueco excesivo;
- muy poca precipitación;
- movimiento inestable;
- cobertura insuficiente;
- artefacto de radar;
- error de cálculo.

## Salida sugerida

```json
{
  "schemaVersion": 1,
  "radarId": "regional-ma",
  "generatedAt": "...",
  "baseProductTime": "...",
  "algorithm": "extrapolation-v1",
  "inputFrameHashes": [],
  "leadMinutes": [10, 20, 30],
  "quality": {
    "status": "experimental",
    "motionSignal": 0.0
  },
  "frames": []
}
```

## Criterios de aceptación

- Backtesting reproducible.
- Comparación con baselines.
- Métricas por horizonte.
- El motor sabe rechazar casos.
- Entradas y algoritmo quedan trazables.
- Existe ADR sobre horizonte y método.
- No se expone todavía al usuario como función estable.
- Un resultado malo no afecta al histórico observado.

## Prompt para Codex

```text
[PEGA AQUÍ LA INSTRUCCIÓN COMÚN]

Implementa únicamente la Fase 14: motor experimental de nowcasting y evaluación retrospectiva.

Trabaja con campos escalares de reflectividad de radares regionales validados. Compara persistencia, desplazamiento global, Lucas–Kanade, Farnebäck y cualquier alternativa adicional que pueda justificarse sin introducir aprendizaje automático.

Genera extrapolaciones prudentes y evalúalas contra observaciones posteriores mediante backtesting. Incluye FSS por escalas y umbrales, CSI, precision/recall de área, tiempo de cálculo, memoria y porcentaje de casos rechazados.

El motor debe poder declarar el cálculo no disponible con una razón explícita. No conviertas a mm/h sin una relación validada. No integres todavía la función en la interfaz principal.

Termina con un ADR que elija método, horizonte, requisitos mínimos y limitaciones. No avances a la Fase 15.
```

---

# Fase 15 — Integración del nowcasting en la interfaz

## Objetivo

Mostrar el nowcasting validado como una extensión claramente separada de las observaciones oficiales.

## UI

Toggle:

```text
Estimación próxima media hora
Cálculo propio basado en el desplazamiento reciente del radar.
```

Separación temporal:

```text
Pasado observado                 Futuro estimado
09:20 ... 11:20 | +10  +20  +30
                 ↑ ahora
```

Reglas visuales:

- línea divisoria en `ahora`;
- área futura con fondo o estilo distinto;
- etiquetas `estimado`;
- marca permanente `No oficial AEMET`;
- hora base;
- algoritmo y versión disponibles en detalles;
- estado de calidad;
- horizonte reducido cuando la calidad sea insuficiente;
- ausencia de resultado cuando el motor rechace el caso.

## Interacción

- El toggle activa el cálculo solo para el radar actual.
- Al cambiar de radar, cancelar o solicitar un nuevo cálculo.
- No ejecutar continuamente si no cambia la observación base.
- Cachear por hashes y versión.
- Mantener el histórico observado intacto.
- Invalidar el resultado al llegar una nueva observación.
- Desactivar automáticamente en radares no compatibles.
- Mostrar un estado útil mientras se calcula.

## Textos permitidos

```text
Estimación propia
Movimiento extrapolado desde las últimas imágenes
Calidad limitada
No hay una estimación fiable disponible
Basado en el radar de las 11:20
```

Evitar:

```text
Va a llover
Predicción de AEMET
Radar futuro real
Garantizado
```

## Criterios de aceptación

- Ningún usuario puede confundir observado y estimado.
- El motor no disponible no rompe el timeline.
- Cambiar de radar cancela trabajo.
- El resultado se invalida al aparecer una observación nueva.
- Existe detalle de método y limitaciones.
- No se ocultan casos rechazados.
- El radar básico sigue funcionando con el toggle desactivado.
- Existen pruebas E2E para carga, éxito, rechazo, error e invalidación.

## Prompt para Codex

```text
[PEGA AQUÍ LA INSTRUCCIÓN COMÚN]

Implementa únicamente la Fase 15: integración del nowcasting en la interfaz, usando el método y horizonte aprobados en la Fase 14.

Añade un toggle independiente, separa pasado observado y futuro estimado en la línea temporal y marca permanentemente la estimación como propia y no oficial de AEMET. Muestra hora base, horizonte, estado de calidad y motivos de indisponibilidad.

Implementa caché por hashes, invalidación al llegar una nueva observación, cancelación al cambiar de radar y estados completos de carga, error y no disponible.

Mantén intacta la reproducción histórica del MVP. Añade pruebas E2E que demuestren que observado y estimado no se confunden.

No implementes todavía el aviso de llegada de lluvia. No avances a la Fase 16.
```

---

# Fase 16 — Aviso aproximado de llegada de lluvia

## Objetivo

Estimar si una zona cercana a la ubicación seleccionada podría recibir precipitación dentro del horizonte de nowcasting.

## Privacidad

- Usar geolocalización local.
- No enviar la posición exacta al servidor si el cálculo puede hacerse en cliente.
- Si el nowcasting se produce en backend, preferir descargar el campo y evaluar la ubicación localmente.
- No registrar coordenadas.
- Permitir seleccionar un punto manual en el mapa.
- Permitir borrar la ubicación o punto seleccionado.

## Método inicial

1. Obtener ubicación o punto manual.
2. Crear un radio configurable alrededor, no evaluar un único píxel.
3. Evaluar cada horizonte del nowcast.
4. Aplicar un umbral de reflectividad validado.
5. Exigir cobertura mínima o presencia consistente.
6. Calcular el primer intervalo plausible.
7. Ajustar el resultado según la calidad del nowcast.
8. Devolver un rango, no un minuto exacto.

Ejemplo:

```json
{
  "status": "possible-arrival",
  "windowMinutes": [20, 30],
  "threshold": {
    "kind": "reflectivity",
    "value": 18
  },
  "confidence": "limited",
  "baseProductTime": "...",
  "algorithmVersion": "...",
  "message": "La precipitación podría alcanzar la zona en unos 20–30 minutos."
}
```

## Estados

```text
precipitación detectada ahora
posible llegada en 10–20 min
posible llegada en 20–30 min
sin estimación fiable
fuera de cobertura
sin señal de precipitación dentro del horizonte
nowcasting desactivado
```

`Sin señal dentro del horizonte` no equivale a `no va a llover`.

## UI

- Toggle subordinado al nowcasting.
- Punto o radio visible opcionalmente.
- Tarjeta discreta.
- Hora del observado base.
- Rango estimado.
- Calidad.
- Texto `Estimación propia`.
- Botón para cambiar el punto.
- Posibilidad de ocultar el radio.
- Estado cuando la ubicación no está disponible.

## Notificaciones

La primera implementación será solo dentro de la aplicación.

Las notificaciones del sistema o push quedan fuera de alcance porque implican:

- permisos adicionales;
- ejecución en segundo plano;
- periodicidad;
- consumo;
- posibles falsas alarmas;
- infraestructura adicional.

## Backtesting específico

- error absoluto de llegada;
- tasa de avisos falsos;
- tasa de llegadas no detectadas;
- resultados por umbral;
- resultados por radio;
- resultados por horizonte;
- diferencias entre precipitación débil e intensa.

## Criterios de aceptación

- Se devuelve un rango y no falsa precisión.
- Se distingue falta de señal de falta de fiabilidad.
- No se emite aviso cuando el nowcast está rechazado.
- La ubicación permanece local y descartable.
- La validación retrospectiva está documentada.
- Los textos son prudentes y accesibles.
- El usuario puede usar un punto manual sin conceder GPS.

## Prompt para Codex

```text
[PEGA AQUÍ LA INSTRUCCIÓN COMÚN]

Implementa únicamente la Fase 16: aviso aproximado de llegada de lluvia.

Permite usar ubicación local o un punto manual. Evalúa el nowcasting aprobado dentro de un radio configurable y con umbrales de reflectividad validados. Exige cobertura mínima y devuelve rangos temporales, nunca falsa precisión.

Distingue claramente:
- precipitación actual;
- posible llegada;
- sin señal dentro del horizonte;
- sin estimación fiable;
- fuera de cobertura.

Añade backtesting de error de llegada, falsos avisos y eventos no detectados. No registres coordenadas. Implementa solo avisos dentro de la aplicación, sin push ni ejecución en segundo plano.

No avances a la Fase 17.
```

---

# Fase 17 — Integración, rendimiento, operación y revisión final

## Objetivo

Asegurar que todas las funciones post-MVP coexisten sin degradar la simplicidad, estabilidad o rendimiento de la aplicación.

## Matriz de combinaciones

Probar:

```text
radar
radar + avisos
radar + rayos
radar + nowcasting
radar + llegada
radar + avisos + rayos
radar + avisos + nowcasting
radar + rayos + nowcasting
todas las capas compatibles
cambio rápido entre radares
móvil con memoria limitada
offline parcial
AEMET caído
worker reiniciado
respuesta CAP inválida
imagen de rayos inválida
motor de nowcasting rechazando el caso
```

## Requisitos

- Presupuestos de CPU, memoria y red.
- Cancelación global de tareas.
- Priorización:
  1. radar observado actual;
  2. histórico del radar;
  3. avisos;
  4. rayos;
  5. nowcasting.
- Feature flags operativas.
- Health ampliado por producto.
- Logs de duración y rechazo.
- Retención de derivados.
- Limpieza de cachés.
- Evitar fugas de fuentes, capas y texturas MapLibre.
- Pruebas de actualización PWA.
- Runbook de fallo de AEMET.
- Runbook de CAP inválido.
- Runbook de imagen de rayos retrasada.
- Runbook de algoritmo degradado.
- Rollback individual de cada función.
- Revisión de atribuciones.
- Revisión de textos meteorológicos.
- Revisión de accesibilidad.
- Revisión de privacidad.
- Documentación de limitaciones.

## Objetivo de producto

La aplicación debe seguir abriendo directamente en el radar.

Las funciones avanzadas estarán en el menú contextual y no convertirán la pantalla principal en un panel saturado.

El orden de importancia de la interfaz será:

```text
radar actual
hora y estado
timeline histórico
controles básicos
capas opcionales
estimaciones propias
```

## Criterios de aceptación

- El radar básico sigue funcionando aunque fallen todas las funciones opcionales.
- No hay tareas huérfanas al cambiar de radar.
- La memoria vuelve cerca del baseline tras desactivar capas.
- Los estados desactualizados son visibles.
- Las funciones pueden deshabilitarse mediante feature flags.
- Existe documentación operativa completa.
- Se ha probado rollback.
- Las atribuciones son correctas.
- Observado y estimado son inequívocos.
- El menú no oculta los controles básicos.
- La aplicación sigue siendo utilizable en móvil.

## Prompt para Codex

```text
[PEGA AQUÍ LA INSTRUCCIÓN COMÚN]

Implementa únicamente la Fase 17: integración, rendimiento, operación y revisión final post-MVP.

Construye una matriz automatizada y manual de combinaciones entre radar, avisos, rayos, nowcasting y llegada de lluvia. Mide CPU, memoria, red, FPS, cancelación y liberación de recursos.

Añade presupuestos de rendimiento, feature flags operativas, health detallado, retención de derivados, limpieza de cachés, prevención de fugas de MapLibre y runbooks de fallo y rollback.

Revisa accesibilidad, privacidad, atribuciones y todos los textos que distinguen observación oficial y estimación propia.

El radar básico debe continuar funcionando si cualquier función opcional falla o se desactiva. No añadas nuevas funciones durante esta fase.
```

---

# 5. ADR sugeridas

Añadirlas solo cuando cada decisión haya sido comprobada.

```text
ADR-008 — Registro de capas opcionales y procedencia
ADR-009 — Selección automática y privacidad de ubicación
ADR-010 — Modelo normalizado de avisos CAP
ADR-011 — Integración raster de la imagen oficial de rayos
ADR-012 — Georreferenciación y caché de la capa de rayos
ADR-013 — Método y horizonte de nowcasting
ADR-014 — Métricas y criterio de rechazo del nowcasting
ADR-015 — Representación visual del futuro estimado
ADR-016 — Método de llegada aproximada de lluvia
ADR-017 — Presupuestos de rendimiento post-MVP
```

---

# 6. Nuevos tipos de producto sugeridos

El esquema existente debe evolucionar de forma versionada.

```ts
type TimelineFrameKind =
  | "observation"
  | "nowcast";

type TimelineFrame = {
  id: string;
  kind: TimelineFrameKind;
  nominalTime: string;
  sourceProductTime?: string;
  baseProductTime?: string;
  source: "AEMET" | "own-processing";
  official: boolean;
  algorithm?: {
    name: string;
    version: string;
  };
  inputFrameHashes?: string[];
  quality?: {
    status: "valid" | "limited" | "unavailable";
    reason?: string;
  };
  url?: string;
};

type MapOverlayKind =
  | "radar"
  | "lightning-raster"
  | "aemet-warning";

type MapOverlayManifest = {
  schemaVersion: number;
  id: string;
  kind: MapOverlayKind;
  source: "AEMET" | "own-processing";
  official: boolean;
  productTime?: string;
  generatedAt: string;
  status: "ready" | "stale" | "unavailable" | "error";
  attribution: string;
  dataUrl: string;
  legend?: {
    kind: "embedded" | "structured" | "none";
    url?: string;
  };
};
```

Un nowcast debe referenciar la observación base y las entradas utilizadas para estimar el movimiento.

La imagen de rayos seguirá siendo un overlay independiente y no un conjunto de fotogramas del radar.

---

# 7. Estrategia de ramas sugerida

```text
feature/phase-10-layer-framework
feature/phase-11-auto-radar
feature/phase-12-cap-alerts
feature/phase-13-lightning-raster
experiment/phase-14-nowcast-engine
feature/phase-15-nowcast-ui
feature/phase-16-rain-arrival
chore/phase-17-post-mvp-hardening
```

No mezclar en una misma rama el experimento del motor de nowcasting y su integración final en la interfaz.

---

# 8. Fuentes técnicas que deben verificarse durante el desarrollo

- Especificación OpenAPI vigente de AEMET OpenData.
- Producto vigente de avisos CAP.
- Producto vigente de mapa de rayos.
- Documento oficial del formato CAP utilizado por AEMET.
- Especificación OASIS CAP correspondiente.
- Documentación de la biblioteca seleccionada para:
  - movimiento;
  - extrapolación;
  - verificación espacial;
  - FSS.
- Documentación oficial de MapLibre para:
  - raster sources;
  - image sources;
  - fill;
  - line;
  - GeoJSON sources;
  - gestión y eliminación de recursos.
- Documentación oficial de Web Workers si alguna parte del nowcasting se ejecuta en cliente.

Toda comprobación debe registrar fecha, versión y resultado en la documentación del proyecto.

---

# 9. Criterio de cierre post-MVP

El desarrollo post-MVP podrá considerarse cerrado cuando:

1. el radar se seleccione automáticamente sin perder el control manual;
2. los avisos oficiales puedan activarse y consultarse;
3. la imagen oficial de rayos pueda activarse como capa raster;
4. el nowcasting se muestre únicamente cuando sea evaluable;
5. la llegada aproximada utilice rangos y lenguaje prudente;
6. todas las capas tengan atribución, hora y estado;
7. el radar básico funcione aunque fallen las funciones opcionales;
8. ubicación y preferencias se traten de forma privada;
9. existan pruebas, health, logs, runbooks y rollback;
10. la interfaz continúe siendo sencilla y centrada en el radar.
