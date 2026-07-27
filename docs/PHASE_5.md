# Fase 5 — Reproducción temporal

Estado: implementación y validación con historial real completadas el 26 de
julio de 2026.

## Alcance implementado

La fase convierte el visor estático de Murcia en un reproductor temporal que:

- consume `radar/regional-mu/manifest.json`;
- publica 3 horas y 50 minutos anclados en la última observación;
- muestra un botón por observación y por hueco declarado;
- mantiene sincronizados botones, slider, hora, estado y mapa;
- reproduce en bucle con velocidades lenta, normal y rápida;
- mantiene una pausa mayor en el último fotograma;
- permite navegar con las flechas izquierda y derecha;
- usa hora local `Europe/Madrid` y muestra `CET` o `CEST` según la fecha;
- conserva la última reflectividad real durante los huecos;
- precarga primero la observación más reciente y reutiliza cada URL;
- alterna dos capas MapLibre con un crossfade corto;
- desactiva la transición con `prefers-reduced-motion`.

No se han añadido otros radares, composición nacional, selector de producto,
PWA ni despliegue. Pertenecen a fases posteriores.

## Ventana de 3 horas y 50 minutos

ADR-024 amplía la ventana de ADR-016 para reproducir las 24 observaciones que
publica la cronología PPI. El valor predeterminado es:

```text
AEMET_HISTORY_HOURS=3.8333333333333335
```

La ventana sigue anclada en el último fotograma real, no en la hora de
generación del manifiesto. Una secuencia de Murcia exactamente alineada a su
cadencia nominal de 10 minutos puede contener 24 observaciones contando ambos
extremos.

`frames` contiene únicamente observaciones archivadas. Los intervalos ausentes
permanecen en `gaps`; ampliar la ventana no autoriza a rellenarlos.

## Publicación de derivados

La Fase 5 integra los procesadores validados en las fases 3 y 4 con el ciclo
periódico y con `rebuild-manifests`.

Para cada hash nuevo de Murcia:

1. `regional-v1` valida el GIF, extrae las clases y aplica la máscara estática;
2. `regional-georeference-v1` reproyecta la capa mediante vecino más próximo;
3. el PNG se publica bajo una URL inmutable:

```text
/radar/regional-mu/frames/<sha256>/overlay-3857.png
```

4. el fotograma del manifiesto conserva `rawUrl` para auditoría y añade
   `imageUrl` para el navegador.

El procesador reutiliza el derivado cuando coinciden:

- SHA-256 del GIF;
- SHA-256 de la configuración de paleta;
- SHA-256 de la máscara;
- SHA-256 de la calibración.

Un fallo de procesamiento no sustituye el manifiesto válido anterior. Nacional
y los demás radares no usan la calibración de Murcia.

## Contrato y huecos

El frontend exige `window.minutes: 230`, `window.hours: 230 / 60`,
observaciones ordenadas, hashes completos,
URLs locales de imagen y estadísticas coherentes. Combina `frames` con
`gaps[].expectedTimes` para construir las posiciones visibles.

Cuando se selecciona un hueco:

- el texto anuncia que no existe observación;
- permanece visible la última reflectividad real anterior;
- se muestra la hora original de la imagen conservada;
- reproducción y teclado continúan por la posición siguiente.

La continuidad es exclusivamente visual: el hueco sigue marcado como `Sin dato`
y no obtiene una entrada de `frames`, hash o timestamp nuevo. No se calculan
valores meteorológicos intermedios.

## Reproducción y precarga

La reproducción usa un temporizador encadenado, de modo que cambiar la velocidad
afecta al siguiente paso sin acumular intervalos. El último fotograma permanece
2,4 veces el intervalo elegido antes de volver al primero.

La cola de precarga ordena:

1. último fotograma;
2. fotogramas cercanos a la selección;
3. resto del historial desde los más recientes.

Un mapa de promesas por URL garantiza que dos solicitudes de precarga del mismo
recurso comparten la misma descarga. MapLibre mantiene dos fuentes `image` y
actualiza la inactiva con `ImageSource.updateImage`; después cruza sus
opacidades durante 180 ms. La [API oficial de MapLibre][maplibre-image-source]
documenta esa actualización de URL y coordenadas.

## Muestra real versionada

La muestra de desarrollo procede de la ejecución manual de la Fase 2 del 24 de
julio de 2026. Al reconstruirla con la ventana actual:

| Métrica | Resultado |
| --- | ---: |
| Originales archivados | 18 |
| Observaciones publicadas | 18 |
| Primera obtención UTC | `16:27:31` |
| Última obtención UTC | `19:17:31` |
| Duración observada | 2 h 50 min |
| Huecos declarados | 3 |
| PNG derivados | 18 |

Los huecos corresponden a las obtenciones esperadas alrededor de `16:37`,
`17:07` y `18:37` UTC. Se muestran como tres posiciones sin imagen. La base
temporal es `retrievedAt`, porque esos originales no aportaron una hora de
producto verificable.

La muestra está en:

```text
apps/web/public/radar/regional-mu/manifest.json
apps/web/public/radar/regional-mu/frames/<sha256>/overlay-3857.png
```

No contiene GIF originales, API key ni URLs efímeras.

## Uso local

Después de instalar:

```bash
make dev-web
```

Abrir `http://127.0.0.1:5173/`. La muestra incluida no necesita API key. El mapa
base sí necesita acceso a Internet con el estilo predeterminado.

Para reconstruir 3 horas y 50 minutos desde un archivo local real:

```bash
.venv/bin/aemet-radar rebuild-manifests \
  --product regional-mu \
  --data-dir data \
  --history-hours 3.8333333333333335
```

## Validación automatizada

Las pruebas cubren:

- selección inclusiva de 24 observaciones en 3 horas y 50 minutos;
- derivados deterministas y reutilización de la caché;
- `imageUrl` nulo cuando un producto no tiene procesador;
- validación defensiva del manifiesto de Murcia;
- combinación ordenada de observaciones y huecos;
- prioridad y deduplicación de la precarga;
- sincronización de botones, slider, texto y mapa;
- selección explícita de un hueco conservando la última imagen real;
- play/pause, velocidad rápida, pausa final y bucle;
- navegación con flechas;
- opacidad, controles de calibración y error de carga.
- respeto de `prefers-reduced-motion`.

La comprobación manual incluyó escritorio, móvil, cambio de zoom y reproducción;
la preferencia de movimiento reducido se verificó de forma automatizada.

## Limitaciones

- La muestra histórica usa hora de obtención y contiene intervalos de cinco y
  quince minutos; no debe presentarse como una cuadrícula exacta de hora de
  producto.
- La precarga se limita al radar seleccionado. La muestra regional completa
  confirmó que 24 texturas por radar no obliga a cargar los demás productos.
- Las velocidades controlan el ritmo visual, no alteran los timestamps.
- El estilo de OpenFreeMap sigue siendo configurable y no ofrece SLA.

[maplibre-image-source]: https://maplibre.org/maplibre-gl-js/docs/API/classes/ImageSource/
