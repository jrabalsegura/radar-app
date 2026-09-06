import { useCallback, useEffect, useRef, useState } from 'react';
import type { RadarIndex } from './radarIndex';
import { closestRegionalRadar, type LongitudeLatitude } from './radarLocation';

// La ubicación nunca se envía al worker ni a un servicio de búsqueda.
export function useRadarLocation(
  index: RadarIndex | null,
  selectRadar: (id: string) => void,
) {
  const [locationStatus, setStatus] = useState<
    'idle' | 'locating' | 'located' | 'error'
  >('idle');
  const [locationMessage, setMessage] = useState('');
  const [userCoordinates, setCoordinates] = useState<LongitudeLatitude | null>(
    null,
  );
  const request = useRef(0);
  const resetLocation = useCallback(() => {
    request.current += 1;
    setStatus('idle');
    setMessage('');
  }, []);
  useEffect(
    () => () => {
      request.current += 1;
    },
    [],
  );

  function locateNearestRadar() {
    const sequence = ++request.current;
    if (!index || !navigator.geolocation) {
      setStatus('error');
      setMessage('La geolocalización no está disponible.');
      return;
    }
    setStatus('locating');
    setMessage('Buscando el radar más cercano…');
    navigator.geolocation.getCurrentPosition(
      (position) => {
        if (sequence !== request.current) return;
        const coordinates: LongitudeLatitude = [
          position.coords.longitude,
          position.coords.latitude,
        ];
        const nearest = closestRegionalRadar(index.radars, coordinates);
        if (!nearest) {
          setStatus('error');
          setMessage('No hay radares regionales configurados.');
          return;
        }
        setCoordinates(coordinates);
        // Un radar con imágenes antiguas sigue siendo consultable; su edad se muestra aparte.
        selectRadar(nearest.available ? nearest.id : 'national');
        setStatus('located');
        setMessage(
          nearest.available
            ? `Radar más cercano: ${nearest.label}.`
            : `${nearest.label} no tiene imágenes. Mostrando composición nacional (Península y Baleares).`,
        );
      },
      () => {
        if (sequence !== request.current) return;
        setStatus('error');
        setMessage(
          'No se pudo obtener tu ubicación. Puedes elegir el radar manualmente.',
        );
      },
      {
        enableHighAccuracy: false,
        maximumAge: 10 * 60 * 1000,
        timeout: 10_000,
      },
    );
  }
  return {
    locationStatus,
    locationMessage,
    userCoordinates,
    locateNearestRadar,
    resetLocation,
  };
}
