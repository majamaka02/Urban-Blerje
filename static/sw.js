// Service Worker për PWA
const CACHE_NAME = 'stoku-app-v1';
const urlsToCache = [
  '/',
  '/static/style.css',
  '/static/manifest.json',
  '/templates/base.html',
  '/templates/login.html',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css'
];

// Install event - cache resources
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Cache opened');
        return cache.addAll(urlsToCache).catch(err => {
          console.log('Some resources failed to cache:', err);
        });
      })
  );
  self.skipWaiting();
});

// Activate event - clean up old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            console.log('Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// Fetch event - serve from cache, fallback to network
self.addEventListener('fetch', event => {
  // Skip non-GET requests
  if (event.request.method !== 'GET') {
    return;
  }

  // Protected routes - ALWAYS fetch from network first
  const protectedRoutes = ['/categories', '/department', '/admin_panel', '/audit', '/security_logs', '/templates/'];
  const isProtected = protectedRoutes.some(route => event.request.url.includes(route));
  
  if (isProtected) {
    // Network first for protected pages - ensures authentication check
    event.respondWith(
      fetch(event.request)
        .then(response => {
          // Don't cache protected content
          return response;
        })
        .catch(() => {
          // If offline and protected route, redirect to login
          return new Response('Offline - Please login again', { status: 401 });
        })
    );
    return;
  }

  // For API/dynamic requests, network first then cache
  if (event.request.url.includes('/export/') || 
      event.request.url.includes('/toggle/') ||
      event.request.url.includes('/delete/')) {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          // Don't cache these requests
          return response;
        })
        .catch(() => {
          return caches.match(event.request);
        })
    );
    return;
  }

  // For static resources, cache first then network
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        if (response) {
          return response;
        }
        return fetch(event.request)
          .then(response => {
            // Cache successful responses
            if (!response || response.status !== 200 || response.type !== 'basic') {
              return response;
            }
            const responseToCache = response.clone();
            caches.open(CACHE_NAME)
              .then(cache => {
                cache.put(event.request, responseToCache);
              });
            return response;
          })
          .catch(() => {
            // Return offline page or cached resource
            return caches.match('/');
          });
      })
  );
});

// Background sync for offline actions
self.addEventListener('sync', event => {
  if (event.tag === 'sync-data') {
    event.waitUntil(syncData());
  }
});

async function syncData() {
  try {
    // Sync pending requests when back online
    console.log('Background sync triggered');
  } catch (error) {
    console.log('Sync failed:', error);
  }
}
