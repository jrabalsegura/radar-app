# CODEX_PROMPTS.md — Prompts de ejecución por fase

## Instrucción común para todas las fases

Pegar este bloque al principio de cada prompt:

```text
Estás trabajando en el repositorio de la aplicación personal de radar AEMET.

Antes de modificar nada:
1. Lee completos `docs/SPEC.md`, `docs/ROADMAP.md` y `docs/DECISIONS.md`.
2. Lee `README.md`, el estado actual del repositorio y las pruebas existentes.
3. Ejecuta `git status --short`.
4. Identifica exactamente la fase solicitada y sus exclusiones.
5. No implementes funciones de fases posteriores.
6. No introduzcas dependencias grandes sin justificar la necesidad.
7. No incluyas secretos, API keys ni coordenadas ficticias en código de producción.
8. Conserva compatibilidad con lo ya validado.
9. Si descubres una incertidumbre técnica, no la ocultes: documéntala y crea una prueba o salida de diagnóstico.
10. Trabaja en cambios pequeños y coherentes.

Al terminar:
- ejecuta lint, tipado, tests y build aplicables;
- muestra los comandos ejecutados y su resultado;
- resume los archivos modificados;
- explica cómo validar manualmente la fase;
- enumera limitaciones o preguntas abiertas;
- actualiza documentación solo cuando el cambio sea real;
- no empieces la fase siguiente;
- deja `git status --short` explicado.
```

---

## Prompt Fase 0

```text
[PEGA AQUÍ LA INSTRUCCIÓN COMÚN]

Implementa únicamente la Fase 0 descrita en `docs/ROADMAP.md`.

Crea la estructura inicial del monorepo, el frontend React/TypeScript/Vite y el paquete Python del worker. Configura herramientas de calidad y pruebas mínimas ejecutables. Añade `.env.example` sin secretos, una estrategia de Git documentada y comandos de desarrollo consistentes.

No llames a AEMET, no implementes el mapa y no proceses imágenes.

Antes de escribir código, presenta un plan corto basado en el estado real del repositorio. Después ejecútalo. No avances a la Fase 1.
```

---

## Prompt Fase 1

```text
[PEGA AQUÍ LA INSTRUCCIÓN COMÚN]

Implementa únicamente la Fase 1: spike de ingesta AEMET y archivo de originales.

Empieza por Murcia y la composición nacional. Crea un cliente HTTP robusto que lea `AEMET_API_KEY` del entorno, consulte el endpoint, descargue inmediatamente la URL de `datos`, valide la respuesta y almacene el original con SHA-256.

Añade un comando `fetch-once` y un informe JSON que recoja cabeceras relevantes, MIME real, formato detectado, dimensiones, modo, paleta, metadatos internos y tiempos. Investiga de forma programática las opciones para obtener `productTime`, sin depender todavía de OCR general.

Implementa fixtures y pruebas para éxito, duplicado, timeout, 401, 429, 503, contenido inválido y fallo al descargar la URL efímera.

No extraigas reflectividad, no georreferencies y no construyas frontend funcional. No avances a la Fase 2.
```

---

## Prompt Fase 2

```text
[PEGA AQUÍ LA INSTRUCCIÓN COMÚN]

Implementa únicamente la Fase 2: historial y manifiestos.

Añade ejecución periódica configurable, reintentos limitados, backoff, retención inicial de 24 horas, selección de las últimas 3 horas y 50 minutos, detección de huecos, publicación atómica de manifiestos y `health.json`.

Trabaja solo con los originales de Murcia y composición nacional. Crea una CLI para reconstruir manifiestos desde disco. Prueba secuencias completas, duplicadas, desordenadas, con huecos y con datos retrasados.

No proceses la reflectividad, no uses MapLibre y no implementes animación. No avances a la Fase 3.
```

---

## Prompt Fase 3

```text
[PEGA AQUÍ LA INSTRUCCIÓN COMÚN]

Implementa únicamente la Fase 3: extracción de reflectividad del radar regional de Murcia.

Construye una herramienta de análisis reproducible para:
- normalizar el GIF;
- recortar la zona útil;
- enumerar y visualizar la paleta;
- generar o aplicar una máscara estática versionada;
- clasificar píxeles de reflectividad;
- eliminar fondo, círculo exterior, límites administrativos, logotipo, textos y leyenda;
- producir una salida RGBA transparente;
- generar imágenes de depuración y un informe JSON.

Empieza por colores inequívocos y trata el amarillo ambiguo de forma explícita y documentada. Añade golden tests pequeños y un comando que regenere todas las salidas de una muestra.

No georreferencies aún y no generalices a otros radares. Si una muestra no permite resolver una regla con seguridad, documenta la limitación en vez de ocultarla. No avances a la Fase 4.
```

---

## Prompt Fase 4

```text
[PEGA AQUÍ LA INSTRUCCIÓN COMÚN]

Implementa únicamente la Fase 4: georreferenciación de Murcia y mapa mínimo.

Investiga usando las muestras y referencias verificables el centro, alcance, orientación y proyección del producto. Crea una configuración de calibración con puntos de control reales y una salida reproyectada compatible con MapLibre.

Añade un frontend mínimo con MapLibre que muestre un único fotograma procesado, control de opacidad y una vista de depuración. Calcula y documenta el error de alineación en varios puntos.

No uses coordenadas aproximadas como definitivas. No implementes timeline, PWA ni otros radares. Registra la decisión de proyección en `docs/DECISIONS.md`. No avances a la Fase 5.
```

---

## Prompt Fase 5

```text
[PEGA AQUÍ LA INSTRUCCIÓN COMÚN]

Implementa únicamente la Fase 5: reproducción de las últimas 3 horas y 50 minutos para Murcia.

Consume el manifiesto real. Añade:
- slider temporal;
- botones individuales con hora;
- play/pause;
- velocidades lenta, normal y rápida;
- bucle con pausa en el último fotograma;
- navegación con flechas;
- representación de huecos;
- continuidad visual en huecos conservando la última imagen real y su hora;
- precarga priorizada;
- transición corta de opacidad entre observaciones;
- soporte para `prefers-reduced-motion`.

El slider, botones, texto de hora y mapa deben permanecer sincronizados. No interpoles valores meteorológicos. No generalices aún a todos los radares. No avances a la Fase 6.
```

---

## Prompt Fase 6

```text
[PEGA AQUÍ LA INSTRUCCIÓN COMÚN]

Implementa únicamente la Fase 6: generalización a todos los radares regionales validados.

Crea `config/radars.yaml` y una arquitectura de plugins o estrategias configurables para crop, máscara, paleta y georreferenciación. Añade una herramienta de calibración y validación por radar.

Incorpora el selector de radar, ajuste automático de vista, estado y último
fotograma. Escalona las consultas para respetar la API. Mantén visibles y
seleccionables todos los radares del contrato OpenAPI, incluidos los
temporalmente sin datos. Solo publica capas meteorológicas de muestras que
superen los criterios de validación.

No asumas que todas las imágenes son idénticas. No añadas todavía la composición nacional al selector final. No avances a la Fase 7.
```

---

## Prompt Fase 7

```text
[PEGA AQUÍ LA INSTRUCCIÓN COMÚN]

Implementa únicamente la Fase 7: composición nacional.

Analiza el producto nacional como formato independiente. Crea su procesador, máscara, paleta, georreferenciación, manifiesto e integración en el selector. Respeta su cadencia real y representa huecos sin duplicar artificialmente fotogramas.

Documenta cobertura, tratamiento de Península/Baleares/Canarias y limitaciones verificadas. Compara visualmente el resultado con una referencia oficial.

No añadas funciones meteorológicas nuevas. No avances a la Fase 8.
```

---

## Prompt Fase 8

```text
[PEGA AQUÍ LA INSTRUCCIÓN COMÚN]

Implementa únicamente la Fase 8: UX final, PWA y robustez.

Completa diseño responsive, PWA, pantalla completa, geolocalización local, opacidad, estados actualizado/retrasado/error, caché del último manifiesto válido, accesibilidad, optimización de memoria y pruebas Playwright de los flujos principales.

Mantén la interfaz minimalista y centrada en el radar. No añadas cuentas, alertas, nowcasting ni otras capas. No avances a la Fase 9.
```

---

## Prompt Fase 9

```text
[PEGA AQUÍ LA INSTRUCCIÓN COMÚN]

Implementa únicamente la Fase 9: operación, seguridad y despliegue.

Prepara Containerfiles, unidades Quadlet, timer o scheduler, volúmenes persistentes, Nginx, HTTPS, health checks, rotación de logs, retención y procedimientos de backup/rollback.

El destino es el servidor al que se accede con `ssh remote`, pero antes de ejecutar cambios remotos:
1. inspecciona y documenta los archivos que se van a instalar;
2. muestra los comandos;
3. solicita aprobación explícita para cualquier acción destructiva o cambio en producción.

Completa `docs/DEPLOY.md` y `docs/OPERATIONS.md`. Verifica que `AEMET_API_KEY` nunca llegue al frontend ni al repositorio.

No implementes mejoras de la Fase 10.
```
