const CACHE_NAME = 'cantina-v2';
const STATIC_ASSETS = [
    '/',
    '/index.html',
    '/admin.html',
    '/login.html',
    '/styles.css',
    '/script.js',
    '/admin-script.js',
    '/login-script.js',
    '/manifest.json',
    '/icons/icon-192x192.png', // Verifique se estes arquivos existem
    '/icons/icon-512x512.png',
    'https://cdn.jsdelivr.net/npm/chart.js', // Cachear biblioteca de gráficos
    'https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js', // Cachear animações
    'https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/ScrollTrigger.min.js', // Plugin de Scroll
    'https://cdn.jsdelivr.net/npm/sweetalert2@11'
];

// Instalação - cachear assets estáticos
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            console.log('Service Worker: Caching App Shell');
            return cache.addAll(STATIC_ASSETS);
        })
    );
    self.skipWaiting();
});

// Ativação - limpar caches antigos
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames
                    .filter((name) => name !== CACHE_NAME)
                    .map((name) => caches.delete(name))
            );
        })
    );
    self.clients.claim();
});

// Background sync para pedidos offline
self.addEventListener('sync', (event) => {
    if (event.tag === 'sync-pedidos') {
        event.waitUntil(syncPendingOrders());
    }
});

self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);

    // Lista de caminhos da API que NUNCA devem ser cacheados
    const apiPaths = ['/auth', '/usuarios', '/produtos', '/pedidos', '/config', '/dashboard', '/relatorios'];

    // Se for uma requisição não-GET ou uma chamada de API, deixa o navegador lidar (Network Only)
    if (request.method !== 'GET' || apiPaths.some(path => url.pathname.startsWith(path))) {
        return;
    }

    // Para todos os outros GETs (arquivos do site: HTML, CSS, JS, Imagens), usa a estratégia "Cache First".
    event.respondWith(
        caches.match(request).then((response) => {
            // Retorna do cache se encontrar, senão busca na rede.
            return response || fetch(request);
        })
    );
});