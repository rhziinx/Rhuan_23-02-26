from typing import Optional, List
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, status, BackgroundTasks, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import Response, FileResponse, StreamingResponse, HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, text, select, update, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship, selectinload
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import secrets
import os
import time
from enum import Enum
import uuid
import logging
from logging.handlers import RotatingFileHandler
import csv
import io

# --- CONFIGURAÇÃO DE LOGGING PROFISSIONAL ---
logger = logging.getLogger("cantina_api")
logger.setLevel(logging.INFO)

file_handler = RotatingFileHandler("sistema.log", maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
logger.addHandler(console_handler)

# --- RATE LIMITING (SEGURANÇA SAAS) ---
limiter = Limiter(key_func=get_remote_address)

# Configurações de segurança
SECRET_KEY = os.getenv("SECRET_KEY", "SUA_CHAVE_SECRETA_FIXA_PARA_DEV_NAO_USE_RANDOM_EM_PROD")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 horas

# Configuração de senha
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
security = HTTPBearer()

# --- DATABASE ASYNC (PREPARADO PARA POSTGRESQL) ---
# Mantemos a lógica híbrida: SQLite local (escola) e preparado para Postgres (futuro)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./cantina_v3.db")

IS_PRODUCTION = os.getenv("ENV") == "production"

engine = create_async_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    pool_pre_ping=True,
    echo=False
)

# Sessão Assíncrona Factory
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

# --- ENUMS ---
class StatusPedido(str, Enum):
    AGUARDANDO_PAGAMENTO = "aguardando_pagamento"
    AGENDADO = "agendado"
    PREPARANDO = "preparando"    
    PRONTO = "pronto"
    ENTREGUE = "entregue"
    CANCELADO = "cancelado"

class FormaPagamento(str, Enum):
    PIX = "pix"
    CARTAO = "cartao"
    DINHEIRO = "dinheiro"
    VR = "vr"
    VA = "va"

class CategoriaProduto(str, Enum):
    LANCHES = "Lanches"
    BEBIDAS = "Bebidas"
    DOCES = "Doces"
    COMBOS = "Combos"
    SALGADOS = "Salgados"
    OUTROS = "Outros"

# --- TABELAS (MODELS) ---
class Usuario(Base):
    __tablename__ = "usuarios"
    
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    usuario = Column(String(50), unique=True, index=True, nullable=False)
    senha_hash = Column(String(255), nullable=False)
    nome = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=True)
    telefone = Column(String(20), nullable=True)
    is_admin = Column(Boolean, default=False)
    is_ativo = Column(Boolean, default=True)
    ultimo_acesso = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    
    pedidos = relationship("Pedido", back_populates="usuario")
    logs = relationship("LogSistema", back_populates="usuario")

class Produto(Base):
    __tablename__ = "produtos"
    
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    nome = Column(String(100), nullable=False, index=True)
    descricao = Column(Text, nullable=True)
    preco = Column(Float, nullable=False)
    preco_custo = Column(Float, default=0.0)
    categoria = Column(String(50), default=CategoriaProduto.LANCHES.value)
    imagem_url = Column(String(500), default="https://via.placeholder.com/400x300?text=Produto")
    estoque = Column(Integer, default=0)
    estoque_minimo = Column(Integer, default=5)
    ativo = Column(Boolean, default=True)
    destaque = Column(Boolean, default=False)
    tempo_preparo = Column(Integer, default=10)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    itens_pedido = relationship("ItemPedido", back_populates="produto")

class Pedido(Base):
    __tablename__ = "pedidos"
    
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    codigo = Column(String(20), unique=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    cliente_nome = Column(String(100), nullable=True)
    cliente_telefone = Column(String(20), nullable=True)
    status = Column(String(50), default=StatusPedido.AGUARDANDO_PAGAMENTO.value)
    data_retirada = Column(DateTime, nullable=False)
    forma_pagamento = Column(String(50), nullable=True)
    total = Column(Float, nullable=False)
    desconto = Column(Float, default=0.0)
    taxa_entrega = Column(Float, default=0.0)
    observacoes = Column(Text, nullable=True)
    mesa = Column(String(10), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    pago_at = Column(DateTime, nullable=True)
    entregue_at = Column(DateTime, nullable=True)
    
    usuario = relationship("Usuario", back_populates="pedidos")
    itens = relationship("ItemPedido", back_populates="pedido", cascade="all, delete-orphan")

class ItemPedido(Base):
    __tablename__ = "itens_pedido"
    
    id = Column(Integer, primary_key=True)
    pedido_id = Column(Integer, ForeignKey("pedidos.id"))
    produto_id = Column(Integer, ForeignKey("produtos.id"))
    quantidade = Column(Integer, nullable=False)
    preco_unitario = Column(Float, nullable=False)
    observacao = Column(String(255), nullable=True)
    
    pedido = relationship("Pedido", back_populates="itens")
    produto = relationship("Produto", back_populates="itens_pedido")

    @property
    def produto_nome(self):
        return self.produto.nome if self.produto else "Produto removido"

class Configuracao(Base):
    __tablename__ = "configuracoes"
    
    id = Column(Integer, primary_key=True)
    chave = Column(String(100), unique=True, nullable=False)
    valor = Column(Text, nullable=True)
    descricao = Column(String(255), nullable=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class LogSistema(Base):
    __tablename__ = "logs_sistema"
    
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    acao = Column(String(100), nullable=False)
    detalhes = Column(Text, nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=func.now())
    
    usuario = relationship("Usuario", back_populates="logs")

class Cupom(Base):
    __tablename__ = "cupons"

    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(50), unique=True, index=True, nullable=False)
    descricao = Column(String(255))
    tipo_desconto = Column(String(20), default="percentual")
    valor_desconto = Column(Float, nullable=False)
    ativo = Column(Boolean, default=True)
    usos_maximos = Column(Integer, default=0)

class UsuarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    uuid: str
    usuario: str
    email: Optional[str] = None
    is_admin: bool = False

class UsuarioCreate(BaseModel):
    usuario: str = Field(..., min_length=3, max_length=50)
    senha: str = Field(..., min_length=6)
    nome: str = Field(..., min_length=2, max_length=100)
    email: Optional[str] = None
    is_admin: bool = False

class ProdutoCreate(BaseModel):
    nome: str = Field(..., min_length=2, max_length=100)
    descricao: Optional[str] = Field(None, max_length=500)
    preco: float = Field(..., gt=0)
    preco_custo: Optional[float] = Field(0, ge=0)
    categoria: CategoriaProduto = CategoriaProduto.LANCHES
    imagem_url: Optional[str] = "https://via.placeholder.com/400x300?text=Produto"
    estoque: int = Field(0, ge=0)
    estoque_minimo: int = Field(5, ge=0)
    tempo_preparo: int = Field(10, ge=1)
    destaque: bool = False

class ProdutoUpdate(BaseModel):
    nome: Optional[str] = Field(None, min_length=2, max_length=100)
    descricao: Optional[str] = None
    preco: Optional[float] = Field(None, gt=0)
    preco_custo: Optional[float] = Field(None, ge=0)
    categoria: Optional[CategoriaProduto] = None
    imagem_url: Optional[str] = None
    estoque: Optional[int] = Field(None, ge=0)
    estoque_minimo: Optional[int] = Field(None, ge=0)
    tempo_preparo: Optional[int] = Field(None, ge=1)
    ativo: Optional[bool] = None
    destaque: Optional[bool] = None

class ProdutoResponse(BaseModel):
    id: int
    uuid: str
    nome: str
    descricao: Optional[str]
    preco: float
    categoria: str
    imagem_url: Optional[str] = None
    estoque: int
    estoque_minimo: int
    ativo: bool
    destaque: bool
    tempo_preparo: int
    
    model_config = ConfigDict(from_attributes=True)

class ItemPedidoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    produto_nome: str
    quantidade: int
    preco_unitario: float
    observacao: Optional[str] = None

class ItemPedidoCreate(BaseModel):
    produto_id: int
    quantidade: int = Field(..., ge=1, le=100, description="Quantidade máxima de 100 itens por produto")
    observacao: Optional[str] = Field(None, max_length=150, description="Observação curta para o item")

class PedidoCreate(BaseModel):
    itens: List[ItemPedidoCreate] = Field(..., min_length=1, description="O pedido deve conter pelo menos um item")
    data_retirada: datetime
    cliente_nome: Optional[str] = Field(None, max_length=100)
    cliente_telefone: Optional[str] = Field(None, max_length=20)
    mesa: Optional[str] = Field(None, max_length=10)
    observacoes: Optional[str] = Field(None, max_length=500, description="Observações gerais do pedido")
    desconto: Optional[float] = Field(0, ge=0)
    taxa_entrega: Optional[float] = Field(0, ge=0)

class PedidoResponse(BaseModel):
    id: int
    uuid: str
    codigo: str
    cliente_nome: Optional[str]
    status: str
    data_retirada: Optional[datetime]
    forma_pagamento: Optional[str]
    total: float
    desconto: float
    taxa_entrega: float
    mesa: Optional[str]
    created_at: datetime
    itens: List[ItemPedidoResponse]
    
    model_config = ConfigDict(from_attributes=True)

class LoginRequest(BaseModel):
    usuario: str
    senha: str

class ConfigUpdate(BaseModel):
    chave: str
    valor: str

class ConfiguracaoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    chave: str
    valor: Optional[str] = None
    descricao: Optional[str] = None

class RecoveryRequest(BaseModel):
    email: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioResponse
    expires_in: int

class DashboardStats(BaseModel):
    total_vendas_hoje: float
    total_pedidos_hoje: int
    ticket_medio_hoje: float
    produtos_baixo_estoque: int
    pedidos_pendentes: int
    vendas_semana: List[dict]
    top_produtos: List[dict]

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- WEBSOCKET MANAGER (REAL-TIME) ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        # Envia mensagem para todos os admins conectados
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                # Se falhar enviar, removemos a conexão morta
                self.disconnect(connection)

manager = ConnectionManager()

# --- MIDDLEWARE DE PERFORMANCE (SAAS MONITORING) ---
# Mede o tempo exato de processamento de cada requisição.
# Essencial para saber se o servidor está lento.
async def performance_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = time.perf_counter() - start_time
    # Adiciona header com o tempo de resposta (bom para debug)
    response.headers["X-Process-Time"] = str(process_time)
    # Loga se for lento (> 0.5s)
    if process_time > 0.5:
        logger.warning(f"Lentidão detectada: {request.method} {request.url.path} demorou {process_time:.4f}s")
    return response

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- MIGRATIONS E SETUP INICIAL ---
    async with engine.begin() as conn:
        # Cria tabelas se não existirem
        await conn.run_sync(Base.metadata.create_all)
        
        # Otimização WAL para SQLite
        if "sqlite" in DATABASE_URL:
            await conn.execute(text("PRAGMA journal_mode=WAL;"))
            await conn.execute(text("PRAGMA synchronous=NORMAL;"))
            logger.info("SQLite WAL Mode ativado (Melhor performance de concorrência)")

    async with AsyncSessionLocal() as db:
        try:
            # Verifica Admin
            result = await db.execute(select(Usuario).where(Usuario.usuario == "admin"))
            admin = result.scalars().first()
            
            if not admin:
                admin = Usuario(
                    usuario="admin",
                    senha_hash=get_password_hash("admin123"),
                    nome="Administrador",
                    email="admin@cantina.com",
                    is_admin=True,
                    is_ativo=True
                )
                db.add(admin)
                await db.commit()
                logger.info("Usuário admin criado: admin / admin123")
            
            # Configurações padrão
            configs_padrao = [
                ("nome_empresa", "Cantina Digital", "Nome da empresa exibido no sistema"),
                ("telefone", "", "Telefone para contato"),
                ("endereco", "", "Endereço da cantina"),
                ("horario_funcionamento", "07:00-18:00", "Horário de funcionamento"),
                ("tempo_medio_preparo", "15", "Tempo médio de preparo em minutos"),
                ("chave_pix", "", "Chave PIX para recebimentos"),
                ("taxa_entrega", "0", "Taxa de entrega padrão"),
                ("logo_url", "", "URL do logotipo da empresa"),
                ("cor_tema", "#E10600", "Cor principal do tema (hex)"),
            ]
            
            for chave, valor, descricao in configs_padrao:
                res = await db.execute(select(Configuracao).where(Configuracao.chave == chave))
                if not res.scalars().first():
                    db.add(Configuracao(chave=chave, valor=valor, descricao=descricao))
            
            # Produtos de teste
            res_prod = await db.execute(select(func.count(Produto.id)))
            count = res_prod.scalar()
            
            if count == 0:
                produtos_senna = [
                {
                    "nome": "Combo Pole Position",
                    "descricao": "Hambúrguer duplo artesanal, cheddar inglês, bacon crocante e maionese da casa. Acompanha batatas rústicas.",
                    "preco": 34.90,
                    "categoria": "Combos",
                    "imagem_url": "https://images.unsplash.com/photo-1594212699903-ec8a3eca50f5?w=800&q=80",
                    "estoque": 50,
                    "destaque": True,
                    "tempo_preparo": 15
                },
                {
                    "nome": "Sanduíche do Campeão",
                    "descricao": "Ciabatta, frango grelhado, pesto de manjericão, mussarela de búfala e tomate seco.",
                    "preco": 22.50,
                    "categoria": "Lanches",
                    "imagem_url": "https://images.unsplash.com/photo-1553909489-cd47e3b4430f?w=800&q=80",
                    "estoque": 30,
                    "destaque": True,
                    "tempo_preparo": 10
                },
                {
                    "nome": "Energético S do Senna",
                    "descricao": "Dose extra de energia para acelerar o seu dia. Lata 473ml.",
                    "preco": 14.00,
                    "categoria": "Bebidas",
                    "imagem_url": "https://images.unsplash.com/photo-1622483767028-3f66f32aef97?w=800&q=80",
                    "estoque": 100,
                    "destaque": False,
                    "tempo_preparo": 0
                },
                {
                    "nome": "Grand Prix Chocolate",
                    "descricao": "Fatia de bolo de chocolate belga intenso com cobertura de ganache e raspas de ouro.",
                    "preco": 18.90,
                    "categoria": "Doces",
                    "imagem_url": "https://images.unsplash.com/photo-1578985545062-69928b1d9587?w=800&q=80",
                    "estoque": 20,
                    "destaque": True,
                    "tempo_preparo": 0
                }
            ]
                for p in produtos_senna:
                    db.add(Produto(**p))
                await db.commit()
                logger.info("Produtos temáticos criados")
        except Exception as e:
            logger.error(f"Erro na inicialização: {e}")
    yield

# FastAPI App
app = FastAPI(
    title="Cantina Enterprise API",
    description="API profissional para gestão de cantinas e restaurantes",
    version="2.0.1 Stable",
    docs_url="/docs" if os.getenv("ENV") != "production" else None,
    lifespan=lifespan
)

app.middleware("http")(performance_middleware)

# Configurar Rate Limiter no App
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS configurado para produção
if IS_PRODUCTION:
    # Em produção, liste EXATAMENTE os domínios permitidos
    origins = ["https://sua-cantina.com", "https://admin.sua-cantina.com"]
else:
    # Em dev, permite tudo
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware de Compressão (Melhora performance em redes móveis)
app.add_middleware(GZipMiddleware, minimum_size=1000)

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

# Dependency
async def get_db():
    async with AsyncSessionLocal() as db:
        yield db

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: AsyncSession = Depends(get_db)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        usuario_id: str = payload.get("sub")
        if usuario_id is None:
            raise HTTPException(status_code=401, detail="Token inválido")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")
    
    result = await db.execute(select(Usuario).where(Usuario.usuario == usuario_id))
    usuario = result.scalars().first()
    
    if usuario is None or not usuario.is_ativo:
        raise HTTPException(status_code=401, detail="Usuário não encontrado ou inativo")
    return usuario

@app.get("/health")
@limiter.limit("5/minute")
async def health_check(request: Request, db: AsyncSession = Depends(get_db)):
    """Rota para monitoramento verificar se a API e o Banco estão vivos"""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected", "timestamp": datetime.now(timezone.utc)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database connection failed: {str(e)}")

# --- WEBSOCKET ENDPOINT ---
@app.websocket("/ws/pedidos")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Mantém a conexão viva e aguarda comandos (ping/pong)
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/config/public")
@limiter.limit("20/minute")
async def get_public_config(request: Request, db: AsyncSession = Depends(get_db)):
    """Retorna configurações públicas para o frontend"""
    chaves = ["nome_empresa", "chave_pix", "telefone", "logo_url", "cor_tema"]
    result = await db.execute(select(Configuracao).where(Configuracao.chave.in_(chaves)))
    configs = result.scalars().all()
    return {c.chave: c.valor for c in configs}

@app.get("/config", response_model=List[ConfiguracaoResponse])
async def get_all_configs(db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    result = await db.execute(select(Configuracao))
    return result.scalars().all()

@app.put("/config")
async def update_configs(configs: List[ConfigUpdate], db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    for config_item in configs:
        await db.execute(
            update(Configuracao).where(Configuracao.chave == config_item.chave).values(valor=config_item.valor)
        )
    
    await db.commit()
    await log_acao(db, "ATUALIZAR_CONFIG", current_user.id, "Configurações do sistema atualizadas")
    return {"msg": "Configurações salvas com sucesso"}


async def gerar_codigo_pedido(db: AsyncSession) -> str:
    """Gera código único para pedido (PED-001234)"""
    result = await db.execute(select(Pedido).order_by(Pedido.id.desc()).limit(1))
    ultimo = result.scalars().first()
    numero = 1 if not ultimo else ultimo.id + 1
    return f"PED-{numero:06d}"

async def log_acao(db: AsyncSession, acao: str, usuario_id: Optional[int] = None, detalhes: Optional[str] = None, ip: Optional[str] = None):
    """Registra ação no log do sistema"""
    log = LogSistema(usuario_id=usuario_id, acao=acao, detalhes=detalhes, ip_address=ip)
    db.add(log)
    await db.commit()

# Endpoints de Autenticação
@app.post("/auth/login", response_model=TokenResponse)
@limiter.limit("5/minute") # Rate Limit automático pelo SlowAPI
async def login(login_data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    
    result = await db.execute(select(Usuario).where(Usuario.usuario == login_data.usuario))
    usuario = result.scalars().first()
    
    if not usuario or not verify_password(login_data.senha, usuario.senha_hash):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    
    if not usuario.is_ativo:
        raise HTTPException(status_code=403, detail="Usuário desativado")
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": usuario.usuario, "id": usuario.id, "is_admin": usuario.is_admin},
        expires_delta=access_token_expires
    )
    
    usuario.ultimo_acesso = datetime.now(timezone.utc)
    await db.commit()
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "usuario": usuario,
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }

@app.post("/auth/refresh")
async def refresh_token(current_user: Usuario = Depends(get_current_user)):
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": current_user.usuario, "id": current_user.id, "is_admin": current_user.is_admin},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/auth/recuperar-senha")
@limiter.limit("3/hour")
async def recuperar_senha(request: Request, recovery: RecoveryRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Usuario).where(Usuario.email == recovery.email))
    user = result.scalars().first()
    if user:
        logger.info(f"Solicitação de recuperação de senha para: {user.email}")
    return {"msg": "Se o e-mail estiver cadastrado, você receberá as instruções."}

# Endpoints de Usuários
@app.post("/usuarios", response_model=UsuarioResponse)
async def criar_usuario(usuario: UsuarioCreate, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    res = await db.execute(select(Usuario).where(Usuario.usuario == usuario.usuario))
    if res.scalars().first():
        raise HTTPException(status_code=400, detail="Usuário já existe")
    
    db_usuario = Usuario(
        usuario=usuario.usuario,
        senha_hash=get_password_hash(usuario.senha),
        nome=usuario.nome,
        email=usuario.email,
        is_admin=usuario.is_admin
    )
    db.add(db_usuario)
    await db.commit()
    await db.refresh(db_usuario)
    
    await log_acao(db, "CRIAR_USUARIO", current_user.id, f"Usuário {usuario.usuario} criado")
    return db_usuario

@app.get("/usuarios/me", response_model=UsuarioResponse)
async def get_me(current_user: Usuario = Depends(get_current_user)):
    return current_user

# Endpoints de Produtos
@app.get("/produtos", response_model=List[ProdutoResponse])
async def listar_produtos(
    categoria: Optional[str] = None,
    ativos: Optional[bool] = None,
    destaque: Optional[bool] = None,
    busca: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(Produto)
    
    if ativos is not None:
        query = query.where(Produto.ativo == ativos)
    if categoria:
        query = query.where(Produto.categoria == categoria)
    if destaque is not None: 
        query = query.where(Produto.destaque == destaque)
    if busca:
        query = query.where(Produto.nome.ilike(f"%{busca}%"))
    
    result = await db.execute(query.order_by(Produto.nome))
    return result.scalars().all()

@app.get("/produtos/{produto_id}", response_model=ProdutoResponse)
async def obter_produto(produto_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Produto).where(Produto.id == produto_id))
    produto = result.scalars().first()
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return produto

@app.post("/produtos", response_model=ProdutoResponse)
async def criar_produto(
    produto: ProdutoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    db_produto = Produto(**produto.model_dump())
    db.add(db_produto)
    await db.commit()
    await db.refresh(db_produto)
    
    await log_acao(db, "CRIAR_PRODUTO", current_user.id, f"Produto {produto.nome} criado")
    return db_produto

@app.put("/produtos/{produto_id}", response_model=ProdutoResponse)
async def atualizar_produto(
    produto_id: int,
    produto: ProdutoUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    result = await db.execute(select(Produto).where(Produto.id == produto_id))
    db_produto = result.scalars().first()
    if not db_produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    
    update_data = produto.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_produto, field, value)
    
    await db.commit()
    await db.refresh(db_produto)
    
    await log_acao(db, "ATUALIZAR_PRODUTO", current_user.id, f"Produto {produto_id} atualizado")
    return db_produto

@app.delete("/produtos/{produto_id}")
async def deletar_produto(
    produto_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    result = await db.execute(select(Produto).where(Produto.id == produto_id))
    db_produto = result.scalars().first()
    if not db_produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    
    # Soft delete - apenas desativa
    db_produto.ativo = False
    await db.commit()
    
    await log_acao(db, "DESATIVAR_PRODUTO", current_user.id, f"Produto {produto_id} desativado")
    return {"msg": "Produto desativado com sucesso"}

# --- ROTA DE BACKUP (SEGURANÇA) ---
@app.get("/admin/backup_db")
async def download_backup_db(current_user: Usuario = Depends(get_current_user)):
    """Permite que o admin baixe uma cópia do banco de dados SQLite"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    # Nome do arquivo de banco definido no DATABASE_URL ou padrão
    db_filename = "cantina_v3.db"
    
    if not os.path.exists(db_filename):
        raise HTTPException(status_code=404, detail="Arquivo de banco de dados não encontrado")
    
    filename_download = f"backup_cantina_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    return FileResponse(path=db_filename, filename=filename_download, media_type='application/x-sqlite3')

# --- ROTA DE RESET (PERIGO / UTILITÁRIO) ---
@app.delete("/admin/reset_db")
async def reset_database(
    confirmacao: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """PERIGO: Apaga todos os pedidos e logs! Útil para limpar testes."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    if not confirmacao:
        raise HTTPException(status_code=400, detail="Para zerar, você deve marcar 'confirmacao' como true")
    
    # Limpar tabelas de movimento (Mantém Produtos e Usuários)
    await db.execute(text("DELETE FROM itens_pedido"))
    await db.execute(text("DELETE FROM pedidos"))
    await db.execute(text("DELETE FROM logs_sistema"))
    
    await db.commit()
    
    await log_acao(db, "RESET_COMPLETO", current_user.id, "Banco de dados limpo via Admin")
    return {"msg": "Sistema limpo! Todos os pedidos e históricos foram apagados."}

@app.get("/produtos/estoque/baixo", response_model=List[ProdutoResponse])
async def produtos_baixo_estoque(db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    result = await db.execute(select(Produto).where(
        Produto.ativo == True,
        Produto.estoque <= Produto.estoque_minimo
    ))
    return result.scalars().all()

# Endpoints de Pedidos
@app.post("/pedidos", response_model=PedidoResponse)
@limiter.limit("5/minute")
async def criar_pedido(request: Request, pedido: PedidoCreate, db: AsyncSession = Depends(get_db)):
    # Calcular total e verificar estoque
    total = 0
    itens_para_criar = []
    
    for item in pedido.itens:
        # --- CORREÇÃO DE CONCORRÊNCIA (ATOMIC UPDATE) ---
        stmt = update(Produto).where(
            Produto.id == item.produto_id,
            Produto.ativo == True,
            Produto.estoque >= item.quantidade
        ).values(estoque=Produto.estoque - item.quantidade)
        
        result_update = await db.execute(stmt)
        
        if result_update.rowcount == 0:
            # Se nenhuma linha foi afetada, ou o produto não existe ou não tem estoque
            await db.rollback() 
            raise HTTPException(
                status_code=400, 
                detail=f"Estoque insuficiente ou produto indisponível para o ID {item.produto_id}. Tente novamente."
            )
            
        res_p = await db.execute(select(Produto).where(Produto.id == item.produto_id))
        produto = res_p.scalars().first()
        
        preco_unitario = produto.preco
        total += preco_unitario * item.quantidade
        
        itens_para_criar.append({
            "produto_id": item.produto_id,
            "quantidade": item.quantidade,
            "preco_unitario": preco_unitario,
            "observacao": item.observacao
        })
    
    # Aplicar desconto e taxa
    total = total + (pedido.taxa_entrega or 0) - (pedido.desconto or 0)
    if total < 0:
        total = 0
    
    # Criar pedido
    db_pedido = Pedido(
        codigo=await gerar_codigo_pedido(db),
        cliente_nome=pedido.cliente_nome,
        data_retirada=pedido.data_retirada,
        cliente_telefone=pedido.cliente_telefone,
        mesa=pedido.mesa,
        total=total,
        desconto=pedido.desconto or 0,
        taxa_entrega=pedido.taxa_entrega or 0,
        observacoes=pedido.observacoes,
        status=StatusPedido.AGUARDANDO_PAGAMENTO.value
    )
    db.add(db_pedido)
    await db.flush()  # Para obter o ID
    
    # Criar itens
    for item_data in itens_para_criar:
        db_item = ItemPedido(pedido_id=db_pedido.id, **item_data)
        db.add(db_item)
    
    await db.commit()
    
    # Recarregar com relacionamentos
    result = await db.execute(select(Pedido).options(selectinload(Pedido.itens).selectinload(ItemPedido.produto)).where(Pedido.id == db_pedido.id))
    db_pedido = result.scalars().first()
    
    # Notificar Admin via WebSocket (TURBO 🚀)
    await manager.broadcast({"type": "novo_pedido", "pedido_id": db_pedido.id, "codigo": db_pedido.codigo})
    
    return db_pedido

@app.get("/pedidos", response_model=List[PedidoResponse])
async def listar_pedidos(
    status: Optional[str] = None,
    data_inicio: Optional[datetime] = None,
    data_fim: Optional[datetime] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    # IMPORTANTE: Carregar itens junto (Eager Loading)
    query = select(Pedido).options(selectinload(Pedido.itens).selectinload(ItemPedido.produto))
    
    if status:
        statuses = status.split(',')
        if len(statuses) > 1:
            query = query.where(Pedido.status.in_(statuses))
        else:
            query = query.where(Pedido.status == status)
    if data_inicio:
        query = query.where(Pedido.created_at >= data_inicio)
    if data_fim:
        query = query.where(Pedido.created_at <= data_fim)
    
    result = await db.execute(query.order_by(Pedido.created_at.desc()).offset(offset).limit(limit))
    return result.scalars().all()

@app.get("/pedidos/{pedido_id}", response_model=PedidoResponse)
async def obter_pedido(pedido_id: int, db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    result = await db.execute(select(Pedido).options(selectinload(Pedido.itens).selectinload(ItemPedido.produto)).where(Pedido.id == pedido_id))
    pedido = result.scalars().first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return pedido

# --- ROTA DE COMPROVANTE (URGENTE PARA IMPRESSÃO) ---
@app.get("/pedidos/{pedido_id}/comprovante", response_class=HTMLResponse)
async def imprimir_comprovante(pedido_id: int, db: AsyncSession = Depends(get_db)):
    """Gera um HTML simples formatado para impressoras térmicas (80mm ou 58mm)"""
    result = await db.execute(select(Pedido).options(selectinload(Pedido.itens).selectinload(ItemPedido.produto)).where(Pedido.id == pedido_id))
    pedido = result.scalars().first()
    
    if not pedido:
        return HTMLResponse("<h1>Pedido não encontrado</h1>", status_code=404)

    # Buscar config para nome da empresa
    res_conf = await db.execute(select(Configuracao).where(Configuracao.chave == "nome_empresa"))
    conf = res_conf.scalars().first()
    nome_empresa = conf.valor if conf else "Cantina Digital"

    html = f"""
    <html>
    <head>
        <title>Pedido {pedido.codigo}</title>
        <style>
            body {{ font-family: 'Courier New', monospace; font-size: 12px; width: 300px; margin: 0; padding: 10px; }}
            .header {{ text-align: center; margin-bottom: 10px; border-bottom: 1px dashed #000; padding-bottom: 5px; }}
            .item {{ display: flex; justify-content: space-between; margin-bottom: 3px; }}
            .total {{ border-top: 1px dashed #000; margin-top: 5px; padding-top: 5px; font-weight: bold; text-align: right; }}
            .footer {{ text-align: center; margin-top: 15px; font-size: 10px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h3>{nome_empresa}</h3>
            <p>Senha: <strong>{pedido.codigo}</strong></p>
            <p>{pedido.created_at.strftime('%d/%m/%Y %H:%M')}</p>
        </div>
        
        <div>
            <p><strong>Cliente:</strong> {pedido.cliente_nome or 'Não inf.'}</p>
            <p><strong>Retirada:</strong> {pedido.data_retirada.strftime('%H:%M')}</p>
            {f'<p><strong>Mesa:</strong> {pedido.mesa}</p>' if pedido.mesa else ''}
        </div>
        
        <hr style="border-top: 1px dashed #000;">
        
    """
    
    for item in pedido.itens:
        html += f"""
        <div class="item">
            <span>{item.quantidade}x {item.produto_nome}</span>
            <span>R$ {item.preco_unitario * item.quantidade:.2f}</span>
        </div>
        """
        if item.observacao:
            html += f"<div style='font-size:10px; margin-bottom:5px;'>OBS: {item.observacao}</div>"

    html += f"""
        <div class="total">TOTAL: R$ {pedido.total:.2f}</div>
        <div class="footer">Pagamento: {pedido.forma_pagamento or 'Pendente'}</div>
        <script>window.print();</script>
    </body>
    </html>
    """
    return html

@app.post("/pedidos/{pedido_id}/pagar")
async def pagar_pedido(
    pedido_id: int,
    forma_pagamento: FormaPagamento,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Pedido).where(Pedido.id == pedido_id))
    pedido = result.scalars().first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    if pedido.status != StatusPedido.AGUARDANDO_PAGAMENTO.value:
        raise HTTPException(status_code=400, detail="Pedido já foi pago ou cancelado")
    
    pedido.status = StatusPedido.AGENDADO.value
    pedido.forma_pagamento = forma_pagamento.value
    pedido.pago_at = datetime.utcnow()
    await db.commit()
    
    await log_acao(db, "AGENDAMENTO", None, 
             f"Pedido {pedido.codigo} agendado e pago via {forma_pagamento.value}")

    # Notificar Admin (WebSocket)
    await manager.broadcast({"type": "update_pedido", "pedido_id": pedido.id, "status": pedido.status})
    
    return {"msg": "Pagamento confirmado e pedido agendado", "pedido": pedido.codigo}

@app.put("/pedidos/{pedido_id}/status")
async def atualizar_status_pedido(
    pedido_id: int,
    status: StatusPedido,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    result = await db.execute(select(Pedido).where(Pedido.id == pedido_id))
    pedido = result.scalars().first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    pedido.status = status.value
    
    if status == StatusPedido.ENTREGUE:
        pedido.entregue_at = datetime.utcnow()
    
    await db.commit()
    
    # Notificar Admin (WebSocket)
    await manager.broadcast({"type": "update_pedido", "pedido_id": pedido.id, "status": status.value})
    
    await log_acao(db, "ATUALIZAR_STATUS", current_user.id, f"Pedido {pedido.codigo} -> {status.value}")
    return {"msg": f"Status atualizado para {status.value}"}

@app.delete("/pedidos/{pedido_id}")
async def cancelar_pedido(
    pedido_id: int,
    motivo: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    # Carregar itens para devolver ao estoque
    result = await db.execute(select(Pedido).options(selectinload(Pedido.itens)).where(Pedido.id == pedido_id))
    pedido = result.scalars().first()

    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    # Devolver estoque (Atomicamente também)
    for item in pedido.itens:
        await db.execute(
            update(Produto).where(Produto.id == item.produto_id).values(estoque=Produto.estoque + item.quantidade)
        )
    
    pedido.status = StatusPedido.CANCELADO.value
    await db.commit()
    
    # Notificar Admin (WebSocket)
    await manager.broadcast({"type": "update_pedido", "pedido_id": pedido.id, "status": "cancelado"})

    await log_acao(db, "CANCELAR_PEDIDO", current_user.id, 
             f"Pedido {pedido.codigo} cancelado. Motivo: {motivo}")
    
    return {"msg": "Pedido cancelado com sucesso"}

# Dashboard e Relatórios
@app.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    hoje = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Vendas agendadas para hoje
    res_vendas = await db.execute(select(func.sum(Pedido.total)).where(
        func.date(Pedido.created_at) == hoje.date(),
        Pedido.status.in_([StatusPedido.AGENDADO.value, StatusPedido.PREPARANDO.value, StatusPedido.PRONTO.value, StatusPedido.ENTREGUE.value])
    ))
    vendas_hoje = res_vendas.scalar() or 0
    
    res_qtd = await db.execute(select(func.count(Pedido.id)).where(
        func.date(Pedido.created_at) == hoje.date()
    ))
    pedidos_hoje = res_qtd.scalar() or 0
    
    ticket_medio = vendas_hoje / pedidos_hoje if pedidos_hoje > 0 else 0
    
    # Produtos com estoque baixo
    res_baixo = await db.execute(select(func.count(Produto.id)).where(
        Produto.ativo == True,
        Produto.estoque <= Produto.estoque_minimo
    ))
    baixo_estoque = res_baixo.scalar() or 0
    
    # Pedidos pendentes
    res_pend = await db.execute(select(func.count(Pedido.id)).where(
        Pedido.status.in_([StatusPedido.AGUARDANDO_PAGAMENTO.value, StatusPedido.AGENDADO.value, StatusPedido.PREPARANDO.value])
    ))
    pendentes = res_pend.scalar() or 0
    
    # Vendas da semana (últimos 7 dias)
    semana_atras = hoje - timedelta(days=7)
    res_semana = await db.execute(select(
        func.date(Pedido.created_at).label('data'),
        func.sum(Pedido.total).label('total'),
        func.count(Pedido.id).label('quantidade')
    ).where(
        Pedido.created_at >= semana_atras,
        Pedido.status.in_([StatusPedido.AGENDADO.value, StatusPedido.PREPARANDO.value, StatusPedido.PRONTO.value, StatusPedido.ENTREGUE.value])
    ).group_by(func.date(Pedido.created_at)))
    vendas_semana = res_semana.all()
    
    # Top 5 Produtos mais vendidos
    res_top = await db.execute(select(
        Produto.nome,
        func.sum(ItemPedido.quantidade).label('total_vendido')
    ).join(ItemPedido, Produto.id == ItemPedido.produto_id)\
     .join(Pedido, Pedido.id == ItemPedido.pedido_id)\
     .where(
        Pedido.status.in_([StatusPedido.AGENDADO.value, StatusPedido.PREPARANDO.value, StatusPedido.PRONTO.value, StatusPedido.ENTREGUE.value])
    ).group_by(Produto.id, Produto.nome).order_by(func.sum(ItemPedido.quantidade).desc()).limit(5))
    top_produtos = res_top.all()
    
    return {
        "total_vendas_hoje": round(vendas_hoje, 2),
        "total_pedidos_hoje": pedidos_hoje,
        "ticket_medio_hoje": round(ticket_medio, 2),
        "produtos_baixo_estoque": baixo_estoque,
        "pedidos_pendentes": pendentes,
        "vendas_semana": [{"data": str(v.data), "total": float(v.total), "quantidade": v.quantidade} for v in vendas_semana],
        "top_produtos": [{"nome": tp.nome, "quantidade": tp.total_vendido} for tp in top_produtos]
    }

@app.get("/relatorios/vendas")
async def relatorio_vendas(
    data_inicio: datetime,
    data_fim: datetime,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    res = await db.execute(select(
        func.date(Pedido.created_at).label('data'),
        func.sum(Pedido.total).label('total'),
        func.count(Pedido.id).label('quantidade'),
        Pedido.forma_pagamento
    ).where(
        Pedido.created_at.between(data_inicio, data_fim),
        Pedido.status.in_([StatusPedido.AGENDADO.value, StatusPedido.PREPARANDO.value, StatusPedido.PRONTO.value, StatusPedido.ENTREGUE.value])
    ).group_by(func.date(Pedido.created_at), Pedido.forma_pagamento))
    vendas = res.all()
    
    return {
        "periodo": {"inicio": data_inicio, "fim": data_fim},
        "vendas": [{"data": str(v.data), "total": float(v.total), "quantidade": v.quantidade, "forma_pagamento": v.forma_pagamento} for v in vendas]
    }

@app.get("/relatorios/exportar/csv")
async def exportar_pedidos_csv(
    data_inicio: Optional[datetime] = None,
    data_fim: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Gera um arquivo CSV dos pedidos para análise em Excel. Se datas não forem passadas, baixa tudo."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    # Montar Query com filtros opcionais
    query = select(Pedido).options(selectinload(Pedido.itens).selectinload(ItemPedido.produto))
    
    if data_inicio:
        query = query.where(Pedido.created_at >= data_inicio)
    if data_fim:
        query = query.where(Pedido.created_at <= data_fim)
        
    # Ordenar e Executar
    res = await db.execute(query.order_by(Pedido.created_at.desc()))
    pedidos = res.scalars().all()
    
    # Criar arquivo em memória (StringIO)
    output = io.StringIO()
    
    # --- CORREÇÃO PARA EXCEL (BOM) ---
    # Adiciona a assinatura UTF-8 para o Excel reconhecer acentos (ç, ã, é) automaticamente
    output.write('\ufeff')
    
    writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_MINIMAL)
    
    # Cabeçalho do CSV
    writer.writerow([
        "ID", "Código", "Data Pedido", "Cliente", "Telefone", 
        "Status", "Total (R$)", "Forma Pagto", "Itens"
    ])
    
    # Linhas
    for p in pedidos:
        # Formatar lista de itens em uma string única
        itens_str = " | ".join([f"{i.quantidade}x {i.produto_nome}" for i in p.itens])
        
        writer.writerow([
            p.id, p.codigo, p.created_at.strftime("%d/%m/%Y %H:%M"), 
            p.cliente_nome, p.cliente_telefone, 
            p.status, f"{p.total:.2f}".replace('.', ','), 
            p.forma_pagamento, itens_str
        ])
    
    output.seek(0)
    
    filename = f"relatorio_pedidos_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})

# Servir arquivos estáticos (Frontend) - DEVE SER O ÚLTIMO
app.mount("/", StaticFiles(directory=".", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)