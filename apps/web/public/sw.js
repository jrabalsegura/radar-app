const VERSION = 'phase-8-v1';
const APP_CACHE = `radar-app-${VERSION}`;
const DATA_CACHE = `radar-data-${VERSION}`;
const IMAGE_CACHE = `radar-images-${VERSION}`;
const MAP_CACHE = `radar-map-${VERSION}`;
const APP_SHELL = [
  '/',
  '/index.html',
  '/manifest.webmanifest',
  '/icons/radar-192.png',
  '/icons/radar-512.png',
  '/icons/apple-touch-icon.png',
];
const CACHE_LIMITS = new Map([
  [DATA_CACHE, 40],
  [IMAGE_CACHE, 56],
  [MAP_CACHE, 90],
]);

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(APP_CACHE)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter(
              (key) =>
                key.startsWith('radar-') &&
                ![APP_CACHE, DATA_CACHE, IMAGE_CACHE, MAP_CACHE].includes(key),
            )
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') {
    return;
  }
  const url = new URL(request.url);

  if (request.mode === 'navigate') {
    event.respondWith(
      networkFirst(request, APP_CACHE).catch(() => caches.match('/index.html')),
    );
    return;
  }

  if (url.origin === self.location.origin && url.pathname.endsWith('.json')) {
    event.respondWith(networkFirst(request, DATA_CACHE));
    return;
  }

  if (
    url.origin === self.location.origin &&
    url.pathname.startsWith('/radar/') &&
    /\.(png|gif|webp)$/.test(url.pathname)
  ) {
    event.respondWith(cacheFirst(request, IMAGE_CACHE));
    return;
  }

  if (url.origin === self.location.origin) {
    event.respondWith(cacheFirst(request, APP_CACHE));
    return;
  }

  if (
    url.hostname.endsWith('openfreemap.org') ||
    url.hostname.endsWith('openstreetmap.org')
  ) {
    event.respondWith(cacheFirst(request, MAP_CACHE));
  }
});

async function networkFirst(request, cacheName) {
  try {
    const response = await fetch(request);
    if (isCacheable(response)) {
      const cache = await caches.open(cacheName);
      await cache.put(request, response.clone());
      await trimCache(cacheName);
    }
    return response;
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) {
      return markCacheHit(cached);
    }
    throw error;
  }
}

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) {
    return cached;
  }
  const response = await fetch(request);
  if (isCacheable(response)) {
    const cache = await caches.open(cacheName);
    await cache.put(request, response.clone());
    await trimCache(cacheName);
  }
  return response;
}

function isCacheable(response) {
  return response.ok || response.type === 'opaque';
}

function markCacheHit(response) {
  if (response.type === 'opaque') {
    return response;
  }
  const headers = new Headers(response.headers);
  headers.set('X-Radar-Cache', 'hit');
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

async function trimCache(cacheName) {
  const limit = CACHE_LIMITS.get(cacheName);
  if (!limit) {
    return;
  }
  const cache = await caches.open(cacheName);
  const requests = await cache.keys();
  const overflow = requests.length - limit;
  if (overflow > 0) {
    await Promise.all(
      requests.slice(0, overflow).map((request) => cache.delete(request)),
    );
  }
}
