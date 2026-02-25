const CACHE_NAME = 'cantina-v13';
const STATIC_ASSETS = [
    '/',
    '/index.html',
    '/styles.css',
    '/script.js',
    '/manifest.json'
];

// Instalação - cachear assets estáticos
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
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

// Fetch - estratégia stale-while-revalidate
self.addEventListener('fetch', (event) => {
    const { request } = event;
    
    // Ignorar requisições não GET
    if (request.method !== 'GET') return;
    
    // Ignorar requisições da API (deixar passar)
    if (request.url.includes('localhost:8000')) {
        event.respondWith(networkFirst(request));
        return;
    }
    
    // MUDANÇA: Usar NetworkFirst para garantir que o CSS/JS carregue corretamente no desenvolvimento
    event.respondWith(networkFirst(request));
});

async function staleWhileRevalidate(request) {
    const cached = await caches.match(request);
    const fetchPromise = fetch(request).then(async networkResponse => {
        if (networkResponse.ok) {
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, networkResponse.clone());
        }
        return networkResponse;
    }).catch(error => {
        // Se falhar e não tiver cache, retorna erro silencioso para não travar
        console.warn('Falha ao buscar:', request.url);
        if (cached) return cached;
        
        // Se não tiver cache e for a página principal, deixa o navegador mostrar erro de conexão
        // em vez de retornar uma página em branco 404
        throw error;
    });

    return cached || fetchPromise;
}

async function networkFirst(request) {
    try {
        const networkResponse = await fetch(request);
        // Atualizar cache com dados frescos se a requisição for bem-sucedida
        if (networkResponse.ok) {
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, networkResponse.clone());
        }
        return networkResponse;
    } catch (error) {
        // Tentar retornar do cache se falhar a rede
        const cached = await caches.match(request);
        return cached; // Retorna o cache ou undefined se não houver
    }
}

// Background sync para pedidos offline
self.addEventListener('sync', (event) => {
    if (event.tag === 'sync-pedidos') {
        event.waitUntil(syncPendingOrders());
    }
});

async function syncPendingOrders() {
    // Implementar sincronização de pedidos pendentes
    console.log('Sincronizando pedidos pendentes...');
}