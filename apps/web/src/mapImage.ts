import type { Map, MapSourceDataEvent, ErrorEvent } from 'maplibre-gl';
import type { MapCoordinates } from './radarManifest';
import { firstLabelLayer } from './mapStyle';

// Un slot pendiente se crea oculto. Solo se muestra tras cargar su fuente real.
// Cada intento dispone de su propia fuente: cancelar B no puede modificar A.
export function prepareMapImage(
  map: Map,
  id: string,
  url: string,
  coordinates: MapCoordinates,
  signal?: AbortSignal,
): Promise<void> {
  removeMapImage(map, id);
  return new Promise((resolve, reject) => {
    const finish = (error?: Error) => {
      clearTimeout(timer);
      map.off('sourcedata', loaded);
      map.off('error', failed);
      signal?.removeEventListener('abort', aborted);
      if (error) reject(error);
      else resolve();
    };
    const loaded = (event: MapSourceDataEvent) => {
      if (event.sourceId === id && event.sourceDataType === 'metadata')
        finish();
    };
    const failed = (event: ErrorEvent) => {
      if ('sourceId' in event && event.sourceId === id)
        finish(new Error(event.error.message));
    };
    const aborted = () =>
      finish(new DOMException('Selección cancelada', 'AbortError'));
    const timer = setTimeout(
      () => finish(new Error('La imagen tardó demasiado en cargar.')),
      20_000,
    );
    map.on('sourcedata', loaded);
    map.on('error', failed);
    signal?.addEventListener('abort', aborted, { once: true });
    if (signal?.aborted) {
      aborted();
      return;
    }
    try {
      map.addSource(id, { type: 'image', url, coordinates });
      map.addLayer(
        {
          id,
          type: 'raster',
          source: id,
          paint: {
            'raster-opacity': 0,
            'raster-fade-duration': 0,
            'raster-resampling': 'nearest',
          },
        },
        firstLabelLayer(map.getStyle()),
      );
    } catch (error) {
      finish(error instanceof Error ? error : new Error(String(error)));
    }
  });
}

export function removeMapImage(map: Map, id: string): void {
  if (map.getLayer(id)) map.removeLayer(id);
  if (map.getSource(id)) map.removeSource(id);
}
