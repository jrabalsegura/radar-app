import type { Map, StyleSpecification } from 'maplibre-gl';

// Conserva Liberty y sus teselas/proyección; solo adelanta y refuerza los rótulos.
export function improvePlaceLabels(map: Map): void {
  const layers = map.getStyle().layers;
  for (const layer of layers) {
    if (layer.type !== 'symbol' || layer['source-layer'] !== 'place') continue;
    map.setLayoutProperty(layer.id, 'text-field', [
      'coalesce',
      ['get', 'name'],
      ['get', 'name:latin'],
      ['get', 'name_en'],
    ]);
    if (
      ![
        'label_city',
        'label_city_capital',
        'label_town',
        'label_village',
        'label_other',
      ].includes(layer.id)
    )
      continue;
    const minimum =
      layer.id === 'label_town'
        ? 5
        : layer.id === 'label_village'
          ? 7
          : layer.id === 'label_other'
            ? 8
            : 3;
    map.setLayerZoomRange(layer.id, minimum, layer.maxzoom ?? 24);
    map.setLayoutProperty(layer.id, 'icon-optional', true);
    map.setLayoutProperty(layer.id, 'text-padding', 2);
    map.setLayoutProperty(layer.id, 'symbol-sort-key', [
      'coalesce',
      ['get', 'rank'],
      999,
    ]);
    map.setPaintProperty(layer.id, 'text-color', '#263342');
    map.setPaintProperty(layer.id, 'text-halo-color', '#ffffff');
    map.setPaintProperty(layer.id, 'text-halo-width', 1.6);
    map.setPaintProperty(layer.id, 'text-halo-blur', 0.3);
    if (layer.id.startsWith('label_city')) {
      map.setLayoutProperty(layer.id, 'text-size', [
        'interpolate',
        ['linear'],
        ['zoom'],
        4,
        12,
        7,
        14,
        11,
        19,
      ]);
      map.moveLayer(layer.id); // Las ciudades tienen prioridad sobre otros rótulos.
    }
  }
}

export function firstLabelLayer(style: StyleSpecification): string | undefined {
  return style.layers.find((layer) => layer.type === 'symbol')?.id;
}
