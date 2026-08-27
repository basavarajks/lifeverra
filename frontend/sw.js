// Minimal service worker. LifeVerra doesn't need offline support or asset
// caching right now - this file exists purely because Chrome/Android will
// only fire the automatic "Install app?" prompt (the beforeinstallprompt
// event) for a site that has a registered service worker with a fetch
// handler. Without this file, "Quick Access from Home Screen" can only
// ever show manual instructions - it can never trigger the real one-tap
// install dialog, because Chrome doesn't consider the site installable.
self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

// A pass-through fetch handler is required for installability - it does
// not cache or intercept anything, every request just goes to the network
// exactly as if this file didn't exist.
self.addEventListener('fetch', (event) => {
  event.respondWith(fetch(event.request));
});
