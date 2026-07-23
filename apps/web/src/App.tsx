const foundations = [
  'Frontend React y TypeScript',
  'Worker Python tipado',
  'Calidad y pruebas automatizadas',
];

export function App() {
  return (
    <main className="app-shell">
      <section className="welcome-card" aria-labelledby="page-title">
        <p className="phase-label">Fase 0</p>
        <h1 id="page-title">Radar AEMET</h1>
        <p className="intro">
          La base del proyecto está preparada. Los datos de radar llegarán en
          las siguientes fases.
        </p>

        <ul className="foundation-list" aria-label="Componentes preparados">
          {foundations.map((foundation) => (
            <li key={foundation}>
              <span aria-hidden="true">✓</span>
              {foundation}
            </li>
          ))}
        </ul>

        <p className="scope-note">
          Sin conexión a AEMET ni procesamiento meteorológico.
        </p>
      </section>
    </main>
  );
}
