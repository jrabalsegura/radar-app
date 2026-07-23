# ROADMAP.md — Desarrollo por fases

> Cada fase se implementa en una rama independiente, se valida y se integra antes de comenzar la siguiente.
>
> Codex no debe implementar trabajo de fases posteriores, aunque parezca conveniente.

---

## Fase 0 — Repositorio, documentación y disciplina de trabajo

### Objetivo

Crear un repositorio mantenible, con contexto persistente, herramientas de calidad y una base mínima de frontend y worker sin funcionalidad meteorológica.

### Alcance

- Inicializar Git.
- Crear la estructura definida en `SPEC.md`.
- Añadir `README.md`, `.gitignore`, `.editorconfig` y `.env.example`.
- Copiar y revisar los documentos de `docs/`.
- Crear esqueleto React + TypeScript + Vite.
- Crear paquete Python del worker.
- Configurar lint, formato, tipado y pruebas.
- Añadir comandos uniformes mediante `Makefile`, `justfile` o scripts documentados.
- CI local o GitHub Actions para validar frontend y worker.

### Exclusiones

- No llamar a AEMET.
- No crear mapa.
- No procesar imágenes.
- No preparar todavía el despliegue real.

### Criterios de aceptación

- Instalación reproducible documentada.
- `git status` limpio.
- Tests vacíos o mínimos ejecutables.
- Linters y type checking pasan.
- Ningún secreto versionado.
- Codex puede encontrar claramente el contexto y el roadmap.

### Validación manual

```bash
git status
npm --prefix apps/web test
npm --prefix apps/web run build
pytest
ruff check .
```

---

## Fase 1 — Spike de ingesta AEMET y archivo de originales

### Objetivo

Demostrar que el worker puede consultar, descargar, identificar y archivar de forma segura los productos actuales de AEMET.

### Alcance

- Cliente AEMET con API key desde entorno.
- Endpoint regional de Murcia como primera referencia.
- Endpoint de composición nacional.
- Inventario provisional de códigos regionales, comprobado mediante llamadas controladas.
- Descarga del recurso `datos`.
- Captura de cabeceras HTTP, tipo MIME, dimensiones, modo de color, paleta y metadatos internos.
- SHA-256 y deduplicación.
- Almacenamiento original organizado por radar y fecha.
- Registro de `retrievedAt`.
- Investigación de `productTime` sin OCR general.
- Comando CLI `fetch-once`.
- Informes JSON de inspección.
- Fixtures sanitizados para pruebas.

### Exclusiones

- No separar reflectividad.
- No georreferenciar.
- No frontend funcional.
- No sondear agresivamente la API.

### Criterios de aceptación

- Dos ejecuciones sobre la misma imagen no crean duplicados.
- Un GIF válido queda almacenado junto con su informe.
- Los errores HTTP no destruyen datos anteriores.
- La API key no aparece en logs.
- Existe un informe comparativo regional/nacional.
- Las incertidumbres quedan registradas en `DECISIONS.md`.

---

## Fase 2 — Historial de dos horas y manifiestos sin procesamiento visual

### Objetivo

Construir el ciclo de ingesta continuada y el modelo temporal antes de abordar la parte gráfica compleja.

### Alcance

- Scheduler configurable.
- Polling con timeout, reintentos limitados y backoff.
- Ingesta de Murcia y composición nacional.
- Retención inicial de 24 horas.
- Selección pública de las últimas dos horas.
- Detección y representación de huecos.
- Manifiestos atómicos.
- `health.json`.
- CLI para reconstruir manifiestos.
- Pruebas con 13 fotogramas y con secuencias incompletas.
- Servicio local de archivos para inspección.

### Exclusiones

- No animación.
- No MapLibre.
- No capa transparente.
- No todos los radares todavía.

### Criterios de aceptación

- El manifiesto ordena correctamente los fotogramas.
- Solo publica dos horas aunque conserve más originales.
- No inventa fotogramas ante huecos.
- Un fallo temporal conserva el manifiesto válido anterior.
- El estado identifica datos retrasados.

---

## Fase 3 — Extracción de reflectividad para un único radar: Murcia

### Objetivo

Obtener una capa transparente y limpia a partir de la imagen gráfica regional de Murcia.

### Alcance

- Recorte parametrizado.
- Análisis y configuración de paleta.
- Generación reproducible de máscara estática.
- Eliminación de límites, logo, textos y leyenda.
- Máscara de cobertura.
- Tratamiento del amarillo ambiguo.
- Salidas de depuración.
- Golden tests.
- Informe de píxeles clasificados y descartados.
- Procesador versionado `regional-v1`.

### Estrategia incremental

1. Separar primero colores inequívocos.
2. Excluir zonas fijas mediante máscara.
3. Añadir colores ambiguos y validar.
4. Comparar varios fotogramas secos y lluviosos.
5. Documentar pérdidas conocidas.

### Exclusiones

- No georreferenciación definitiva.
- No generalizar a todos los radares.
- No ocultar errores mediante retoques manuales no reproducibles.

### Criterios de aceptación

- Salida RGBA con fondo transparente.
- No aparecen logo, leyenda ni fronteras amarillas.
- Los ecos visibles se conservan en muestras representativas.
- El procesamiento es determinista.
- La máscara y la paleta están versionadas.
- Una revisión visual se puede repetir con un comando.

---

## Fase 4 — Georreferenciación de Murcia sobre MapLibre

### Objetivo

Superponer correctamente la capa procesada de Murcia sobre un mapa real.

### Alcance

- Determinar centro, alcance, orientación y proyección.
- Crear configuración de calibración.
- Añadir puntos de control.
- Reproyectar el raster o definir una imagen compatible con MapLibre.
- Frontend mínimo de mapa.
- Capa de radar con control de opacidad.
- Vista de depuración que muestre referencias cartográficas.
- Medición del error de alineación.
- Documentar la decisión en `DECISIONS.md`.

### Exclusiones

- No timeline completo.
- No PWA.
- No todos los radares.
- No aceptar un simple ajuste visual sin medición.

### Criterios de aceptación

- La capa coincide con varios puntos geográficos de control.
- El error máximo y medio quedan documentados.
- La alineación se mantiene al hacer zoom.
- La configuración no contiene coordenadas ficticias.
- La aplicación muestra claramente que son datos de AEMET.

---

## Fase 5 — Reproducción de las últimas dos horas

### Objetivo

Implementar la experiencia principal de uso con Murcia.

### Alcance

- Lectura del manifiesto.
- Precarga priorizada.
- Slider temporal.
- Botones individuales por fotograma.
- Play/pause.
- Velocidades lenta, normal y rápida.
- Bucle con pausa en el último fotograma.
- Hora local `Europe/Madrid`.
- Teclas de flecha.
- Huecos temporales visibles.
- Crossfade entre dos capas sin interpolar datos.
- Control de movimiento reducido.

### Criterios de aceptación

- Se puede seleccionar cualquier fotograma con slider o botón.
- Ambos controles permanecen sincronizados.
- La reproducción no salta silenciosamente huecos sin indicarlos.
- El último fotograma queda destacado.
- En móvil, los botones son utilizables y desplazables.
- No se descargan repetidamente recursos ya precargados.

---

## Fase 6 — Generalización a todos los radares regionales

### Objetivo

Convertir el procesador de Murcia en un pipeline configurable para el conjunto de radares regionales.

### Alcance

- Inventario validado de radares.
- `radars.yaml`.
- Configuración por radar para crop, máscara, paleta y georreferenciación.
- Herramienta de calibración y previsualización.
- Procesamiento batch.
- Selector de radar.
- Ajuste automático del mapa.
- Estado individual.
- Ingesta escalonada para respetar límites.
- Pruebas de al menos un radar de geometría o plantilla diferente.

### Exclusiones

- No asumir que todos comparten configuración.
- No habilitar un radar hasta superar su validación.
- No ocultar radares fallidos como si estuvieran actualizados.

### Criterios de aceptación

- Todos los radares habilitados tienen manifiesto independiente.
- Cambiar de radar no mezcla fotogramas.
- Cada radar muestra su estado y hora.
- La aplicación solo precarga el seleccionado.
- Añadir un nuevo radar está documentado y no exige tocar lógica central.

---

## Fase 7 — Composición nacional

### Objetivo

Añadir la composición nacional como producto propio, con procesador y georreferenciación específicos.

### Alcance

- Inspección completa del formato nacional.
- Procesador `national-v1`.
- Máscara y paleta propias.
- Georreferenciación nacional.
- Historial de dos horas según cadencia real.
- Integración en el selector.
- Tratamiento explícito de Península, Baleares y Canarias según el producto disponible.
- Comparación visual con el visor oficial.

### Exclusiones

- No reutilizar a la fuerza parámetros regionales.
- No fingir una cadencia de 10 minutos si el producto nacional no la proporciona.
- No rellenar intervalos ausentes mediante duplicados.

### Criterios de aceptación

- La composición se alinea con el mapa base.
- La UI representa su cadencia real.
- Los botones corresponden a imágenes reales.
- Se documentan cobertura y limitaciones.

---

## Fase 8 — UX final, PWA y robustez del frontend

### Objetivo

Transformar el prototipo funcional en una aplicación personal cómoda y fiable.

### Alcance

- Diseño responsive definitivo.
- PWA.
- Pantalla completa.
- Geolocalización local.
- Selector regional/nacional pulido.
- Opacidad.
- Indicadores actualizado/retrasado/error.
- Estado vacío.
- Último manifiesto válido en caché.
- Accesibilidad.
- Optimización de memoria.
- Métricas de rendimiento.
- Pruebas Playwright de los flujos principales.

### Criterios de aceptación

- Funciona en móvil y escritorio.
- Puede instalarse.
- La pérdida de conexión no rompe la interfaz.
- La edad del dato nunca se oculta.
- Los controles son accesibles por teclado.
- Se respeta `prefers-reduced-motion`.

---

## Fase 9 — Operación, seguridad y despliegue

### Objetivo

Desplegar de manera reproducible en el servidor accesible mediante `ssh remote`.

### Alcance

- Containerfiles.
- Quadlet para worker y servidor web.
- Timer systemd o scheduler robusto.
- Volúmenes persistentes.
- Usuario sin privilegios cuando sea posible.
- Archivo de entorno fuera del repositorio.
- Nginx y HTTPS.
- Health checks.
- Logs y rotación.
- Retención.
- Backup de configuración, máscaras y manifiestos.
- `DEPLOY.md` y `OPERATIONS.md`.
- Procedimiento de actualización y rollback.
- Validación desde navegador externo.

### Exclusiones

- No copiar la API key al frontend.
- No ejecutar el worker como root sin justificación.
- No depender de pasos manuales no documentados.

### Criterios de aceptación

- Reinicio del servidor recupera los servicios.
- La clave no aparece en repositorio ni contenido público.
- El worker conserva datos existentes tras actualizar.
- HTTPS funciona.
- Health y logs permiten diagnosticar fallos.
- Rollback probado o simulado.

---

## Fase 10 — Mejoras posteriores al MVP

Solo se abrirá tras cerrar el MVP:

- selección automática del radar según ubicación;
- favoritos locales;
- capa de rayos;
- alertas oficiales AEMET;
- nowcasting claramente marcado como estimación propia;
- aviso aproximado de llegada de lluvia;
- almacenamiento histórico ampliado;
- capa WebGL personalizada si las mediciones lo justifican.
