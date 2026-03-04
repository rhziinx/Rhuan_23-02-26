const API_URL = window.location.protocol === 'file:' ? 'http://localhost:8000' : window.location.origin;

class AdminPanel {
    constructor() {
        this.token = localStorage.getItem('token');
        this.currentSection = 'dashboard';
        this.charts = {};
        this.isLive = false;
        this.liveInterval = null;
        
        this.init();
    }
    
    init() {
        if (!this.token) {
            window.location.href = 'login.html';
            return;
        }
        
        this.bindEvents();
        this.loadUser();
        this.showSection('dashboard');
        this.loadChartJS(); // Iniciar carregamento dos gráficos
        this.loadConfig(); // Carregar tema e configurações ao iniciar
        this.startAutoRefresh();
    }
    
    bindEvents() {
        // Navegação
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                const section = item.dataset.section;
                this.showSection(section);
            });
        });
        
        // Configurar datas padrão para relatórios
        const hoje = new Date().toISOString().split('T')[0];
        const inicioMes = new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().split('T')[0];
        
        const dataInicio = document.getElementById('relDataInicio');
        const dataFim = document.getElementById('relDataFim');
        if (dataInicio) dataInicio.value = inicioMes;
        if (dataFim) dataFim.value = hoje;
    }

    // --- CARREGAMENTO SEGURO DO CHART.JS ---
    loadChartJS() {
        if (typeof Chart !== 'undefined') return; // Já carregado via HTML
        
        const script = document.createElement('script');
        script.src = "https://cdn.jsdelivr.net/npm/chart.js";
        script.onload = () => this.refreshData(); // Recarrega dados quando terminar de baixar
        document.head.appendChild(script);
    }
    // ---------------------------------------
    
    async loadUser() {
        try {
            const response = await fetch(`${API_URL}/usuarios/me`, {
                headers: { 'Authorization': `Bearer ${this.token}` }
            });
            
            if (response.ok) {
                const user = await response.json();
                document.getElementById('userName').textContent = user.nome;
            }
        } catch (error) {
            console.error('Erro ao carregar usuário:', error);
        }
    }
    
    showSection(section) {
        // Atualizar navegação
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.toggle('active', item.dataset.section === section);
        });
        
        // Mostrar seção
        document.querySelectorAll('.content-section').forEach(sec => {
            sec.classList.toggle('active', sec.id === `${section}Section`);
        });
        
        this.currentSection = section;
        
        // Carregar dados específicos
        switch(section) {
            case 'dashboard':
                this.loadDashboard();
                break;
            case 'pedidos':
                this.loadPedidos();
                break;
            case 'produtos':
                this.loadProdutos();
                break;
            case 'config':
                this.loadConfig();
                break;
        }
    }
    
    async loadDashboard() {
        try {
            const response = await fetch(`${API_URL}/dashboard/stats`, {
                headers: { 'Authorization': `Bearer ${this.token}` }
            });
            
            if (!response.ok) throw new Error('Erro ao carregar estatísticas');
            
            const stats = await response.json();
            
            // Atualizar cards
            document.getElementById('vendasHoje').textContent = `R$ ${stats.total_vendas_hoje.toFixed(2)}`;
            document.getElementById('pedidosHoje').textContent = stats.total_pedidos_hoje;
            document.getElementById('ticketMedio').textContent = `R$ ${stats.ticket_medio_hoje.toFixed(2)}`;
            document.getElementById('estoqueBaixo').textContent = stats.produtos_baixo_estoque;
            document.getElementById('pedidosBadge').textContent = stats.pedidos_pendentes;
            
            // Gráfico
            this.renderChart(stats.vendas_semana);
            this.renderTopProductsChart(stats.top_produtos);
            
            // Pedidos recentes
            this.loadPedidosRecentes();
            
        } catch (error) {
            console.error('Erro:', error);
            this.showToast('Erro ao carregar dashboard', 'error');
        }
    }
    
    renderChart(vendasData) {
        const ctx = document.getElementById('vendasChart');
        if (!ctx) return;

        // Proteção: Se o Chart.js ainda não carregou, tenta de novo em 500ms
        if (typeof Chart === 'undefined') {
            setTimeout(() => this.renderChart(vendasData), 500);
            return;
        }
        
        if (this.charts.vendas) {
            this.charts.vendas.destroy();
        }
        
        const labels = vendasData.map(v => {
            const data = new Date(v.data);
            return data.toLocaleDateString('pt-BR', { weekday: 'short' });
        });
        
        const valores = vendasData.map(v => v.total);
        
        this.charts.vendas = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Vendas (R$)',
                    data: valores,
                    borderColor: '#E60000',
                    backgroundColor: 'rgba(249, 115, 22, 0.1)',
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    y: {
                        grid: { color: 'rgba(255,255,255,0.1)' },
                        ticks: {
                            color: '#a1a1aa',
                            callback: function(value) { return 'R$ ' + value.toFixed(0); }
                        },
                        beginAtZero: true,
                    },
                    x: {
                        grid: { color: 'rgba(255,255,255,0.1)' },
                        ticks: { color: '#a1a1aa' }
                    }
                }
            }
        });
    }

    
    renderTopProductsChart(produtosData) {
        const ctx = document.getElementById('topProdutosChart');
        if (!ctx) return;

        // Proteção: Se o Chart.js ainda não carregou, tenta de novo em 500ms
        if (typeof Chart === 'undefined') {
            setTimeout(() => this.renderTopProductsChart(produtosData), 500);
            return;
        }

        if (this.charts.topProdutos) {
            this.charts.topProdutos.destroy();
        }

        const labels = produtosData.map(p => p.nome);
        const data = produtosData.map(p => p.quantidade);

        this.charts.topProdutos = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: data,
                    backgroundColor: [
                        '#E60000', // Senna Red
                        '#FFD700', // Senna Yellow
                        '#ffffff', // White
                        '#a1a1aa', // Gray
                        '#252529'  // Carbon
                    ],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'right', labels: { color: '#ffffff', font: { family: 'Inter' } } }
                }
            }
        });
    }

    async loadPedidosRecentes() {
        try {
            const response = await fetch(`${API_URL}/pedidos?limit=5`, {
                headers: { 'Authorization': `Bearer ${this.token}` }
            });
            
            const pedidos = await response.json();
            const container = document.getElementById('pedidosRecentes');
            
            if (pedidos.length === 0) {
                container.innerHTML = '<p class="loading">Nenhum pedido recente</p>';
                return;
            }
            
            container.innerHTML = pedidos.map(p => `
                <div class="pedido-item">
                    <div class="pedido-info">
                        <h4>${p.codigo}</h4>
                        <span>${p.cliente_nome || 'Cliente não identificado'} • ${new Date(p.created_at).toLocaleTimeString()}</span>
                    </div>
                    <div class="pedido-total">R$ ${p.total.toFixed(2)}</div>
                </div>
            `).join('');
            
        } catch (error) {
            console.error('Erro:', error);
        }
    }
    
    async loadPedidos() {
        // Busca todos os status ativos para o Kanban
        const url = `${API_URL}/pedidos?status=agendado,preparando,pronto`;
        
        try {
            const response = await fetch(url, {
                headers: { 'Authorization': `Bearer ${this.token}` }
            });
            
            if (!response.ok) throw new Error('Falha ao carregar pedidos');
            
            const pedidos = await response.json();
            
            // Limpar colunas
            document.getElementById('kanban-agendado').innerHTML = '';
            document.getElementById('kanban-preparando').innerHTML = '';
            document.getElementById('kanban-pronto').innerHTML = '';
            
            // Contadores
            let counts = { agendado: 0, preparando: 0, pronto: 0 };

            pedidos.forEach(p => {
                const colId = `kanban-${p.status}`;
                const container = document.getElementById(colId);
                
                if (container) {
                    counts[p.status]++;
                    const card = document.createElement('div');
                    card.className = 'k-card';
                    card.innerHTML = `
                        <div class="k-card-header">
                            <span class="k-code">${p.codigo}</span>
                            <span class="k-time">${new Date(p.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                        </div>
                        <div class="k-items">
                            <div style="color: #fff; font-weight: bold; margin-bottom: 4px;">${p.cliente_nome || 'Cliente'}</div>
                            ${p.itens.map(i => `• ${i.quantidade}x ${i.produto_nome}`).join('<br>')}
                            ${p.observacoes ? `<br><em style="color: #f59e0b; font-size: 0.8rem;">Obs: ${p.observacoes}</em>` : ''}
                        </div>
                        <div class="k-actions">
                            ${this.getKanbanButton(p)}
                        </div>
                    `;
                    container.appendChild(card);
                }
            });
            
            // Atualizar badges
            document.getElementById('count-agendado').textContent = counts.agendado;
            document.getElementById('count-preparando').textContent = counts.preparando;
            document.getElementById('count-pronto').textContent = counts.pronto;

        } catch (error) {
            console.error('Erro:', error);
            this.showToast('Erro ao atualizar Kanban', 'error');
        }
    }
    
    getKanbanButton(pedido) {
        if (pedido.status === 'agendado') {
            return `<button class="k-btn next" onclick="admin.updateStatus(${pedido.id}, 'preparando')">Iniciar Preparo ➜</button>`;
        } else if (pedido.status === 'preparando') {
            return `<button class="k-btn next" style="background: #f59e0b; color: black;" onclick="admin.updateStatus(${pedido.id}, 'pronto')">Marcar Pronto ➜</button>`;
        } else if (pedido.status === 'pronto') {
            return `<button class="k-btn next" style="background: #10b981;" onclick="admin.updateStatus(${pedido.id}, 'entregue')">Entregar (Finalizar) ✓</button>`;
        }
        return '';
    }
    
    async updateStatus(pedidoId, status) {
        try {
            const response = await fetch(`${API_URL}/pedidos/${pedidoId}/status?status=${status}`, {
                method: 'PUT',
                headers: { 'Authorization': `Bearer ${this.token}` }
            });
            
            if (response.ok) {
                // this.showToast('Status atualizado!', 'success'); // Opcional, removido para ser mais rápido
                this.loadPedidos();
                this.loadDashboard();
            }
        } catch (error) {
            this.showToast('Erro ao atualizar status', 'error');
        }
    }
    
    async loadProdutos() {
        try {
            const response = await fetch(`${API_URL}/produtos`, {
                headers: { 'Authorization': `Bearer ${this.token}` }
            });
            
            const produtos = await response.json();
            const tbody = document.getElementById('produtosTable');
            
            tbody.innerHTML = produtos.map(p => `
                <tr>
                    <td><img src="${p.imagem_url}" class="product-thumb" onerror="this.src='https://via.placeholder.com/48'"></td>
                    <td>
                        <strong>${p.nome}</strong>
                        ${p.destaque ? ' ⭐' : ''}
                    </td>
                    <td>${p.categoria}</td>
                    <td>R$ ${p.preco.toFixed(2)}</td>
                    <td>
                        <span style="color: ${p.estoque <= p.estoque_minimo ? '#ef4444' : '#10b981'}; font-weight: 600;">
                            ${p.estoque}
                        </span>
                    </td>
                    <td>
                        <span class="status-badge ${p.ativo ? 'pronto' : 'cancelado'}">
                            ${p.ativo ? 'Ativo' : 'Inativo'}
                        </span>
                    </td>
                    <td>
                        <button class="btn-secondary" onclick="admin.editProduct(${p.id})" style="padding: 0.375rem 0.75rem;">Editar</button>
                    </td>
                </tr>
            `).join('');
            
        } catch (error) {
            console.error('Erro:', error);
        }
    }
    
    openProductModal() {
        document.getElementById('productForm').reset();
        document.getElementById('productId').value = '';
        document.getElementById('modalTitle').textContent = 'Novo Produto';
        document.getElementById('productModal').classList.add('open');
    }
    
    closeProductModal() {
        document.getElementById('productModal').classList.remove('open');
    }
    
    async editProduct(id) {
        try {
            const response = await fetch(`${API_URL}/produtos/${id}`, {
                headers: { 'Authorization': `Bearer ${this.token}` }
            });
            
            const produto = await response.json();
            
            document.getElementById('productId').value = produto.id;
            document.getElementById('prodNome').value = produto.nome;
            document.getElementById('prodDescricao').value = produto.descricao || '';
            document.getElementById('prodPreco').value = produto.preco;
            document.getElementById('prodCusto').value = produto.preco_custo || '';
            document.getElementById('prodCategoria').value = produto.categoria;
            document.getElementById('prodEstoque').value = produto.estoque;
            document.getElementById('prodEstoqueMin').value = produto.estoque_minimo;
            document.getElementById('prodImagem').value = produto.imagem_url;
            document.getElementById('prodDestaque').checked = produto.destaque;
            document.getElementById('prodAtivo').checked = produto.ativo;
            
            document.getElementById('modalTitle').textContent = 'Editar Produto';
            document.getElementById('productModal').classList.add('open');
            
        } catch (error) {
            this.showToast('Erro ao carregar produto', 'error');
        }
    }
    
    async saveProduct(event) {
        event.preventDefault();
        
        const id = document.getElementById('productId').value;
        const produto = {
            nome: document.getElementById('prodNome').value,
            descricao: document.getElementById('prodDescricao').value,
            preco: parseFloat(document.getElementById('prodPreco').value),
            preco_custo: parseFloat(document.getElementById('prodCusto').value) || 0,
            categoria: document.getElementById('prodCategoria').value,
            estoque: parseInt(document.getElementById('prodEstoque').value),
            estoque_minimo: parseInt(document.getElementById('prodEstoqueMin').value),
            imagem_url: document.getElementById('prodImagem').value,
            destaque: document.getElementById('prodDestaque').checked,
            ativo: document.getElementById('prodAtivo').checked
        };
        
        try {
            const url = id ? `${API_URL}/produtos/${id}` : `${API_URL}/produtos`;
            const method = id ? 'PUT' : 'POST';
            
            const response = await fetch(url, {
                method: method,
                headers: {
                    'Authorization': `Bearer ${this.token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(produto)
            });
            
            if (response.ok) {
                this.showToast(id ? 'Produto atualizado!' : 'Produto criado!', 'success');
                this.closeProductModal();
                this.loadProdutos();
            } else {
                const error = await response.json();
                throw new Error(error.detail || 'Erro ao salvar');
            }
        } catch (error) {
            this.showToast(error.message, 'error');
        }
    }
    
    async loadConfig() {
        try {
            const response = await fetch(`${API_URL}/config`, {
                headers: { 'Authorization': `Bearer ${this.token}` }
            });
            if (!response.ok) throw new Error('Falha ao carregar configurações');
            
            const configs = await response.json();
            const configMap = configs.reduce((acc, c) => {
                acc[c.chave] = c.valor;
                return acc;
            }, {});

            document.getElementById('configNome').value = configMap.nome_empresa || '';
            document.getElementById('configTelefone').value = configMap.telefone || '';
            document.getElementById('configPix').value = configMap.chave_pix || '';
            document.getElementById('configLogo').value = configMap.logo_url || '';
            document.getElementById('configCor').value = configMap.cor_tema || '#f97316';

            // Aplicar tema visualmente
            this.applyTheme(configMap);

        } catch (error) {
            this.showToast('Erro ao carregar configurações', 'error');
            console.error(error);
        }
    }

    async salvarConfig(event) {
        event.preventDefault();
        const configs = [
            { chave: 'nome_empresa', valor: document.getElementById('configNome').value },
            { chave: 'telefone', valor: document.getElementById('configTelefone').value },
            { chave: 'chave_pix', valor: document.getElementById('configPix').value },
            { chave: 'logo_url', valor: document.getElementById('configLogo').value },
            { chave: 'cor_tema', valor: document.getElementById('configCor').value }
        ];

        try {
            const response = await fetch(`${API_URL}/config`, {
                method: 'PUT',
                headers: {
                    'Authorization': `Bearer ${this.token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(configs)
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Erro ao salvar');
            }

            this.showToast('Configurações salvas com sucesso!', 'success');
            
            // Aplicar alterações imediatamente
            const configMap = configs.reduce((acc, c) => {
                acc[c.chave] = c.valor;
                return acc;
            }, {});
            this.applyTheme(configMap);
            
        } catch (error) {
            this.showToast(error.message, 'error');
        }
    }

    applyTheme(config) {
        // Atualizar Nome e Título
        if (config.nome_empresa) {
            const brandTitle = document.querySelector('.sidebar-brand h1');
            if (brandTitle) brandTitle.textContent = config.nome_empresa;
            document.title = `Painel - ${config.nome_empresa}`;
        }

        // Atualizar Cor
        if (config.cor_tema) {
            document.documentElement.style.setProperty('--primary', config.cor_tema);
            document.documentElement.style.setProperty('--primary-dark', config.cor_tema);
        }
        
        // Atualizar Logo
        if (config.logo_url && config.logo_url.startsWith('http')) {
             const brandIcon = document.querySelector('.brand-icon');
             if (brandIcon) {
                 brandIcon.innerHTML = `<img src="${config.logo_url}" style="width:100%; height:100%; object-fit:cover; border-radius:inherit;">`;
                 brandIcon.style.background = 'transparent';
             }
        }
    }

    async gerarRelatorio() {
        const inicio = document.getElementById('relDataInicio').value;
        const fim = document.getElementById('relDataFim').value;
        
        if (!inicio || !fim) {
            this.showToast('Selecione as datas', 'error');
            return;
        }
        
        try {
            const response = await fetch(`${API_URL}/relatorios/vendas?data_inicio=${inicio}T00:00:00&data_fim=${fim}T23:59:59`, {
                headers: { 'Authorization': `Bearer ${this.token}` }
            });
            
            const data = await response.json();
            const container = document.getElementById('relatorioResultado');
            
            const total = data.vendas.reduce((sum, v) => sum + v.total, 0);
            
            container.innerHTML = `
                <h4 style="margin-bottom: 1rem;">Resumo do Período</h4>
                <div class="stats-grid" style="margin-bottom: 2rem;">
                    <div class="stat-card primary">
                        <div class="stat-info">
                            <span class="stat-label">Total em Vendas</span>
                            <strong class="stat-value">R$ ${total.toFixed(2)}</strong>
                        </div>
                    </div>
                    <div class="stat-card success">
                        <div class="stat-info">
                            <span class="stat-label">Total de Pedidos</span>
                            <strong class="stat-value">${data.vendas.reduce((sum, v) => sum + v.quantidade, 0)}</strong>
                        </div>
                    </div>
                </div>
                
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Data</th>
                            <th>Forma Pagamento</th>
                            <th>Quantidade</th>
                            <th>Total</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.vendas.map(v => `
                            <tr>
                                <td>${new Date(v.data).toLocaleDateString()}</td>
                                <td>${v.forma_pagamento || 'N/A'}</td>
                                <td>${v.quantidade}</td>
                                <td>R$ ${v.total.toFixed(2)}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
            
        } catch (error) {
            this.showToast('Erro ao gerar relatório', 'error');
        }
    }
    
    refreshData() {
        if (this.currentSection === 'dashboard') {
            this.loadDashboard();
        } else if (this.currentSection === 'pedidos') {
            this.loadPedidos();
        }
    }
    
    startAutoRefresh() {
        // Atualizar a cada 10 segundos para o Kanban ficar "vivo"
        setInterval(() => {
            if (document.visibilityState === 'visible') {
                this.refreshData();
            }
        }, 10000);
    }
    
    printOrder(pedidoId) {
        window.open(`${API_URL}/pedidos/${pedidoId}/comprovante`, '_blank');
    }
    
    logout() {
        localStorage.removeItem('token');
        localStorage.removeItem('nome');
        window.location.href = 'login.html';
    }
    
    showToast(message, type = 'info') {
        const container = document.getElementById('toastContainer');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            ${type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ'} 
            ${message}
        `;
        
        container.appendChild(toast);
        
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    // --- MODO LIVE (SIMULAÇÃO) ---
    toggleLiveMode() {
        this.isLive = !this.isLive;
        const btn = document.getElementById('btnLive');
        
        if (this.isLive) {
            btn.innerHTML = '<span style="font-size: 10px;">●</span> LIVE ON';
            btn.classList.add('active');
            this.showToast('Modo Live ativado! Pedidos chegando...', 'success');
            this.startSimulation();
        } else {
            btn.innerHTML = '<span style="font-size: 10px;">●</span> LIVE OFF';
            btn.classList.remove('active');
            clearInterval(this.liveInterval);
        }
    }

    startSimulation() {
        // Tenta criar um pedido a cada 5 a 10 segundos
        this.liveInterval = setInterval(() => {
            if (Math.random() > 0.3) { // 70% de chance de criar
                this.createRandomOrder();
            }
        }, 5000);
    }

    async createRandomOrder() {
        // 1. Buscar produtos ativos para pegar IDs válidos
        let produtos = [];
        try {
            const res = await fetch(`${API_URL}/produtos?ativos=true`);
            if (res.ok) produtos = await res.json();
        } catch (e) {
            console.error("Erro ao buscar produtos para simulação");
        }

        if (produtos.length === 0) {
            console.warn("Sem produtos para simular.");
            return;
        }

        const nomes = ["Ayrton", "Rubinho", "Massa", "Hamilton", "Verstappen", "Leclerc", "Norris", "Alonso", "Vettel", "Schumacher"];
        const cliente = nomes[Math.floor(Math.random() * nomes.length)];
        
        // Gera data para hoje daqui a 30 min
        const data = new Date();
        data.setMinutes(data.getMinutes() + 30);

        // Payload do pedido simulado
        const pedido = {
            itens: [],
            data_retirada: data.toISOString(),
            cliente_nome: cliente,
            cliente_telefone: "11999999999",
            observacoes: "Pedido Simulado (Live Mode)",
            forma_pagamento: "pix"
        };

        // Adiciona um ou mais produtos aleatórios ao pedido
        const qtdItens = Math.floor(Math.random() * 3) + 1;
        for (let i = 0; i < qtdItens; i++) {
            const prod = produtos[Math.floor(Math.random() * produtos.length)];
            pedido.itens.push({
                produto_id: prod.id,
                quantidade: 1,
                observacao: ""
            });
        }

        try {
            const response = await fetch(`${API_URL}/pedidos`, {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.token}`
                },
                body: JSON.stringify(pedido)
            });

            if (response.ok) {
                const novoPedido = await response.json();
                
                // 1. Simular pagamento (para mudar status para 'agendado' e registrar financeiro)
                const payResponse = await fetch(`${API_URL}/pedidos/${novoPedido.id}/pagar?forma_pagamento=pix`, {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${this.token}` }
                });

                if (payResponse.ok) {
                    this.showToast(`🔔 Novo pedido de ${cliente}!`, 'info');
                    this.loadPedidos(); 
                    this.loadDashboard();
                } else {
                    // Fallback: Se o pagamento falhar, força o status para 'agendado' via Admin
                    console.warn("Pagamento falhou, forçando status...");
                    await this.updateStatus(novoPedido.id, 'agendado');
                }
            }
        } catch (e) { 
            console.error("Erro na simulação", e); 
        }
    }
}

const admin = new AdminPanel();