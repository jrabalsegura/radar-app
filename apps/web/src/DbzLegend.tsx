// Clases discretas de la paleta AEMET; no implican una conversión a mm/h.
const CLASSES = [
  [12, '#0000fc'],
  [18, '#0094fc'],
  [24, '#00fcfc'],
  [30, '#438323'],
  [36, '#00c000'],
  [42, '#00ff00'],
  [48, '#ffff00'],
  [54, '#ffbb00'],
  [60, '#ff7f00'],
  [66, '#ff0000'],
  [72, '#c8005a'],
] as const;

export function DbzLegend() {
  return (
    <details className="dbz-legend">
      <summary aria-label="Leyenda de reflectividad en dBZ">
        <span className="dbz-legend__bar" aria-hidden="true">
          {CLASSES.map(([dbz, color]) => (
            <i key={dbz} style={{ backgroundColor: color }} />
          ))}
        </span>
        <span className="dbz-legend__scale">
          <span>12</span>
          <span>dBZ</span>
          <span>72+</span>
        </span>
      </summary>
      <p>
        Reflectividad: intensidad del eco radar. Cada color empieza en el valor
        indicado; no equivale directamente a lluvia en mm/h.
      </p>
      <div className="dbz-legend__values">
        {CLASSES.map(([dbz, color]) => (
          <span key={dbz}>
            <i style={{ backgroundColor: color }} />
            {dbz}
            {dbz === 72 ? '+' : ''}
          </span>
        ))}
      </div>
    </details>
  );
}
