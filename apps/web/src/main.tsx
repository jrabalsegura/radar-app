import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './App';
import { startPerformanceMetrics } from './performanceMetrics';
import { registerServiceWorker } from './registerServiceWorker';
import './styles.css';

startPerformanceMetrics();
registerServiceWorker();

const rootElement = document.getElementById('root');

if (!rootElement) {
  throw new Error('No se ha encontrado el elemento raíz de la aplicación.');
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
