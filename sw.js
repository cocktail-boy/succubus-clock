const CACHE_NAME = 'succubus-clock-videos-v17';
const MEDIA_PATHS = [
  '/video_outputs_seedance_1_5_pro_handbrake/anchor_variations/',
  '/video_outputs_seedance_1_5_pro_handbrake/anchor_variations_diewithzero/',
  '/video_outputs_seedance_1_5_pro_handbrake/anchor_variations_closeup_seduction/',
  '/video_outputs_seedance_1_5_pro_handbrake/idle_animations/',
  '/video_outputs_seedance_1_5_pro_handbrake/idle_animations_diewithzero/',
  '/video_outputs_seedance_1_5_pro_handbrake/idle_animations_closeup_seduction/',
  '/video_outputs_seedance_1_5_pro_handbrake/idle_blink_animations/',
  '/video_outputs_seedance_1_5_pro_handbrake/idle_blink_animations_diewithzero/',
  '/video_outputs_seedance_1_5_pro_handbrake/idle_blink_animations_closeup_seduction/',
  '/video_outputs_seedance_1_5_pro_handbrake/idle_look_forward/',
  '/video_outputs_seedance_1_5_pro_handbrake/idle_look_forward_diewithzero/',
  '/video_outputs_seedance_1_5_pro_handbrake/idle_look_forward_closeup_seduction/',
  '/video_outputs_seedance_1_5_pro_handbrake/idle_body_trace/',
  '/video_outputs_seedance_1_5_pro_handbrake/idle_body_trace_diewithzero/',
  '/video_outputs_seedance_1_5_pro_handbrake/idle_body_trace_closeup_seduction/',
  '/music/'
];
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
  const isMedia = MEDIA_PATHS.some((mediaPath) => requestUrl.pathname.startsWith(mediaPath)) &&
    (requestUrl.pathname.endsWith('.mp4') || requestUrl.pathname.endsWith('.mp3'));
  const isStaticAsset =
    requestUrl.pathname === '/index.html' ||
    requestUrl.pathname === '/' ||
    requestUrl.pathname === '/succubus_anchor_01_4x4/anchor.png';

  if (!isSameOrigin || (!isMedia && !isStaticAsset)) {
    return;
  }

  event.respondWith(
    caches.open(CACHE_NAME).then(async (cache) => {
      if (isMedia) {
        return cachedMediaResponse(event.request, cache);
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

async function cachedMediaResponse(request, cache) {
  const cacheKey = new Request(request.url);
  let response = await cache.match(cacheKey);

  if (!response) {
    const networkResponse = await fetch(cacheKey);
    if (networkResponse.ok) {
      await cache.put(cacheKey, networkResponse.clone());
    }
    response = networkResponse;
  }

  if (!request.headers.has('range') || !response.ok) {
    return response;
  }

  return rangedResponse(request, response);
}

async function rangedResponse(request, response) {
  const buffer = await response.arrayBuffer();
  const rangeHeader = request.headers.get('range');
  const rangeMatch = rangeHeader.match(/bytes=(\d+)-(\d*)/);

  if (!rangeMatch) {
    return new Response(buffer, {
      status: 200,
      headers: response.headers
    });
  }

  const start = Number(rangeMatch[1]);
  const end = rangeMatch[2] ? Number(rangeMatch[2]) : buffer.byteLength - 1;
  const chunk = buffer.slice(start, end + 1);
  const headers = new Headers(response.headers);

  headers.set('Accept-Ranges', 'bytes');
  headers.set('Content-Length', String(chunk.byteLength));
  headers.set('Content-Range', `bytes ${start}-${end}/${buffer.byteLength}`);

  return new Response(chunk, {
    status: 206,
    statusText: 'Partial Content',
    headers
  });
}
