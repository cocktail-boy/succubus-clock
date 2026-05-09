const CACHE_NAME = 'succubus-clock-videos-v2';
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/succubus_anchor_01_4x4/anchor.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((cacheNames) => Promise.all(
        cacheNames
          .filter((cacheName) => cacheName !== CACHE_NAME)
          .map((cacheName) => caches.delete(cacheName))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const requestUrl = new URL(event.request.url);
  const isSameOrigin = requestUrl.origin === self.location.origin;
  const isVideo = requestUrl.pathname.endsWith('.mp4');
  const isStaticAsset =
    requestUrl.pathname === '/index.html' ||
    requestUrl.pathname === '/' ||
    requestUrl.pathname === '/succubus_anchor_01_4x4/anchor.png';

  if (!isSameOrigin || (!isVideo && !isStaticAsset)) {
    return;
  }

  event.respondWith(
    caches.open(CACHE_NAME).then(async (cache) => {
      if (isVideo) {
        return cachedVideoResponse(event.request, cache);
      }

      const cachedResponse = await cache.match(event.request);
      if (cachedResponse) {
        return cachedResponse;
      }
      const response = await fetch(event.request);
      if (response.ok && event.request.method === 'GET') {
        cache.put(event.request, response.clone());
      }
      return response;
    })
  );
});

async function cachedVideoResponse(request, cache) {
  const cacheKey = new Request(request.url);
  let response = await cache.match(cacheKey);

  if (!response) {
    response = await fetch(cacheKey);
    if (response.ok) {
      await cache.put(cacheKey, response.clone());
    }
  }

  if (request.headers.has('range')) {
    return rangedResponse(request, response);
  }

  return response;
}

async function rangedResponse(request, response) {
  const rangeHeader = request.headers.get('range');
  const rangeMatch = rangeHeader.match(/bytes=(\d+)-(\d*)/);

  if (!rangeMatch) {
    return response;
  }

  const start = Number(rangeMatch[1]);
  const sourceBuffer = await response.arrayBuffer();
  const end = rangeMatch[2] ? Number(rangeMatch[2]) : sourceBuffer.byteLength - 1;
  const chunk = sourceBuffer.slice(start, end + 1);
  const headers = new Headers(response.headers);

  headers.set('Accept-Ranges', 'bytes');
  headers.set('Content-Length', String(chunk.byteLength));
  headers.set('Content-Range', `bytes ${start}-${end}/${sourceBuffer.byteLength}`);

  return new Response(chunk, {
    status: 206,
    statusText: 'Partial Content',
    headers
  });
}
