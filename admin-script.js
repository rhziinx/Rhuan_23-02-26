const API_URL = 'http://localhost:8000';

class AdminPanel {
    constructor() {
        this.token = localStorage.getItem('token');
        this.currentSection = 'dashboard';
        this.charts = {};
        this.currentStatusFilter = 'pago'; // Padrão: mostrar apenas pedidos pagos (Novos)
        
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
                    borderColor: '#f97316',
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
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                return 'R$ ' + value.toFixed(0);
                            }
                        }
                    }
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
        const status = this.currentStatusFilter;
        const url = status ? `${API_URL}/pedidos?status=${status}` : `${API_URL}/pedidos`;
        
        try {
            const response = await fetch(url, {
                headers: { 'Authorization': `Bearer ${this.token}` }
            });
            
            if (!response.ok) throw new Error('Falha ao carregar pedidos');
            
            const pedidos = await response.json();
            const grid = document.getElementById('pedidosGrid');
            
            if (pedidos.length === 0) {
                grid.innerHTML = '<div class="loading">Nenhum pedido encontrado</div>';
                return;
            }
            
            grid.innerHTML = pedidos.map(p => `
                <div class="pedido-card">
                    <div class="pedido-card-header">
                        <span class="pedido-code">${p.codigo}</span>
                        <span class="status-badge ${p.status}">${this.formatStatus(p.status)}</span>
                    </div>
                    <div class="pedido-itens">
                        ${p.itens.map(i => `${i.quantidade}x ${i.produto_nome}`).join('<br>')}
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                        <strong style="color: #f97316; font-size: 1.25rem;">R$ ${p.total.toFixed(2)}</strong>
                        <span style="color: #64748b; font-size: 0.875rem;">
                            ${new Date(p.created_at).toLocaleString()}
                        </span>
                    </div>
                    <div class="pedido-actions">
                        ${this.getStatusActions(p)}
                    </div>
                </div>
            `).join('');
            
        } catch (error) {
            console.error('Erro:', error);
            document.getElementById('pedidosGrid').innerHTML = '<div class="loading" style="color: #ef4444;">Erro ao carregar pedidos. Tente novamente.</div>';
        }
    }
    
    getStatusActions(pedido) {
        const actions = [];
        
        if (pedido.status === 'pago') {
            actions.push(`<button class="btn-primary" onclick="admin.updateStatus(${pedido.id}, 'preparando')">Iniciar Preparo</button>`);
        } else if (pedido.status === 'preparando') {
            actions.push(`<button class="btn-primary" onclick="admin.updateStatus(${pedido.id}, 'pronto')">Marcar Pronto</button>`);
        } else if (pedido.status === 'pronto') {
            actions.push(`<button class="btn-primary" onclick="admin.updateStatus(${pedido.id}, 'entregue')">Entregar</button>`);
        }
        
        actions.push(`<button class="btn-secondary" onclick="admin.printOrder(${pedido.id})">🖨️ Imprimir</button>`);
        
        return actions.join('');
    }
    
    async updateStatus(pedidoId, status) {
        try {
            const response = await fetch(`${API_URL}/pedidos/${pedidoId}/status?status=${status}`, {
                method: 'PUT',
                headers: { 'Authorization': `Bearer ${this.token}` }
            });
            
            if (response.ok) {
                this.showToast('Status atualizado!', 'success');
                this.loadPedidos();
                this.loadDashboard();
            }
        } catch (error) {
            this.showToast('Erro ao atualizar status', 'error');
        }
    }
    
    formatStatus(status) {
        const map = {
            'aguardando_pagamento': 'Aguardando',
            'pago': 'Pago',
            'preparando': 'Preparando',
            'pronto': 'Pronto',
            'entregue': 'Entregue',
            'cancelado': 'Cancelado'
        };
        return map[status] || status;
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
    filtrarPedidos(status) {
        this.currentStatusFilter = status;
        
        // Atualizar visual das abas
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.getAttribute('onclick').includes(`'${status}'`));
        });
        
        this.loadPedidos();
    }
    
    refreshData() {
        if (this.currentSection === 'dashboard') {
            this.loadDashboard();
        }
    }
    
    startAutoRefresh() {
        // Atualizar dashboard a cada 30 segundos se estiver visível
        setInterval(() => {
            if (this.currentSection === 'dashboard' && document.visibilityState === 'visible') {
                this.loadDashboard();
            }
        }, 30000);
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
}

const admin = new AdminPanel();