import { expect, test } from '@playwright/test';

test('recorre el radar con controles accesibles y conserva la edad visible', async ({
  page,
}) => {
  const failedAssetResponses: Array<{ status: number; url: string }> = [];
  const vectorTileResponses: Array<{ status: number; url: string }> = [];
  page.on('response', (response) => {
    const url = new URL(response.url());
    const pathname = url.pathname;
    if (pathname.startsWith('/assets/') && response.status() >= 400) {
      failedAssetResponses.push({
        status: response.status(),
        url: response.url(),
      });
    }
    if (
      url.hostname === 'tiles.openfreemap.org' &&
      pathname.startsWith('/planet/') &&
      pathname.endsWith('.pbf')
    ) {
      vectorTileResponses.push({
        status: response.status(),
        url: response.url(),
      });
    }
  });
  await page.goto('/');

  await expect(
    page.getByRole('heading', { name: 'Radar Murcia' }),
  ).toBeVisible();
  await expect(page.locator('.map-stage')).toHaveAttribute(
    'data-map-ready',
    'true',
  );
  const mapContainer = page.locator('.map-canvas.maplibregl-map');
  await expect(mapContainer).toBeVisible();
  await expect(page.locator('.maplibregl-canvas')).toBeVisible();
  await expect
    .poll(async () =>
      Number(await page.locator('.map-stage').getAttribute('data-top-inset')),
    )
    .toBe(0);
  await expect
    .poll(async () =>
      Number(
        await page.locator('.map-stage').getAttribute('data-bottom-inset'),
      ),
    )
    .toBeGreaterThan(100);
  await expect
    .poll(async () => (await mapContainer.boundingBox())?.height ?? 0)
    .toBeGreaterThan(300);
  await expect(page.locator('.frame-card')).toHaveCount(0);
  await expect.poll(() => vectorTileResponses.length).toBeGreaterThan(0);
  expect(vectorTileResponses.every((response) => response.status < 400)).toBe(
    true,
  );
  expect(failedAssetResponses).toHaveLength(0);
  await expect(page.locator('.data-freshness')).toContainText(
    /Último dato .* · hace /,
  );
  const timeline = page.getByLabel('Instante del radar');
  await expect(timeline).toBeFocused();
  await expect
    .poll(() =>
      timeline.evaluate((element) => getComputedStyle(element).outlineStyle),
    )
    .toBe('none');
  const initialTimelineValue = Number(await timeline.inputValue());
  await page.keyboard.press('ArrowLeft');
  await expect(timeline).toHaveValue(String(initialTimelineValue - 1));

  await expect(
    page.getByRole('option', { name: 'Almería (A)' }),
  ).toBeAttached();
  await page.keyboard.press('A');
  await expect(
    page.getByRole('heading', { name: 'Radar Almería' }),
  ).toBeVisible();

  await page.keyboard.press('E');
  await expect(
    page.getByRole('heading', { name: 'Composición nacional' }),
  ).toBeVisible();

  const mapOptions = page.getByRole('button', {
    name: 'Abrir opciones del mapa',
  });
  await mapOptions.click();
  const opacity = page.getByLabel('Opacidad del radar');
  await opacity.fill('0.45');
  await expect(page.locator('.map-options__panel output')).toHaveText('45%');
  await page.keyboard.press('Escape');
  await expect(mapOptions).toBeFocused();
  await expect(page.getByLabel('Opacidad del radar')).toHaveCount(0);

  const play = page.getByRole('button', { name: 'Reproducir historial' });
  await play.focus();
  await page.keyboard.press('Enter');
  await expect(
    page.getByRole('button', { name: 'Pausar reproducción' }),
  ).toHaveAttribute('aria-pressed', 'true');

  await page.locator('h1').click();
  await page.keyboard.press('ArrowLeft');
  await expect(
    page.getByRole('button', { name: 'Reproducir historial' }),
  ).toBeVisible();
});

test('la copia local mantiene la interfaz utilizable sin conexión', async ({
  context,
  page,
}) => {
  await page.goto('/');
  await expect(
    page.getByRole('heading', { name: 'Radar Murcia' }),
  ).toBeVisible();
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await expect(page.getByLabel('Instante del radar')).toBeVisible();

  await context.setOffline(true);
  await page.reload({ waitUntil: 'domcontentloaded' });

  await expect(
    page.getByRole('heading', { name: 'Radar Murcia' }),
  ).toBeVisible();
  await expect(page.getByLabel('Instante del radar')).toBeVisible();
  await expect(page.locator('.data-freshness')).toContainText(
    /Último dato .* · hace /,
  );
  await page.getByRole('button', { name: 'Abrir opciones del mapa' }).click();
  await page.getByLabel('Opacidad del radar').fill('0.55');
  await expect(page.locator('.map-options__panel output')).toHaveText('55%');
});

test('respeta movimiento reducido', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');

  await expect(
    page.getByRole('heading', { name: 'Radar Murcia' }),
  ).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(
        () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
      ),
    )
    .toBe(true);
});

test('amplía el reproductor con la Fullscreen API', async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop');
  await page.goto('/');
  await expect(
    page.getByRole('heading', { name: 'Radar Murcia' }),
  ).toBeVisible();

  await page.getByRole('button', { name: 'Abrir opciones del mapa' }).click();
  await page.getByRole('button', { name: 'Pantalla completa' }).click();
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          document.fullscreenElement?.classList.contains('map-layout') ?? false,
      ),
    )
    .toBe(true);

  await page.getByRole('button', { name: 'Abrir opciones del mapa' }).click();
  await page
    .getByRole('button', { name: 'Salir de pantalla completa' })
    .click();
  await expect
    .poll(() => page.evaluate(() => document.fullscreenElement === null))
    .toBe(true);
});

test.describe('geolocalización móvil', () => {
  test.use({
    geolocation: { latitude: 40.1759, longitude: -3.7137 },
    permissions: ['geolocation'],
  });

  test('selecciona el radar regional más cercano sin enviar la ubicación', async ({
    page,
  }) => {
    await page.goto('/');
    await expect(
      page.getByRole('heading', { name: 'Radar Murcia' }),
    ).toBeVisible();

    await page
      .getByRole('button', {
        name: 'Usar mi ubicación para elegir el radar más cercano',
      })
      .click();

    await expect(
      page.getByRole('heading', { name: 'Radar Madrid' }),
    ).toBeVisible();
    await expect(page.getByText('Radar más cercano: Madrid.')).toBeVisible();
  });
});
