from typing import Optional, List
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, status, BackgroundTasks, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import Response, FileResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
from sqlalchemy.sql import func
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
import secrets
import os
from enum import Enum
import uuid
import logging
from logging.handlers import RotatingFileHandler
import csv
import io

# --- CONFIGURAÇÃO DE LOGGING PROFISSIONAL ---
# Cria um logger que escreve tanto no console quanto em arquivo
logger = logging.getLogger("cantina_api")
logger.setLevel(logging.INFO)

# 1. Handler de Arquivo (Rotativo: Max 5MB, guarda os últimos 3 arquivos)
file_handler = RotatingFileHandler("sistema.log", maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# 2. Handler de Console (Para ver na janela preta)
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
logger.addHandler(console_handler)

# Dicionário em memória para Rate Limiting de Login (IP -> {tentativas, bloqueado_ate})
login_attempts = {}

# Configurações de segurança
SECRET_KEY = os.getenv("SECRET_KEY", "SUA_CHAVE_SECRETA_FIXA_PARA_DEV_NAO_USE_RANDOM_EM_PROD")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 horas

# Configuração de senha
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
security = HTTPBearer()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./cantina_v3.db")
IS_PRODUCTION = os.getenv("ENV") == "production"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 15} if "sqlite" in DATABASE_URL else {},
    pool_pre_ping=True,
    echo=False
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Enums
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

# Modelos SQLAlchemy
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
    preco_custo = Column(Float, default=0.0)  # Para relatórios de lucro
    categoria = Column(String(50), default=CategoriaProduto.LANCHES.value)
    imagem_url = Column(String(500), default="https://via.placeholder.com/400x300?text=Produto")
    estoque = Column(Integer, default=0)
    estoque_minimo = Column(Integer, default=5)  # Alerta de estoque baixo
    ativo = Column(Boolean, default=True)
    destaque = Column(Boolean, default=False)  # Produtos em destaque
    tempo_preparo = Column(Integer, default=10)  # Minutos
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    itens_pedido = relationship("ItemPedido", back_populates="produto")

class Pedido(Base):
    __tablename__ = "pedidos"
    
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    codigo = Column(String(20), unique=True, index=True)  # Código amigável (ex: PED-001234)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    cliente_nome = Column(String(100), nullable=True)  # Para pedidos sem cadastro
    cliente_telefone = Column(String(20), nullable=True)
    status = Column(String(50), default=StatusPedido.AGUARDANDO_PAGAMENTO.value)
    data_retirada = Column(DateTime, nullable=False)
    forma_pagamento = Column(String(50), nullable=True)
    total = Column(Float, nullable=False)
    desconto = Column(Float, default=0.0)
    taxa_entrega = Column(Float, default=0.0)
    observacoes = Column(Text, nullable=True)
    mesa = Column(String(10), nullable=True)  # Para restaurantes com mesas
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
    preco_unitario = Column(Float, nullable=False)  # Preço no momento da compra
    observacao = Column(String(255), nullable=True)  # "Sem cebola", etc
    
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
    tipo_desconto = Column(String(20), default="percentual") # ou 'fixo'
    valor_desconto = Column(Float, nullable=False)
    ativo = Column(Boolean, default=True)
    usos_maximos = Column(Integer, default=0) # 0 para infinito

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

class RecoveryRequest(BaseModel):
    email: str

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Garantir que as tabelas existam
    Base.metadata.create_all(bind=engine)
    
    # --- OTIMIZAÇÃO DE PERFORMANCE (WAL MODE) ---
    if "sqlite" in DATABASE_URL:
        try:
            with engine.connect() as conn:
                conn.execute(text("PRAGMA journal_mode=WAL;"))
                conn.execute(text("PRAGMA synchronous=NORMAL;"))
                logger.info("SQLite WAL Mode ativado (Melhor performance de concorrência)")
        except Exception as e:
            logger.warning(f"Não foi possível ativar WAL mode: {e}")

    # --- CORRECAO AUTOMATICA DE BANCO DE DADOS (MIGRATION) ---
    try:
        with engine.connect() as conn:
            # Verificar colunas faltantes na tabela pedidos
            result = conn.execute(text("PRAGMA table_info(pedidos)"))
            existing_columns = {row.name for row in result.fetchall()}
            
            missing_cols = [
                ("data_retirada", "DATETIME"),
                ("forma_pagamento", "VARCHAR(50)"),
                ("desconto", "FLOAT DEFAULT 0"),
                ("taxa_entrega", "FLOAT DEFAULT 0"),
                ("mesa", "VARCHAR(10)"),
                ("pago_at", "DATETIME"),
                ("entregue_at", "DATETIME")
            ]
            
            for col_name, col_type in missing_cols:
                if col_name not in existing_columns:
                    logger.info(f"Migrando: Adicionando coluna '{col_name}' na tabela 'pedidos'")
                    conn.execute(text(f"ALTER TABLE pedidos ADD COLUMN {col_name} {col_type}"))
            
            conn.commit()
    except Exception as e:
        logger.error(f"Erro na migracao automatica: {e}")
    # ---------------------------------------------------------

    db = SessionLocal()
    try:
        # Criar usuário admin padrão se não existir
        admin = db.query(Usuario).filter(Usuario.usuario == "admin").first()
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
            db.commit()
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
            if not db.query(Configuracao).filter(Configuracao.chave == chave).first():
                db.add(Configuracao(chave=chave, valor=valor, descricao=descricao))
        
        # Criar um produto de teste se não houver nenhum
        if db.query(Produto).count() == 0:
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
            logger.info("Produtos temáticos Senna criados")

        db.commit()
    finally:
        db.close()
    yield

# FastAPI App
app = FastAPI(
    title="Cantina Enterprise API",
    description="API profissional para gestão de cantinas e restaurantes",
    version="2.0.0",
    docs_url="/docs" if os.getenv("ENV") != "production" else None,
    lifespan=lifespan
)

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
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        usuario_id: str = payload.get("sub")
        if usuario_id is None:
            raise HTTPException(status_code=401, detail="Token inválido")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")
    
    usuario = db.query(Usuario).filter(Usuario.usuario == usuario_id).first()
    if usuario is None or not usuario.is_ativo:
        raise HTTPException(status_code=401, detail="Usuário não encontrado ou inativo")
    return usuario

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Rota para monitoramento verificar se a API e o Banco estão vivos"""
    try:
        # Tenta fazer uma query simples (SELECT 1)
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected", "timestamp": datetime.now(timezone.utc)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database connection failed: {str(e)}")

@app.get("/config/public")
def get_public_config(db: Session = Depends(get_db)):
    """Retorna configurações públicas para o frontend"""
    chaves = ["nome_empresa", "chave_pix", "telefone", "logo_url", "cor_tema"]
    configs = db.query(Configuracao).filter(Configuracao.chave.in_(chaves)).all()
    return {c.chave: c.valor for c in configs}

@app.get("/config", response_model=List[ConfiguracaoResponse])
def get_all_configs(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    return db.query(Configuracao).all()

@app.put("/config")
def update_configs(configs: List[ConfigUpdate], db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    for config_item in configs:
        db.query(Configuracao).filter(Configuracao.chave == config_item.chave).update(
            {"valor": config_item.valor}, synchronize_session=False
        )
    
    db.commit()
    log_acao(db, "ATUALIZAR_CONFIG", current_user.id, "Configurações do sistema atualizadas")
    return {"msg": "Configurações salvas com sucesso"}


def gerar_codigo_pedido(db: Session) -> str:
    """Gera código único para pedido (PED-001234)"""
    ultimo = db.query(Pedido).order_by(Pedido.id.desc()).first()
    numero = 1 if not ultimo else ultimo.id + 1
    return f"PED-{numero:06d}"

def log_acao(db: Session, acao: str, usuario_id: Optional[int] = None, detalhes: Optional[str] = None, ip: Optional[str] = None):
    """Registra ação no log do sistema"""
    log = LogSistema(usuario_id=usuario_id, acao=acao, detalhes=detalhes, ip_address=ip)
    db.add(log)
    db.commit()

# Endpoints de Autenticação
@app.post("/auth/login", response_model=TokenResponse)
def login(login_data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    # --- RATE LIMITING (SEGURANÇA) ---
    client_ip = request.client.host
    now = datetime.now()
    
    # Verificar se o IP está bloqueado
    if client_ip in login_attempts:
        attempt = login_attempts[client_ip]
        if attempt["blocked_until"] and now < attempt["blocked_until"]:
            tempo_restante = (attempt["blocked_until"] - now).seconds
            logger.warning(f"Login bloqueado para IP {client_ip}. Tentativas excessivas.")
            raise HTTPException(
                status_code=429, 
                detail=f"Muitas tentativas falhas. Tente novamente em {tempo_restante} segundos."
            )
        # Se o tempo de bloqueio passou, reseta
        if attempt["blocked_until"] and now >= attempt["blocked_until"]:
            login_attempts[client_ip] = {"count": 0, "blocked_until": None}

    usuario = db.query(Usuario).filter(Usuario.usuario == login_data.usuario).first()
    
    if not usuario or not verify_password(login_data.senha, usuario.senha_hash):
        # Registrar falha
        if client_ip not in login_attempts:
            login_attempts[client_ip] = {"count": 0, "blocked_until": None}
        
        login_attempts[client_ip]["count"] += 1
        
        # Se errou 5 vezes, bloqueia por 15 minutos
        if login_attempts[client_ip]["count"] >= 5:
            login_attempts[client_ip]["blocked_until"] = now + timedelta(minutes=15)
            logger.warning(f"IP {client_ip} bloqueado por 15 min após 5 falhas de login.")
            
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    
    if not usuario.is_ativo:
        raise HTTPException(status_code=403, detail="Usuário desativado")
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": usuario.usuario, "id": usuario.id, "is_admin": usuario.is_admin},
        expires_delta=access_token_expires
    )
    
    # Sucesso: Limpar tentativas do IP
    if client_ip in login_attempts:
        del login_attempts[client_ip]
    
    usuario.ultimo_acesso = datetime.now(timezone.utc)
    db.commit()
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "usuario": usuario,
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }

@app.post("/auth/refresh")
def refresh_token(current_user: Usuario = Depends(get_current_user)):
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": current_user.usuario, "id": current_user.id, "is_admin": current_user.is_admin},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/auth/recuperar-senha")
def recuperar_senha(request: RecoveryRequest, db: Session = Depends(get_db)):
    # Em um sistema real, aqui enviaríamos um e-mail.
    # Por enquanto, vamos apenas simular e logar.
    user = db.query(Usuario).filter(Usuario.email == request.email).first()
    if user:
        logger.info(f"Solicitação de recuperação de senha para: {user.email}")
    return {"msg": "Se o e-mail estiver cadastrado, você receberá as instruções."}

# Endpoints de Usuários
@app.post("/usuarios", response_model=UsuarioResponse)
def criar_usuario(usuario: UsuarioCreate, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    if db.query(Usuario).filter(Usuario.usuario == usuario.usuario).first():
        raise HTTPException(status_code=400, detail="Usuário já existe")
    
    db_usuario = Usuario(
        usuario=usuario.usuario,
        senha_hash=get_password_hash(usuario.senha),
        nome=usuario.nome,
        email=usuario.email,
        is_admin=usuario.is_admin
    )
    db.add(db_usuario)
    db.commit()
    db.refresh(db_usuario)
    
    log_acao(db, "CRIAR_USUARIO", current_user.id, f"Usuário {usuario.usuario} criado")
    return db_usuario

@app.get("/usuarios/me", response_model=UsuarioResponse)
def get_me(current_user: Usuario = Depends(get_current_user)):
    return current_user

# Endpoints de Produtos
@app.get("/produtos", response_model=List[ProdutoResponse])
def listar_produtos(
    categoria: Optional[str] = None,
    ativos: Optional[bool] = None,
    destaque: Optional[bool] = None,
    busca: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Produto)
    
    if ativos is not None:
        query = query.filter(Produto.ativo == ativos)
    if categoria:
        query = query.filter(Produto.categoria == categoria)
    if destaque is not None: 
        query = query.filter(Produto.destaque == destaque)
    if busca:
        query = query.filter(Produto.nome.ilike(f"%{busca}%"))
    
    return query.order_by(Produto.nome).all()

@app.get("/produtos/{produto_id}", response_model=ProdutoResponse)
def obter_produto(produto_id: int, db: Session = Depends(get_db)):
    produto = db.query(Produto).filter(Produto.id == produto_id).first()
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return produto

@app.post("/produtos", response_model=ProdutoResponse)
def criar_produto(
    produto: ProdutoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    db_produto = Produto(**produto.model_dump())
    db.add(db_produto)
    db.commit()
    db.refresh(db_produto)
    
    log_acao(db, "CRIAR_PRODUTO", current_user.id, f"Produto {produto.nome} criado")
    return db_produto

@app.put("/produtos/{produto_id}", response_model=ProdutoResponse)
def atualizar_produto(
    produto_id: int,
    produto: ProdutoUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    db_produto = db.query(Produto).filter(Produto.id == produto_id).first()
    if not db_produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    
    update_data = produto.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_produto, field, value)
    
    db.commit()
    db.refresh(db_produto)
    
    log_acao(db, "ATUALIZAR_PRODUTO", current_user.id, f"Produto {produto_id} atualizado")
    return db_produto

@app.delete("/produtos/{produto_id}")
def deletar_produto(
    produto_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    db_produto = db.query(Produto).filter(Produto.id == produto_id).first()
    if not db_produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    
    # Soft delete - apenas desativa
    db_produto.ativo = False
    db.commit()
    
    log_acao(db, "DESATIVAR_PRODUTO", current_user.id, f"Produto {produto_id} desativado")
    return {"msg": "Produto desativado com sucesso"}

# --- ROTA DE BACKUP (SEGURANÇA) ---
@app.get("/admin/backup_db")
def download_backup_db(current_user: Usuario = Depends(get_current_user)):
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
def reset_database(
    confirmacao: bool = False,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """PERIGO: Apaga todos os pedidos e logs! Útil para limpar testes."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    if not confirmacao:
        raise HTTPException(status_code=400, detail="Para zerar, você deve marcar 'confirmacao' como true")
    
    # Limpar tabelas de movimento (Mantém Produtos e Usuários)
    db.query(ItemPedido).delete()
    db.query(Pedido).delete()
    db.query(LogSistema).delete()
    
    db.commit()
    
    log_acao(db, "RESET_COMPLETO", current_user.id, "Banco de dados limpo via Admin")
    return {"msg": "Sistema limpo! Todos os pedidos e históricos foram apagados."}

@app.get("/produtos/estoque/baixo", response_model=List[ProdutoResponse])
def produtos_baixo_estoque(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    return db.query(Produto).filter(
        Produto.ativo == True,
        Produto.estoque <= Produto.estoque_minimo
    ).all()

# Endpoints de Pedidos
@app.post("/pedidos", response_model=PedidoResponse)
def criar_pedido(pedido: PedidoCreate, db: Session = Depends(get_db)):
    # Calcular total e verificar estoque
    total = 0
    itens_para_criar = []
    
    for item in pedido.itens:
        # --- CORREÇÃO DE CONCORRÊNCIA (ATOMIC UPDATE) ---
        # Em vez de ler e depois escrever, tentamos atualizar diretamente no banco
        # se houver estoque suficiente. Isso evita que dois usuários comprem o último item.
        
        # 1. Tenta decrementar o estoque atomicamente
        rows_affected = db.query(Produto).filter(
            Produto.id == item.produto_id,
            Produto.ativo == True,
            Produto.estoque >= item.quantidade
        ).update(
            {"estoque": Produto.estoque - item.quantidade},
            synchronize_session=False
        )
        
        if rows_affected == 0:
            # Se nenhuma linha foi afetada, ou o produto não existe ou não tem estoque
            db.rollback() # Cancela tudo que foi feito até agora neste loop
            raise HTTPException(
                status_code=400, 
                detail=f"Estoque insuficiente ou produto indisponível para o ID {item.produto_id}. Tente novamente."
            )
            
        produto = db.query(Produto).filter(Produto.id == item.produto_id).first()
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
        codigo=gerar_codigo_pedido(db),
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
    db.flush()  # Para obter o ID
    
    # Criar itens
    for item_data in itens_para_criar:
        db_item = ItemPedido(pedido_id=db_pedido.id, **item_data)
        db.add(db_item)
    
    db.commit()
    db.refresh(db_pedido)
    
    return db_pedido

@app.get("/pedidos", response_model=List[PedidoResponse])
def listar_pedidos(
    status: Optional[str] = None,
    data_inicio: Optional[datetime] = None,
    data_fim: Optional[datetime] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    query = db.query(Pedido)
    
    if status:
        statuses = status.split(',')
        if len(statuses) > 1:
            query = query.filter(Pedido.status.in_(statuses))
        else:
            query = query.filter(Pedido.status == status)
    if data_inicio:
        query = query.filter(Pedido.created_at >= data_inicio)
    if data_fim:
        query = query.filter(Pedido.created_at <= data_fim)
    
    pedidos = query.order_by(Pedido.created_at.desc()).offset(offset).limit(limit).all()
    return pedidos

@app.get("/pedidos/{pedido_id}", response_model=PedidoResponse)
def obter_pedido(pedido_id: int, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    pedido = db.query(Pedido).filter(Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return pedido

@app.post("/pedidos/{pedido_id}/pagar")
def pagar_pedido(
    pedido_id: int,
    forma_pagamento: FormaPagamento,
    db: Session = Depends(get_db)
):
    pedido = db.query(Pedido).filter(Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    if pedido.status != StatusPedido.AGUARDANDO_PAGAMENTO.value:
        raise HTTPException(status_code=400, detail="Pedido já foi pago ou cancelado")
    
    pedido.status = StatusPedido.AGENDADO.value
    pedido.forma_pagamento = forma_pagamento.value
    pedido.pago_at = datetime.utcnow()
    db.commit()
    
    log_acao(db, "AGENDAMENTO", None, 
             f"Pedido {pedido.codigo} agendado e pago via {forma_pagamento.value}")
    
    return {"msg": "Pagamento confirmado e pedido agendado", "pedido": pedido.codigo}

@app.put("/pedidos/{pedido_id}/status")
def atualizar_status_pedido(
    pedido_id: int,
    status: StatusPedido,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    pedido = db.query(Pedido).filter(Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    pedido.status = status.value
    
    if status == StatusPedido.ENTREGUE:
        pedido.entregue_at = datetime.utcnow()
    
    db.commit()
    
    log_acao(db, "ATUALIZAR_STATUS", current_user.id, f"Pedido {pedido.codigo} -> {status.value}")
    return {"msg": f"Status atualizado para {status.value}"}

@app.delete("/pedidos/{pedido_id}")
def cancelar_pedido(
    pedido_id: int,
    motivo: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    pedido = db.query(Pedido).filter(Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    # Devolver estoque (Atomicamente também)
    for item in pedido.itens:
        db.query(Produto).filter(Produto.id == item.produto_id).update(
            {"estoque": Produto.estoque + item.quantidade},
            synchronize_session=False
        )
    
    pedido.status = StatusPedido.CANCELADO.value
    db.commit()
    
    log_acao(db, "CANCELAR_PEDIDO", current_user.id, 
             f"Pedido {pedido.codigo} cancelado. Motivo: {motivo}")
    
    return {"msg": "Pedido cancelado com sucesso"}

# Dashboard e Relatórios
@app.get("/dashboard/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    hoje = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Vendas agendadas para hoje
    vendas_hoje = db.query(func.sum(Pedido.total)).filter(
        func.date(Pedido.created_at) == hoje.date(),
        Pedido.status.in_([StatusPedido.AGENDADO.value, StatusPedido.PREPARANDO.value, StatusPedido.PRONTO.value, StatusPedido.ENTREGUE.value])
    ).scalar() or 0
    
    pedidos_hoje = db.query(Pedido).filter(
        func.date(Pedido.created_at) == hoje.date()
    ).count()
    
    ticket_medio = vendas_hoje / pedidos_hoje if pedidos_hoje > 0 else 0
    
    # Produtos com estoque baixo
    baixo_estoque = db.query(Produto).filter(
        Produto.ativo == True,
        Produto.estoque <= Produto.estoque_minimo
    ).count()
    
    # Pedidos pendentes
    pendentes = db.query(Pedido).filter(
        Pedido.status.in_([StatusPedido.AGUARDANDO_PAGAMENTO.value, StatusPedido.AGENDADO.value, StatusPedido.PREPARANDO.value])
    ).count()
    
    # Vendas da semana (últimos 7 dias)
    semana_atras = hoje - timedelta(days=7)
    vendas_semana = db.query(
        func.date(Pedido.created_at).label('data'),
        func.sum(Pedido.total).label('total'),
        func.count(Pedido.id).label('quantidade')
    ).filter(
        Pedido.created_at >= semana_atras,
        Pedido.status.in_([StatusPedido.AGENDADO.value, StatusPedido.PREPARANDO.value, StatusPedido.PRONTO.value, StatusPedido.ENTREGUE.value])
    ).group_by(func.date(Pedido.created_at)).all()
    
    # Top 5 Produtos mais vendidos
    top_produtos = db.query(
        Produto.nome,
        func.sum(ItemPedido.quantidade).label('total_vendido')
    ).join(ItemPedido, Produto.id == ItemPedido.produto_id)\
     .join(Pedido, Pedido.id == ItemPedido.pedido_id)\
     .filter(
        Pedido.status.in_([StatusPedido.AGENDADO.value, StatusPedido.PREPARANDO.value, StatusPedido.PRONTO.value, StatusPedido.ENTREGUE.value])
    ).group_by(Produto.id, Produto.nome).order_by(func.sum(ItemPedido.quantidade).desc()).limit(5).all()
    
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
def relatorio_vendas(
    data_inicio: datetime,
    data_fim: datetime,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    vendas = db.query(
        func.date(Pedido.created_at).label('data'),
        func.sum(Pedido.total).label('total'),
        func.count(Pedido.id).label('quantidade'),
        Pedido.forma_pagamento
    ).filter(
        Pedido.created_at.between(data_inicio, data_fim),
        Pedido.status.in_([StatusPedido.AGENDADO.value, StatusPedido.PREPARANDO.value, StatusPedido.PRONTO.value, StatusPedido.ENTREGUE.value])
    ).group_by(func.date(Pedido.created_at), Pedido.forma_pagamento).all()
    
    return {
        "periodo": {"inicio": data_inicio, "fim": data_fim},
        "vendas": [{"data": str(v.data), "total": float(v.total), "quantidade": v.quantidade, "forma_pagamento": v.forma_pagamento} for v in vendas]
    }

@app.get("/relatorios/exportar/csv")
def exportar_pedidos_csv(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Gera um arquivo CSV com todos os pedidos para análise em Excel"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    # Buscar todos os pedidos com seus itens
    pedidos = db.query(Pedido).order_by(Pedido.created_at.desc()).all()
    
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