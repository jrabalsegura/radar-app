import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { App } from './App';

describe('App', () => {
  it('identifica la aplicación y el alcance de la fase inicial', () => {
    render(<App />);

    expect(
      screen.getByRole('heading', { name: 'Radar AEMET' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Fase 0')).toBeInTheDocument();
    expect(screen.getByText(/Sin conexión a AEMET/i)).toBeInTheDocument();
  });
});
