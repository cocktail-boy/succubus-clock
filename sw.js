const CACHE_NAME = 'succubus-clock-videos-v12';
const MEDIA_PATHS = [
  '/video_outputs_seedance_2_0/anchor_variations/',
  '/video_outputs_seedance_2_0/idle_animations/',
  '/video_outputs_seedance_1_5_pro/anchor_variations/',
  '/video_outputs_seedance_1_5_pro/idle_animations/',
  '/video_outputs_seedance_1_5_pro/idle_blink_animations/',
  '/video_outputs_seedance_1_5_pro/idle_look_forward/',
  '/video_outputs_seedance_1_5_pro/idle_body_trace/',
  '/video_outputs_seedance_1_5_pro_handbrake/anchor_variations/',
  '/video_outputs_seedance_1_5_pro_handbrake/idle_animations/',
  '/video_outputs_seedance_1_5_pro_handbrake/idle_blink_animations/',
  '/video_outputs_seedance_1_5_pro_handbrake/idle_look_forward/',
  '/video_outputs_seedance_1_5_pro_handbrake/idle_body_trace/',
  '/music/'
];
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/succubus_anchor_01_4x4/anchor.png'
];
const mediaBuffers = new Map();
const MAX_MEDIA_BUFFERS = 12;

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
  if (request.headers.has('range')) {
    const media = await cachedMediaIfAvailable(request, cache);
    if (media) {
      return rangedResponse(request, media);
    }
    return fetch(request);
  }

  const media = await cachedMedia(request, cache);

  return new Response(media.buffer.slice(0), {
    status: 200,
    headers: media.headers
  });
}

async function cachedMediaIfAvailable(request, cache) {
  const cached = mediaBuffers.get(request.url);
  if (cached) {
    return cached;
  }

  const response = await cache.match(new Request(request.url));
  if (!response) {
    return null;
  }

  const media = {
    buffer: await response.arrayBuffer(),
    headers: new Headers(response.headers)
  };
  mediaBuffers.set(request.url, media);
  trimMediaBuffers();
  return media;
}

async function cachedMedia(request, cache) {
  const cached = mediaBuffers.get(request.url);
  if (cached) {
    return cached;
  }

  const cacheKey = new Request(request.url);
  let response = await cache.match(cacheKey);

  if (!response) {
    response = await fetch(cacheKey);
    if (response.ok) {
      await cache.put(cacheKey, response.clone());
    }
  }

  const media = {
    buffer: await response.arrayBuffer(),
    headers: new Headers(response.headers)
  };
  mediaBuffers.set(request.url, media);
  trimMediaBuffers();
  return media;
}

function trimMediaBuffers() {
  while (mediaBuffers.size > MAX_MEDIA_BUFFERS) {
    const oldestUrl = mediaBuffers.keys().next().value;
    mediaBuffers.delete(oldestUrl);
  }
}

async function rangedResponse(request, media) {
  const rangeHeader = request.headers.get('range');
  const rangeMatch = rangeHeader.match(/bytes=(\d+)-(\d*)/);

  if (!rangeMatch) {
    return new Response(media.buffer.slice(0), {
      status: 200,
      headers: media.headers
    });
  }

  const start = Number(rangeMatch[1]);
  const end = rangeMatch[2] ? Number(rangeMatch[2]) : media.buffer.byteLength - 1;
  const chunk = media.buffer.slice(start, end + 1);
  const headers = new Headers(media.headers);

  headers.set('Accept-Ranges', 'bytes');
  headers.set('Content-Length', String(chunk.byteLength));
  headers.set('Content-Range', `bytes ${start}-${end}/${media.buffer.byteLength}`);

  return new Response(chunk, {
    status: 206,
    statusText: 'Partial Content',
    headers
  });
}
