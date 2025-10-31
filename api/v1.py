import os
import time
from functools import lru_cache
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone

import jwt
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

# ------------------------------------------------------------------------------
# App metadata (aparece no Swagger /docs)
# ------------------------------------------------------------------------------
app = FastAPI(
    title="Books to Scrape API",
    version="1.0.0",
    description="API pública de livros coletados de https://books.toscrape.com",
)

# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------
DATA_CSV_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "books.csv")
)

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
JWT_ALG = "HS256"
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

ALLOW_SCRAPER_WRITE = os.getenv("ALLOW_SCRAPER_WRITE", "false").lower() in {
    "1",
    "true",
    "yes",
}

# ------------------------------------------------------------------------------
# Auth models
# ------------------------------------------------------------------------------
class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# ------------------------------------------------------------------------------
# Token helpers
# ------------------------------------------------------------------------------
def create_token(sub: str, minutes: int = 60) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALG)


def decode_token(token: str) -> Dict[str, Any]:
    # tolera pequenos drifts de relógio e ignora validação estrita de iat
    return jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[JWT_ALG],
        options={"verify_iat": False},
        leeway=10,
    )


# ------------------------------------------------------------------------------
# Bearer auth (publica o esquema no OpenAPI -> botão "Authorize" aparece)
# ------------------------------------------------------------------------------
bearer_scheme = HTTPBearer(auto_error=False)

def bearer_auth(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> str:
    if credentials is None or (credentials.scheme or "").lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = (credentials.credentials or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    try:
        decoded = decode_token(token)
        sub = decoded.get("sub", "")
        if not sub:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return sub
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ------------------------------------------------------------------------------
# Data loading
# ------------------------------------------------------------------------------
def _read_csv() -> pd.DataFrame:
    if not os.path.exists(DATA_CSV_PATH):
        # CSV ausente: retorna DF vazio com colunas esperadas
        cols = [
            "id",
            "title",
            "price",
            "rating",
            "availability",
            "category",
            "image_url",
            "product_page_url",
        ]
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(DATA_CSV_PATH)
    # tipos básicos
    for col in ["id", "rating", "availability"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "price" in df.columns:
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
    return df


@lru_cache(maxsize=1)
def load_df() -> pd.DataFrame:
    return _read_csv().copy()


# ------------------------------------------------------------------------------
# Public endpoints
# ------------------------------------------------------------------------------
@app.get("/api/v1/health")
def health():
    df = load_df()
    return {
        "status": "ok",
        "rows": int(df.shape[0]),
        "last_check": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


@app.get("/api/v1/books")
def list_books(
    limit: int = Query(50, ge=1, le=1000),
    order_by: str = Query(
        "id",
        description="Campo para ordenar (id, title, price, rating, availability)",
    ),
    order: str = Query("asc", description="asc|desc"),
    category: Optional[str] = Query(None, description="Filtra por categoria exata"),
):
    df = load_df()
    if category:
        df = df[df["category"] == category]
    if order_by not in df.columns:
        order_by = "id"
    ascending = order.lower() != "desc"
    df = df.sort_values(by=order_by, ascending=ascending)
    if limit:
        df = df.head(limit)
    return df.to_dict(orient="records")


@app.get("/api/v1/books/{book_id}")
def get_book(book_id: int):
    df = load_df()
    row = df[df["id"] == book_id]
    if row.empty:
        raise HTTPException(status_code=404, detail="Book not found")
    return row.iloc[0].to_dict()


@app.get("/api/v1/books/search")
def search_books(
    title: Optional[str] = Query(
        None, description="Busca por substring no título (case-insensitive)"
    ),
    category: Optional[str] = Query(None, description="Filtra por categoria exata"),
):
    df = load_df()
    if title:
        df = df[df["title"].str.contains(title, case=False, na=False)]
    if category:
        df = df[df["category"] == category]
    return df.to_dict(orient="records")


@app.get("/api/v1/categories")
def list_categories():
    df = load_df()
    if "category" not in df.columns:
        return []
    cats = sorted([c for c in df["category"].dropna().unique().tolist()])
    return cats


@app.get("/api/v1/stats/overview")
def stats_overview():
    df = load_df()
    total = int(df.shape[0])
    avg_price = float(df["price"].mean()) if "price" in df.columns and total > 0 else 0.0
    rating_counts = {}
    if "rating" in df.columns:
        vc = df["rating"].value_counts().sort_index()
        rating_counts = {str(int(k)): int(v) for k, v in vc.items()}
    availability_sum = int(df["availability"].sum()) if "availability" in df.columns else 0
    return {
        "total_books": total,
        "avg_price": avg_price,
        "rating_distribution": rating_counts,
        "availability_sum": availability_sum,
    }


@app.get("/api/v1/stats/categories")
def stats_categories():
    df = load_df()
    if df.empty:
        return []
    gb = df.groupby("category", dropna=True)
    out = []
    for cat, g in gb:
        out.append(
            {
                "category": cat,
                "books": int(g.shape[0]),
                "avg_price": float(g["price"].mean()),
                "max_price": float(g["price"].max()),
                "min_price": float(g["price"].min()),
                "avg_rating": float(g["rating"].mean()),
            }
        )
    # ordena por categoria para estabilidade
    out = sorted(out, key=lambda x: (x["category"] or ""))
    return out


# ------------------------------------------------------------------------------
# Auth endpoints (Desafio 1)
# ------------------------------------------------------------------------------
@app.post("/api/v1/auth/login", response_model=TokenOut, tags=["auth"])
def login(payload: LoginIn):
    if payload.username != ADMIN_USER or payload.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(sub=payload.username, minutes=60)
    return TokenOut(access_token=token, expires_in=60 * 60)


@app.post("/api/v1/auth/refresh", response_model=TokenOut, tags=["auth"])
def refresh_token(_: str = Depends(bearer_auth)):
    token = create_token(sub=ADMIN_USER, minutes=60)
    return TokenOut(access_token=token, expires_in=60 * 60)


@app.get("/api/v1/auth/whoami", tags=["auth"])
def whoami(user: str = Depends(bearer_auth)):
    return {"user": user}


# ------------------------------------------------------------------------------
# Admin: trigger scraper (local) — em produção é demonstrativo
# ------------------------------------------------------------------------------
@app.post(
    "/api/v1/scraping/trigger",
    tags=["admin"],
    summary="Dispara o scraper local",
    description=(
        "Executa o scraper e atualiza `data/books.csv`. "
        "Em produção (Vercel) é apenas demonstrativo (filesystem efêmero): não grava."
    ),
)
def scraping_trigger(
    _: str = Depends(bearer_auth),
    limit: Optional[int] = Query(
        20, ge=1, le=2000, description="Quantidade máxima de livros a coletar (None = tudo)."
    ),
    verbose: bool = Query(False, description="Exibe logs detalhados no servidor."),
    delay: float = Query(0.25, ge=0.0, le=2.0, description="Atraso entre requisições (segundos)."),
    retries: int = Query(
        4, ge=0, le=10, description="Tentativas de retry por requisição (além do retry da sessão HTTP)."
    ),
    checkpoint_every: int = Query(
        100, ge=10, le=1000, description="Salva CSV a cada N livros (checkpoint)."
    ),
    resume: bool = Query(True, description="Retoma do CSV existente, pulando o que já foi coletado."),
):
    if not ALLOW_SCRAPER_WRITE:
        return {
            "ok": False,
            "detail": "Em produção (Vercel) este endpoint é apenas demonstrativo. Rode o scraper localmente.",
        }

    t0 = time.time()
    # Import tardio para não carregar dependências do scraper na inicialização
    from scripts.scrape_books import run as run_scraper  # type: ignore

    output_csv = DATA_CSV_PATH
    run_scraper(
        output_csv=output_csv,
        polite_delay=delay,
        verbose=verbose,
        retries=retries,
        limit=limit,
        checkpoint_every=checkpoint_every,
        resume=resume,
    )
    # Recarrega o DF em memória
    load_df.cache_clear()

    return {
        "ok": True,
        "elapsed_sec": round(time.time() - t0, 2),
        "written": output_csv,
        "limit": limit,
        "verbose": verbose,
        "delay": delay,
        "retries": retries,
        "checkpoint_every": checkpoint_every,
        "resume": resume,
    }
