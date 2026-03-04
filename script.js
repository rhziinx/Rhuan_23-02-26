/**
 * Cantina Digital Enterprise
 * Sistema completo de cardápio digital com PWA, offline support e integração API
 */

// --- INJEÇÃO AUTOMÁTICA DE BIBLIOTECA DE ANIMAÇÃO (GSAP) ---
if (!window.gsap) {
    const script = document.createElement('script');
    script.src = "https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js";
    script.onload = () => console.log("GSAP Animation Engine Loaded 🚀");
    document.head.appendChild(script);

    // Injetar ScrollTrigger (Plugin para animações ao rolar)
    const stScript = document.createElement('script');
    stScript.src = "https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/ScrollTrigger.min.js";
    stScript.onload = () => console.log("GSAP ScrollTrigger Loaded 📜");
    document.head.appendChild(stScript);
}

// --- INJEÇÃO AUTOMÁTICA SWEETALERT2 (Alertas Bonitos) ---
if (!window.Swal) {
             const script = document.createElement('script');
    script.src = "https://cdn.jsdelivr.net/npm/sweetalert2@11";
    script.onload = () => console.log("SweetAlert2 Loaded 🍬");
    document.head.appendChild(script);
}
// -----------------------------------------------------------

let savedApiUrl = window.location.protocol === 'file:' ? 'http://localhost:8000' : window.location.origin;
try {
    savedApiUrl = localStorage.getItem('api_url') || savedApiUrl;
} catch (e) {
    console.warn('Acesso ao LocalStorage bloqueado pelo navegador');
}

const CONFIG = {
    API_URL: savedApiUrl,
    CACHE_NAME: 'cantina-v22',
    DEBOUNCE_DELAY: 300,
    ITEMS_PER_PAGE: 20
};

class CantinaApp {
    constructor() {
        this.state = {
            produtos: [],
            carrinho: [],
            categoria: 'todos',
            busca: '',
            step: 1,
            pedidoAtual: null,
            configPublica: {},
            cupom: null,
            isOnline: navigator.onLine,
            isLoading: false
        };
        
        this.elements = {};
        this.debounceTimer = null;
        
        this.init();
    }
    
    init() {
        try {
            this.cacheElements();
            this.bindEvents();
            this.loadCart();
            this.checkOnlineStatus();
            this.loadProdutos();
            this.loadPublicConfig();
            this.renderCarrinho();
            this.loadRandomQuote();
            this.initButtonEffects(); // Iniciar micro-interações
            this.initMagneticButtons(); // Iniciar efeito magnético
        } catch (error) {
            console.error('Erro ao inicializar:', error);
        } finally {
            // Esconder splash screen mesmo se der erro
            setTimeout(() => {
                const splash = document.getElementById('splash');
                if (splash) {
                    if (window.gsap) {
                        gsap.to(splash, { opacity: 0, duration: 0.5, onComplete: () => splash.classList.add('hidden') });
                    } else {
                        splash.classList.add('hidden');
                    }
                }
            }, 1500);
        }
    }
    
    cacheElements() {
        this.elements = {
            productsGrid: document.getElementById('productsGrid'),
            cartBtn: document.getElementById('cartBtn'),
            cartBadge: document.getElementById('cartBadge'),
            cartModal: document.getElementById('cartModal'),
            cartBody: document.getElementById('cartBody'),
            cartFooter: document.getElementById('cartFooter'),
            subtotalValue: document.getElementById('subtotalValue'),
            totalValue: document.getElementById('totalValue'),
            checkoutModal: document.getElementById('checkoutModal'),
            searchInput: document.getElementById('searchInput'),
            categoriesContainer: document.getElementById('categoriesContainer'),
            couponInput: document.getElementById('couponInput'),
            applyCouponBtn: document.getElementById('applyCouponBtn'),
            toastContainer: document.getElementById('toastContainer'),
            offlineBanner: document.getElementById('offlineBanner')
        };
    }
    
    bindEvents() {
        // Busca com debounce
        this.elements.searchInput?.addEventListener('input', (e) => {
            clearTimeout(this.debounceTimer);
            this.debounceTimer = setTimeout(() => {
                this.state.busca = e.target.value.toLowerCase();
                this.renderProdutos();
            }, CONFIG.DEBOUNCE_DELAY);
        });
        
        // Categorias
        this.elements.categoriesContainer?.addEventListener('click', (e) => {
            if (e.target.classList.contains('category-chip')) {
                this.elements.categoriesContainer.querySelectorAll('.category-chip')
                    .forEach(btn => btn.classList.remove('active'));
                e.target.classList.add('active');
                this.state.categoria = e.target.dataset.category;
                this.renderProdutos();
            }
        });
        
        // Online/Offline
        window.addEventListener('online', () => this.setOnlineStatus(true));
        window.addEventListener('offline', () => this.setOnlineStatus(false));
        
        // Atalhos de teclado
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeAllModals();
            }
        });
        
        // Máscara de telefone
        const phoneInput = document.getElementById('customerPhone');
        if (phoneInput) {
            phoneInput.addEventListener('input', (e) => {
                let value = e.target.value.replace(/\D/g, '');
                if (value.length > 11) value = value.slice(0, 11);
                value = value.replace(/^(\d{2})(\d)/g, '($1) $2');
                value = value.replace(/(\d)(\d{4})$/, '$1-$2');
                e.target.value = value;
            });
        }
    }
    
    checkOnlineStatus() {
        this.setOnlineStatus(navigator.onLine);
    }
    
    setOnlineStatus(online) {
        this.state.isOnline = online;
        const banner = this.elements.offlineBanner;
        if (banner) {
            banner.classList.toggle('show', !online);
        }
        
        // Atualizar indicador no header
        const statusIndicator = document.querySelector('.status-indicator');
        if (statusIndicator) {
            statusIndicator.className = `status-indicator ${online ? 'online' : 'offline'}`;
            statusIndicator.textContent = online ? '● Online' : '● Offline';
        }
    }
    
    async loadProdutos() {
        // Renderizar Skeleton (Loading Bonito) antes de buscar dados
        const grid = this.elements.productsGrid;
        grid.innerHTML = '<div style="padding: 2rem; text-align: center; color: #fff;">Carregando...</div>';
        grid.innerHTML = Array(6).fill(0).map(() => `
            <div class="skeleton-card">
                <div style="height: 50%; background: rgba(255,255,255,0.02);"></div>
                <div style="padding: 1rem;">
                    <div style="height: 20px; width: 70%; background: rgba(255,255,255,0.05); margin-bottom: 10px; border-radius: 4px;"></div>
                    <div style="height: 14px; width: 90%; background: rgba(255,255,255,0.05); margin-bottom: 20px; border-radius: 4px;"></div>
                    <div style="height: 40px; width: 100%; background: rgba(255,255,255,0.05); border-radius: 8px;"></div>
                </div>
                <div class="skeleton-shimmer"></div>
            </div>
        `).join('');
        
        // this.setLoading(true); // Removido pois já temos o skeleton visual
        
        // Timeout de 10 segundos para o loading
        const timeoutId = setTimeout(() => {
            this.showToast('Atenção: Demora no carregamento. Verifique sua conexão.', 'warning');
            this.setLoading(false);
            grid.innerHTML = '<div style="padding: 2rem; text-align: center; color: #fff;">Não foi possível carregar os produtos. Verifique sua conexão e tente novamente.</div>';
            this.hideSplashScreen();
        }, 10000);

        try {
            // Tentar carregar do cache primeiro se offline
            if (!this.state.isOnline) {
                const cached = await this.getFromCache('produtos');
                if (cached) {
                    this.state.produtos = cached;
                    this.renderProdutos();
                    this.showToast('Modo offline - Dados podem estar desatualizados', 'warning');
                    return;
                }
            }
            
            const response = await fetch(`${CONFIG.API_URL}/produtos?ativos=true`);
            if (!response.ok) throw new Error('Erro ao carregar produtos');
            
            this.state.produtos = await response.json();
            this.saveToCache('produtos', this.state.produtos);
            this.renderProdutos();
            this.loadDestaques();
            
        } catch (error) {
            console.error('Erro:', error);
            this.showToast('Erro ao carregar produtos', 'error');
            
            // Tentar usar cache mesmo se online mas com erro
            const cached = await this.getFromCache('produtos');
            if (cached) {
                this.state.produtos = cached;
                this.renderProdutos();
            } else {
                // Se falhar tudo, mostrar estado vazio/erro
                this.state.produtos = [];
                this.renderProdutos();
            }
        } finally {
            this.setLoading(false);
        }
        clearTimeout(timeoutId); // Limpar timeout se carregar antes
    }
    
    loadDestaques() {
        const destaques = this.state.produtos.filter(p => p.destaque && p.ativo).slice(0, 5);
        const container = document.getElementById('highlightsContainer');
        const section = document.getElementById('highlightsSection');
        
        if (destaques.length > 0 && container && section) {
            section.style.display = 'block';
            container.innerHTML = destaques.map(produto => `
                <div class="highlight-card" onclick="app.addToCart(event, ${produto.id})">
                    <h3>${this.escapeHtml(produto.nome)}</h3>
                    <p>${this.escapeHtml(produto.descricao || '')}</p>
                    <div class="highlight-price">R$ ${produto.preco.toFixed(2).replace('.', ',')}</div>
                </div>
            `).join('');
        }
    }
    
    // Função separada para esconder a tela de splash
    hideSplashScreen() {
        const splash = document.getElementById('splash');
        if (splash) {
            if (window.gsap) {
                gsap.to(splash, { opacity: 0, duration: 0.5, onComplete: () => splash.classList.add('hidden') });
            } else {
                splash.classList.add('hidden');
            }
        }
    }



    renderProdutos() {
        const grid = this.elements.productsGrid;

        const renderContent = () => {
            const { produtos, categoria, busca } = this.state;
            let filtrados = produtos;

            if (categoria !== 'todos') {
                filtrados = filtrados.filter(p => p.categoria === categoria);
            }

            if (busca) {
                filtrados = filtrados.filter(p => 
                    p.nome.toLowerCase().includes(busca) || 
                    (p.descricao && p.descricao.toLowerCase().includes(busca))
                );
            }

            const countEl = document.getElementById('resultsCount');
            if (countEl) countEl.textContent = `${filtrados.length} item${filtrados.length !== 1 ? 's' : ''}`;

            if (filtrados.length === 0) {
                grid.innerHTML = `<div class="empty-state" style="grid-column: 1/-1;">...</div>`;
                setTimeout(() => {
                    grid.innerHTML = `
                        <div class="empty-state" style="grid-column: 1/-1;">
                            <div class="empty-icon">🔍</div>
                            <p>Nenhum produto encontrado</p>
                            <span>Tente ajustar os filtros</span>
                        </div>
                    `;
                }, 300);
                return;
            }

            grid.innerHTML = filtrados.map((produto) => {
                const stockStatus = this.getStockStatus(produto.estoque, produto.estoque_minimo);
                const isOutOfStock = produto.estoque === 0;
                
                return `
                    <article class="product-card" data-id="${produto.id}" style="opacity: 0; transform: translateY(30px);">
                        <div class="product-image-container">
                            <img src="${produto.imagem_url}" 
                                 alt="${this.escapeHtml(produto.nome)}"
                                 class="product-image"
                                 loading="lazy"
                                 onerror="this.style.display='none'; this.parentElement.style.backgroundColor='#eee'">
                            ${produto.destaque ? '<span class="product-badge destaque">Destaque</span>' : ''}
                            ${stockStatus.badge ? `<span class="product-badge ${stockStatus.class}">${stockStatus.badge}</span>` : ''}
                        </div>
                        <div class="product-info">
                            <div class="product-header">
                                <h3 class="product-name">${this.escapeHtml(produto.nome)}</h3>
                                <span class="product-stock ${stockStatus.class}">${stockStatus.text}</span>
                            </div>
                            <p class="product-description">${this.escapeHtml(produto.descricao || '')}</p>
                            <div class="product-footer">
                                <div class="product-price">
                                    <span class="currency">R$</span>
                                    ${produto.preco.toFixed(2).replace('.', ',')}
                                </div>
                                <button class="btn-add" 
                                        onclick="app.addToCart(event, ${produto.id})"
                                        ${isOutOfStock ? 'disabled' : ''}
                                        aria-label="Adicionar ${this.escapeHtml(produto.nome)}" >
                                    ${isOutOfStock ? '✕' : '+'}
                                </button>
                            </div>
                        </div>
                    </article>
                `;
            }).join('');
        };

        const animateIn = () => {
            if (grid.children.length > 0 && grid.children[0].classList.contains('product-card')) {
                gsap.fromTo(grid.children, 
                    { y: 100, opacity: 0, rotationX: -90, scale: 0.5, transformOrigin: "50% 0%" },
                    { 
                        y: 0, 
                        opacity: 1, 
                        rotationX: 0,
                        scale: 1,
                        duration: 0.8, 
                        stagger: { amount: 0.5, grid: "auto", from: "center" }, 
                        ease: 'elastic.out(1, 0.5)',
                        onComplete: () => {
                            this.add3DTiltEffect(); // Adiciona o efeito 3D após a entrada
                        }
                    }
                );
            }
        };

        this.waitForGSAP(() => {
            // Se já existem produtos na tela, anima a saída deles primeiro
            if (grid.children.length > 0 && grid.children[0].classList.contains('product-card')) {
                gsap.to(grid.children, {
                    opacity: 0,
                    y: -30, // Anima para cima ao sair
                    duration: 0.3,
                    stagger: 0.05,
                    ease: 'power2.in',
                    onComplete: () => {
                        renderContent(); // Renderiza o novo conteúdo
                        animateIn();     // Anima a entrada do novo conteúdo
                    }
                });
            } else {
                // Se a tela estiver vazia, apenas renderiza e anima a entrada
                renderContent();
                animateIn();
            }
        });
    }

    waitForGSAP(callback) {
        if (window.gsap && window.ScrollTrigger) {
            callback();
        } else {
            setTimeout(() => this.waitForGSAP(callback), 100);
        }
    }

    // Micro-interações: Efeito de clique em botões
    initButtonEffects() {
        document.addEventListener('mousedown', (e) => {
            const btn = e.target.closest('button, .category-chip, .product-card');
            if (btn && window.gsap) {
                gsap.to(btn, { scale: 0.95, duration: 0.1, ease: "power1.out" });
            }
        });
        document.addEventListener('mouseup', (e) => {
            const btn = e.target.closest('button, .category-chip, .product-card');
            if (btn && window.gsap) {
                gsap.to(btn, { scale: 1, duration: 0.4, ease: "elastic.out(1, 0.3)" });
            }
        });
    }

    // Novo: Efeito Magnético nos Botões Principais
    initMagneticButtons() {
        if (!window.gsap) return;
        
        // Seleciona botões importantes
        const buttons = document.querySelectorAll('.btn-primary, .cart-btn, .admin-fab, .category-chip');
        
        buttons.forEach(btn => {
            btn.addEventListener('mousemove', (e) => {
                const rect = btn.getBoundingClientRect();
                const x = e.clientX - rect.left - rect.width / 2;
                const y = e.clientY - rect.top - rect.height / 2;
                
                // Move o botão levemente em direção ao mouse
                gsap.to(btn, {
                    x: x * 0.3,
                    y: y * 0.3,
                    duration: 0.3,
                    ease: 'power2.out'
                });
            });
            
            btn.addEventListener('mouseleave', () => {
                // Volta para o lugar com efeito elástico
                gsap.to(btn, {
                    x: 0,
                    y: 0,
                    duration: 0.8,
                    ease: 'elastic.out(1, 0.3)'
                });
            });
        });
    }

    add3DTiltEffect() {
        const cards = document.querySelectorAll('.product-card');
        
        cards.forEach(card => {
            card.addEventListener('mousemove', (e) => {
                const rect = card.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                
                const xPct = (x / rect.width - 0.5) * 20; // Rotação X
                const yPct = (y / rect.height - 0.5) * -20; // Rotação Y (invertida)

                gsap.to(card, {
                    rotationY: xPct,
                    rotationX: yPct,
                    scale: 1.05,
                    boxShadow: '0 20px 30px rgba(0,0,0,0.4)',
                    duration: 0.5,
                    ease: 'power2.out'
                });
            });

            card.addEventListener('mouseleave', () => {
                gsap.to(card, {
                    rotationY: 0,
                    rotationX: 0,
                    scale: 1,
                    boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.5)',
                    duration: 0.5,
                    ease: 'power2.out'
                });
            });
        });
    }
    
    getStockStatus(estoque, minimo) {
        if (estoque === 0) {
            return { class: 'esgotado', text: 'Esgotado', badge: 'Esgotado' };
        } else if (estoque <= minimo) {
            return { class: 'pouco', text: `${estoque} restantes`, badge: 'Últimas' };
        }
        return { class: 'disponivel', text: 'Disponível', badge: null };
    }
    
    addToCart(event, produtoId) {
        if (event) event.stopPropagation();

        // 1. Efeito de Explosão de Partículas (Surreal!)
        this.createExplosion(event.clientX, event.clientY);

        // --- ANIMAÇÃO: Voar para o carrinho (Efeito Absurdo) ---
        try {
            if (window.gsap) {
                const btn = event.currentTarget;
                const card = btn.closest('.product-card');
                const img = card.querySelector('.product-image');
                const cartBtn = document.getElementById('cartBtn');

                // Só anima se a imagem existir E estiver visível (largura > 0)
                // Isso evita o bug da tela branca com imagens quebradas
                if (img && cartBtn && img.getBoundingClientRect().width > 0) {
                    const imgClone = img.cloneNode(true);
                    const rect = img.getBoundingClientRect();
                    const cartRect = cartBtn.getBoundingClientRect();

                    document.body.appendChild(imgClone);
                    
                    gsap.set(imgClone, {
                        position: 'fixed', top: rect.top, left: rect.left,
                        width: rect.width, height: rect.height,
                        zIndex: 9999, borderRadius: '1rem', pointerEvents: 'none'
                    });

                    const tl = gsap.timeline({ onComplete: () => imgClone.remove() });

                    tl.to(imgClone, {
                        x: cartRect.left - rect.left + (cartRect.width / 2) - (rect.width / 2),
                        y: cartRect.top - rect.top + (cartRect.height / 2) - (rect.height / 2),
                        width: 20, height: 20, opacity: 0.5, rotation: 720,
                        duration: 0.8, ease: "back.in(1.7)"
                    })
                    .to(cartBtn, {
                        scale: 1.4, color: '#FFD700', duration: 0.1, yoyo: true, repeat: 1
                    }, "-=0.2")
                    .to(cartBtn, {
                        color: '', duration: 0.2
                    });
                }
            }
        } catch (e) {
            console.warn("Erro na animação do carrinho (ignorado para não travar):", e);
        }
        // -------------------------------------------------------

        // Efeito Sonoro (Com verificação de segurança)
        const sound = document.getElementById('soundAddToCart');
        if (sound) {
            sound.play().catch(e => console.warn("Audio play failed", e));
        }

        const produto = this.state.produtos.find(p => p.id === produtoId);
        if (!produto || produto.estoque === 0) {
            this.showToast('Produto indisponível', 'error');
            return;
        }
        
        const itemExistente = this.state.carrinho.find(item => item.produto_id === produtoId);
        
        if (itemExistente) {
            if (itemExistente.quantidade >= produto.estoque) {
                this.showToast('Estoque máximo atingido', 'warning');
                return;
            }
            itemExistente.quantidade++;
        } else {
            this.state.carrinho.push({
                produto_id: produto.id,
                nome: produto.nome,
                preco: produto.preco,
                imagem_url: produto.imagem_url,
                quantidade: 1,
                estoque_disponivel: produto.estoque
            });
        }
        
        this.saveCart();
        this.renderCarrinho();
        this.showToast(`${produto.nome} adicionado!`, 'success');
    }

    // Nova Função: Explosão de Partículas
    createExplosion(x, y) {
        if (!window.gsap) return;
        
        const colors = ['#E60000', '#FFD700', '#FFFFFF'];
        const particlesCount = 12;

        for (let i = 0; i < particlesCount; i++) {
            const particle = document.createElement('div');
            document.body.appendChild(particle);
            
            const size = Math.random() * 6 + 4;
            const color = colors[Math.floor(Math.random() * colors.length)];
            
            gsap.set(particle, {
                position: 'fixed', left: x, top: y,
                width: size, height: size, backgroundColor: color,
                borderRadius: '50%', zIndex: 10000, pointerEvents: 'none'
            });

            const angle = Math.random() * Math.PI * 2;
            const velocity = Math.random() * 60 + 40;

            gsap.to(particle, {
                x: Math.cos(angle) * velocity,
                y: Math.sin(angle) * velocity,
                opacity: 0,
                scale: 0,
                duration: 0.6,
                ease: "power2.out",
                onComplete: () => particle.remove()
            });
        }
    }
    
    updateQuantity(index, delta) {
        const item = this.state.carrinho[index];
        const novaQuantidade = item.quantidade + delta;
        
        if (novaQuantidade <= 0) {
            this.removeFromCart(index);
            return;
        }
        
        if (novaQuantidade > item.estoque_disponivel) {
            this.showToast('Estoque insuficiente', 'warning');
            return;
        }
        
        item.quantidade = novaQuantidade;
        this.saveCart();
        this.renderCarrinho();
    }
    
    removeFromCart(index) {
        const item = this.state.carrinho[index];
        this.state.carrinho.splice(index, 1);
        this.saveCart();
        this.renderCarrinho();
        this.showToast(`${item.nome} removido`, 'success');

        // Animação de "tremor" no carrinho
        if (window.gsap) {
            gsap.fromTo('.cart-content', 
                { x: -5 }, 
                { x: 5, duration: 0.05, repeat: 5, yoyo: true, clearProps: 'x', ease: 'power2.inOut' }
            );
        }
    }
    
    saveCart() {
        localStorage.setItem('cantina_cart', JSON.stringify(this.state.carrinho));
    }
    
    loadCart() {
        const saved = localStorage.getItem('cantina_cart');
        if (saved) {
            this.state.carrinho = JSON.parse(saved);
        }
    }
    
    renderCarrinho() {
        const { carrinho } = this.state;
        const count = carrinho.reduce((sum, item) => sum + item.quantidade, 0);
        
        // Atualizar badge
        this.elements.cartBadge.textContent = count;
        this.elements.cartBadge.style.display = count > 0 ? 'flex' : 'none';
        
        // Animação de pulso no botão do carrinho se tiver itens
        if (count > 0) {
            this.elements.cartBtn.classList.add('pulse-animation');
        } else {
            this.elements.cartBtn.classList.remove('pulse-animation');
        }
        
        if (carrinho.length === 0) {
            this.elements.cartBody.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">🛒</div>
                    <p>Seu carrinho está vazio</p>
                    <span>Adicione itens para começar</span>
                </div>
            `;
            this.elements.cartFooter.style.display = 'none';
            return;
        }
        
        this.elements.cartBody.innerHTML = carrinho.map((item, index) => `
            <div class="cart-item">
                <img src="${item.imagem_url}" alt="${this.escapeHtml(item.nome)}" class="cart-item-image">
                <div class="cart-item-details">
                    <div class="cart-item-name">${this.escapeHtml(item.nome)}</div> 
                    <div class="cart-item-price">R$ ${(item.preco * item.quantidade).toFixed(2).replace('.', ',')}</div>
                    <div class="cart-item-controls">
                        <button class="qty-btn" onclick="app.updateQuantity(${index}, -1)">−</button>
                        <span class="qty-value">${item.quantidade}</span>
                        <button class="qty-btn" onclick="app.updateQuantity(${index}, 1)">+</button>
                        <button class="btn-remove" onclick="app.removeFromCart(${index})">Remover</button>
                    </div>
                </div>
            </div>
        `).join('');
        
        // Calcular totais
        const subtotal = carrinho.reduce((sum, item) => sum + (item.preco * item.quantidade), 0);
        let total = subtotal;
        let desconto = 0;

        // Aplicar cupom
        if (this.state.cupom) {
            if (this.state.cupom.tipo_desconto === 'percentual') {
                desconto = (subtotal * this.state.cupom.valor_desconto) / 100;
            } else {
                desconto = this.state.cupom.valor_desconto;
            }
            total -= desconto;
            document.getElementById('discountRow').style.display = 'flex';
            document.getElementById('discountValue').textContent = `- R$ ${desconto.toFixed(2).replace('.', ',')}`;
        } else {
            document.getElementById('discountRow').style.display = 'none';
        }
        
        this.elements.subtotalValue.textContent = `R$ ${subtotal.toFixed(2).replace('.', ',')}`;
        this.elements.totalValue.textContent = `R$ ${total.toFixed(2).replace('.', ',')}`;
        this.elements.cartFooter.style.display = 'block';
    }
    
    toggleCart() {
        const isOpen = this.elements.cartModal.classList.contains('open');
        this.elements.cartModal.classList.toggle('open', !isOpen);
        document.body.style.overflow = !isOpen ? 'hidden' : '';
        if (window.gsap) {
            if (!isOpen) {
                // Abrindo: Efeito elástico vindo de baixo
                gsap.fromTo('.cart-content', { y: '100%' }, { y: '0%', duration: 0.8, ease: 'elastic.out(1, 0.75)' });
            } else {
                // Fechando
                gsap.to('.cart-content', { y: '100%', duration: 0.4, ease: 'power2.in' });
            }
        }
    }
    
    checkout() {
        if (this.state.carrinho.length === 0) {
            this.showToast('Carrinho vazio', 'error');
            return;
        }
        
        this.toggleCart();
        this.openCheckout();
    }
    
    openCheckout() {
        this.state.step = 1;
        this.updateCheckoutStep();
        this.elements.checkoutModal.classList.add('open');
        if (window.gsap) {
            gsap.to('.checkout-content', { y: 0, duration: 0.5, ease: 'power3.out' });
        }
        document.body.style.overflow = 'hidden';
    }
    
    closeCheckout() {
        this.elements.checkoutModal.classList.remove('open');
        document.body.style.overflow = '';
        
        // Se já confirmou o pedido, limpar carrinho
        if (this.state.step === 3) {
            this.state.carrinho = [];
            this.saveCart();
            this.renderCarrinho();
            this.state.step = 1;
        }
    }
    
    updateCheckoutStep() {
        document.querySelectorAll('.checkout-step').forEach((el, i) => {
            el.classList.toggle('active', i + 1 === this.state.step);
        });
        
        const btn = document.getElementById('checkoutActionBtn');
        const steps = ['Continuar', 'Confirmar Pagamento', 'Fechar'];
        btn.textContent = steps[this.state.step - 1];
        
        if (this.state.step === 3) {
            btn.onclick = () => this.closeCheckout();
        } else if (this.state.step === 2) {
            btn.onclick = () => this.confirmPayment();
        } else {
            btn.onclick = () => this.nextStep();
        }
    }
    
    nextStep() {
        // Validação passo 1
        if (this.state.step === 1) {
            const nome = document.getElementById('customerName').value.trim();
            const telefone = document.getElementById('customerPhone').value.trim();
            const data = document.getElementById('pickupDate').value;
            const hora = document.getElementById('pickupTime').value;
            
            if (!nome || !telefone || !data || !hora) {
                this.showToast('Preencha todos os dados, incluindo data e hora da retirada', 'error');
                return;
            }

            // Validar data/hora
            const dataAgendamento = new Date(`${data}T${hora}`);
            const agora = new Date();
            if (dataAgendamento < agora) {
                this.showToast('A data de retirada não pode ser no passado.', 'error');
                return;
            }
        }
        
        this.state.step++;
        this.updateCheckoutStep();
    }
    
    generatePix() {
        const total = this.state.carrinho.reduce((sum, item) => sum + (item.preco * item.quantidade), 0);
        const chave = this.state.configPublica.chave_pix || 'Chave PIX não configurada';
        const nomeEmpresa = this.state.configPublica.nome_empresa || 'Cantina Digital';
        
        document.getElementById('pixKey').textContent = chave;
        
        // Gerar payload para PIX Copia e Cola (simplificado)
        // Uma implementação real usaria uma biblioteca para gerar o BRCode completo.
        const pixPayload = `Chave: ${chave}, Valor: R$ ${total.toFixed(2)}, Loja: ${nomeEmpresa}`;
        
        document.getElementById('pixQrCode').src =
            `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(pixPayload)}`;
    }
    
    copyPixKey() {
        const key = document.getElementById('pixKey').textContent;
        navigator.clipboard.writeText(key).then(() => {
            this.showToast('Chave copiada!', 'success');
        });
    }
    
    async confirmPayment() {
        const formaPagamento = document.querySelector('input[name="payment"]:checked')?.value || 'pix';

        // Gerar PIX somente se for a forma de pagamento escolhida
        if (this.state.step === 1 && formaPagamento === 'pix') {
            this.generatePix();
            return; // Fica no passo 2 para o usuário pagar
        }
        
        // Preparar dados do pedido
        const data = document.getElementById('pickupDate').value;
        const hora = document.getElementById('pickupTime').value;
        const data_retirada = new Date(`${data}T${hora}`).toISOString();

        const pedido = {
            itens: this.state.carrinho.map(item => ({
                produto_id: item.produto_id,
                quantidade: item.quantidade,
                observacao: '',
            })),
            data_retirada: data_retirada,
            cliente_nome: document.getElementById('customerName').value.trim(),
            cliente_telefone: document.getElementById('customerPhone').value.trim(),
            observacoes: document.getElementById('orderObs').value.trim(),
            desconto: this.state.cupom ? (this.state.cupom.tipo_desconto === 'percentual' ? (this.state.carrinho.reduce((sum, item) => sum + (item.preco * item.quantidade), 0) * this.state.cupom.valor_desconto) / 100 : this.state.cupom.valor_desconto) : 0,
            cupom_codigo: this.state.cupom ? this.state.cupom.codigo : null
        };
        
        try {
            const response = await fetch(`${CONFIG.API_URL}/pedidos`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(pedido)
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Erro ao criar pedido');
            }
            
            const resultado = await response.json();
            this.state.pedidoAtual = resultado;
            
            // Confirmar pagamento
            await fetch(`${CONFIG.API_URL}/pedidos/${resultado.id}/pagar?forma_pagamento=${formaPagamento}`, {
                method: 'POST'
            });
            
            // Mostrar confirmação
            document.getElementById('orderCode').textContent = resultado.codigo;
            const dataAgendamento = new Date(resultado.data_retirada);
            document.getElementById('pickupTimeInfo').textContent = dataAgendamento.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
            document.getElementById('soundSuccess').play().catch(e => console.warn("Audio play failed"));
            this.state.step = 3;
            
            // SweetAlert2 Success Modal
            if (window.Swal) {
                Swal.fire({
                    title: 'Pedido Confirmado!',
                    text: `Seu código é: ${resultado.codigo}`,
                    icon: 'success',
                    confirmButtonText: 'Acompanhar',
                    confirmButtonColor: '#009C3B',
                    background: '#1a1a1d',
                    color: '#fff'
                });
            }

            this.triggerConfetti(); // Disparar confetes!
            this.updateCheckoutStep();
            
            // Notificar admin via WhatsApp (opcional)
            this.notifyAdmin(resultado);
            
        } catch (error) {
            this.showToast(error.message, 'error');
        }
    }

    triggerConfetti() {
        if (!window.gsap) return;
        const colors = ['#E60000', '#FFD700', '#ffffff', '#009C3B'];
        
        for (let i = 0; i < 60; i++) {
            const confetto = document.createElement('div');
            const bg = colors[Math.floor(Math.random() * colors.length)];
            document.body.appendChild(confetto);
            
            gsap.set(confetto, {
                position: 'fixed', top: '50%', left: '50%',
                width: Math.random() * 10 + 5, height: Math.random() * 10 + 5,
                backgroundColor: bg, zIndex: 10000, borderRadius: '2px'
            });
            
            const angle = Math.random() * Math.PI * 2;
            const velocity = Math.random() * 300 + 100;
            
            gsap.to(confetto, {
                x: Math.cos(angle) * velocity, y: Math.sin(angle) * velocity,
                rotation: Math.random() * 720, opacity: 0, scale: 0,
                duration: Math.random() * 1.5 + 0.5, ease: "power2.out",
                onComplete: () => confetto.remove()
            });
        }
    }
    
    async applyCoupon() {
        const codigo = this.elements.couponInput.value.trim().toUpperCase();
        if (!codigo) return;

        this.elements.applyCouponBtn.textContent = '...';
        try {
            const response = await fetch(`${CONFIG.API_URL}/cupons/validar/${codigo}`);
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Cupom inválido');
            }
            this.state.cupom = await response.json();
            this.showToast(`Cupom "${this.state.cupom.codigo}" aplicado!`, 'success');
            this.renderCarrinho();

        } catch (error) {
            this.state.cupom = null;
            this.showToast(error.message, 'error');
            this.renderCarrinho();
        } finally {
            this.elements.applyCouponBtn.textContent = 'Aplicar';
        }
    }

    async loadPublicConfig() {
        try {
            const response = await fetch(`${CONFIG.API_URL}/config/public`);
            if (!response.ok) return;
            this.state.configPublica = await response.json();
            
            // Aplicar personalização
            this.applyTheme();
        } catch (error) {
            console.warn('Não foi possível carregar configurações públicas.');
        }
    }

    applyTheme() {
        const { nome_empresa, logo_url, cor_tema } = this.state.configPublica;
        
        // Atualizar Título
        if (nome_empresa) {
            document.title = nome_empresa;
            document.querySelectorAll('h1').forEach(el => {
                if (el.textContent === 'Cantina Digital') el.textContent = nome_empresa;
            });
        }

        // Atualizar Cor
        if (cor_tema) {
            document.documentElement.style.setProperty('--primary-500', cor_tema);
            // document.documentElement.style.setProperty('--primary-600', cor_tema); // Removido para manter gradiente
            
            // Atualizar meta theme-color
            const metaTheme = document.querySelector('meta[name="theme-color"]');
            if (metaTheme) metaTheme.setAttribute('content', cor_tema);
        }

        // Atualizar Logo (se houver URL válida)
        if (logo_url && logo_url.startsWith('http')) {
            document.querySelectorAll('.brand-icon, .splash-logo').forEach(el => {
                el.innerHTML = `<img src="${logo_url}" style="width:100%; height:100%; object-fit:cover; border-radius:inherit;">`;
                el.style.background = 'transparent';
                el.style.boxShadow = 'none';
            });
        }
    }

    loadRandomQuote() {
        const quotes = [
            "Se você quer ser bem sucedido, precisa ter dedicação total, buscar seu último limite e dar o melhor de si.",
            "No que diz respeito ao empenho, ao compromisso, ao esforço, à dedicação, não existe meio termo.",
            "Eu não tenho ídolos. Tenho admiração por trabalho, dedicação e competência.",
            "Vencer é o que importa. O resto é a consequência.",
            "O medo faz parte da vida da gente. Algumas pessoas não sabem como enfrentá-lo, outras aprendem a conviver com ele.",
            "Dinheiro é um negócio curioso. Quem não tem, está louco para ter; quem tem, está cheio de problemas por causa dele.",
            "A vida é muito curta para ser pequena.",
            "Não sei dirigir de outra maneira que não seja arriscada. Quando tiver de ultrapassar, vou ultrapassar."
        ];
        
        const quote = quotes[Math.floor(Math.random() * quotes.length)];
        const el = document.getElementById('sennaQuote');
        if (el) {
            el.textContent = `"${quote}"`;
            if (window.gsap) {
                gsap.from(el, { opacity: 0, x: -20, duration: 1, delay: 1.5, ease: 'power2.out' });
            }
        }
    }

    notifyAdmin(pedido) {
        // Implementar integração com WhatsApp API ou similar
        console.log('Novo pedido:', pedido);
    }
    
    closeAllModals() {
        this.elements.cartModal.classList.remove('open');
        this.elements.checkoutModal.classList.remove('open');
        document.body.style.overflow = '';
    }
    
    showToast(message, type = 'info') {
        // Usar SweetAlert2 se disponível para um visual mais "Pro"
        if (window.Swal) {
            const Toast = Swal.mixin({
                toast: true,
                position: 'top-end',
                showConfirmButton: false,
                timer: 3000,
                timerProgressBar: true,
                background: '#252529',
                color: '#fff',
                didOpen: (toast) => {
                    toast.addEventListener('mouseenter', Swal.stopTimer)
                    toast.addEventListener('mouseleave', Swal.resumeTimer)
                }
            });
            Toast.fire({ icon: type, title: message });
            return;
        }

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            ${type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ'} 
            ${message}
        `;
        
        this.elements.toastContainer.appendChild(toast);
        
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(20px) translateX(-50%)';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
    
    setLoading(loading) {
        this.state.isLoading = loading;
        // Implementar indicador de loading global se necessário
    }
    
    // Cache API para offline
    async saveToCache(key, data) {
        if ('caches' in window) {
            const cache = await caches.open(CONFIG.CACHE_NAME);
            const response = new Response(JSON.stringify(data));
            await cache.put(key, response);
        }
    }
    
    async getFromCache(key) {
        if ('caches' in window) {
            const cache = await caches.open(CONFIG.CACHE_NAME);
            const response = await cache.match(key);
            if (response) {
                return await response.json();
            }
        }
        return null;
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Inicializar app
const app = new CantinaApp();