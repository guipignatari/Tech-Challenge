# api/v1.py
import os
import io
import time
from functools import lru_cache
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone

import jwt
import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
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
DATA_CSV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "books.csv"))

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
JWT_ALG = "HS256"
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

ALLOW_SCRAPER_WRITE = os.getenv("ALLOW_SCRAPER_WRITE", "false").lower() in {"1", "true", "yes"}

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


def bearer_auth(authorization: Optional[str] = Header(None)) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = token.strip()  # remove espaços/quebras de linha
    try:
        decoded = decode_token(token)
        return decoded.get("sub", "")
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
        cols = ["id", "title", "price", "rating", "availability", "category", "image_url", "product_page_url"]
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


@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/docs")


# --- Books (ATENÇÃO à ordem das rotas) ----------------------------------------
# As rotas estáticas devem vir ANTES de /api/v1/books/{book_id} para evitar 422.

@app.get("/api/v1/books")
def list_books(
    limit: int = Query(50, ge=1, le=1000),
    order_by: str = Query("id", description="Campo para ordenar (id, title, price, rating, availability)"),
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


@app.get("/api/v1/books/top-rated")
def top_rated_books(
    limit: int = Query(50, ge=1, le=1000),
    min_rating: int = Query(5, ge=0, le=5, description="Filtra livros com rating >= min_rating"),
    category: Optional[str] = Query(None, description="Filtra por categoria exata"),
):
    """Lista os livros com maior avaliação (rating)."""
    df = load_df()
    if "rating" not in df.columns:
        return []
    df = df[pd.to_numeric(df["rating"], errors="coerce").fillna(0) >= min_rating]
    if category:
        df = df[df["category"] == category]
    df = df.sort_values(by=["rating", "price"], ascending=[False, True])
    return df.head(limit).to_dict(orient="records")


@app.get("/api/v1/books/price-range")
def books_price_range(
    min: float = Query(0.0, description="Preço mínimo"),
    max: float = Query(9999.0, description="Preço máximo"),
    limit: int = Query(50, ge=1, le=1000),
    order_by: str = Query("price", description="id|title|price|rating|availability"),
    order: str = Query("asc", description="asc|desc"),
    category: Optional[str] = Query(None, description="Filtra por categoria exata"),
):
    """Filtra livros dentro de uma faixa de preço específica."""
    df = load_df()
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df[(df["price"] >= float(min)) & (df["price"] <= float(max))]
    if category:
        df = df[df["category"] == category]
    if order_by not in df.columns:
        order_by = "price"
    ascending = order.lower() != "desc"
    df = df.sort_values(by=order_by, ascending=ascending)
    return df.head(limit).to_dict(orient="records")


@app.get("/api/v1/books/{book_id}")
def get_book(book_id: int):
    df = load_df()
    row = df[df["id"] == book_id]
    if row.empty:
        raise HTTPException(status_code=404, detail="Book not found")
    return row.iloc[0].to_dict()


@app.get("/api/v1/books/search")
def search_books(
    title: Optional[str] = Query(None, description="Busca por substring no título (case-insensitive)"),
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
@app.post("/api/v1/auth/login", response_model=TokenOut)
def login(payload: LoginIn):
    if payload.username != ADMIN_USER or payload.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(sub=payload.username, minutes=60)
    return TokenOut(access_token=token, expires_in=60 * 60)


@app.post("/api/v1/auth/refresh", response_model=TokenOut)
def refresh_token(_: str = Depends(bearer_auth)):
    token = create_token(sub=ADMIN_USER, minutes=60)
    return TokenOut(access_token=token, expires_in=60 * 60)


@app.get("/api/v1/auth/whoami")
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
    retries: int = Query(4, ge=0, le=10, description="Tentativas de retry por requisição (além do retry da sessão HTTP)."),
    checkpoint_every: int = Query(100, ge=10, le=1000, description="Salva CSV a cada N livros (checkpoint)."),
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


# ==============================================================================
# ============================  ML-READY (BÔNUS)  ===============================
# ==============================================================================

# ---------- Helpers de features ----------

def _prepare_base(df: pd.DataFrame) -> pd.DataFrame:
    """
    Seleciona colunas relevantes e garante tipos.
    """
    need = ["id", "title", "price", "rating", "availability", "category"]
    for col in need:
        if col not in df.columns:
            df[col] = np.nan
    base = df[need].copy()
    base["title"] = base["title"].fillna("")
    base["title_len"] = base["title"].astype(str).str.len().astype(float)
    base["rating"] = pd.to_numeric(base["rating"], errors="coerce")
    base["availability"] = pd.to_numeric(base["availability"], errors="coerce")
    base["price"] = pd.to_numeric(base["price"], errors="coerce")
    base["category"] = base["category"].astype(str).replace({"nan": ""})
    return base.dropna(subset=["rating", "availability"])


def _category_to_index(series: pd.Series) -> Dict[str, int]:
    """
    Mapeia categorias para índices estáveis (ordenados alfabeticamente).
    """
    cats = sorted([c for c in series.dropna().unique().tolist()])
    return {c: i for i, c in enumerate(cats)}


def _minmax(s: pd.Series) -> pd.Series:
    s = s.astype(float)
    mn, mx = float(s.min()), float(s.max())
    if not np.isfinite(mn) or not np.isfinite(mx) or mx <= mn:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - mn) / (mx - mn)


def _build_features(df: pd.DataFrame, normalized: bool = True) -> pd.DataFrame:
    """
    Constrói um DF de features consistente.
    feature_cols (para treino/pred): rating, availability, category_idx, title_len
    Se normalized=True, adiciona rating_norm/availability_norm e usa-as em 'features_norm_*'.
    """
    base = _prepare_base(df)

    cat2idx = _category_to_index(base["category"])
    base["category_idx"] = base["category"].map(cat2idx).fillna(-1).astype(int)

    # normalizações simples (min-max)
    base["rating_norm"] = _minmax(base["rating"])
    base["availability_norm"] = _minmax(base["availability"])

    # conjunto de features "cruas"
    base["f_rating"] = base["rating"].astype(float)
    base["f_availability"] = base["availability"].astype(float)
    base["f_category_idx"] = base["category_idx"].astype(float)
    base["f_title_len"] = base["title_len"].astype(float)

    # conjunto de features "normalizadas"
    base["fn_rating"] = base["rating_norm"].astype(float)
    base["fn_availability"] = base["availability_norm"].astype(float)
    base["fn_category_idx"] = base["f_category_idx"]  # categórica já está em índice
    base["fn_title_len"] = _minmax(base["title_len"])

    # quais usar
    if normalized:
        used = ["fn_rating", "fn_availability", "fn_category_idx", "fn_title_len"]
    else:
        used = ["f_rating", "f_availability", "f_category_idx", "f_title_len"]

    out = base[
        ["id", "title", "category", "price", "rating", "availability", "title_len", "category_idx",
         "rating_norm", "availability_norm"] + used
    ].copy()

    out.rename(
        columns={
            "fn_rating": "x_rating",
            "fn_availability": "x_availability",
            "fn_category_idx": "x_category_idx",
            "fn_title_len": "x_title_len",
            "f_rating": "x_rating",
            "f_availability": "x_availability",
            "f_category_idx": "x_category_idx",
            "f_title_len": "x_title_len",
        },
        inplace=True,
    )
    return out


def _fit_linear_regression(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """
    Ajusta uma regressão linear simples por mínimos quadrados.
    Retorna vetor de coeficientes beta (incluindo intercepto).
    """
    # adiciona intercepto
    ones = np.ones((X.shape[0], 1), dtype=float)
    Xb = np.hstack([ones, X])
    try:
        beta, *_ = np.linalg.lstsq(Xb, y, rcond=None)
        return beta  # shape: (n_features+1,)
    except Exception:
        # fallback: zeros (intercepto = média)
        return np.array([float(np.nanmean(y))] + [0.0] * X.shape[1], dtype=float)


# ---------- Modelos p/ predição ----------

class MLItem(BaseModel):
    rating: float
    availability: float
    category: Optional[str] = None
    title: Optional[str] = None


class MLPredRequest(BaseModel):
    items: List[MLItem]
    normalized: bool = True  # usar o mesmo espaço de features dos endpoints de treino


class MLPrediction(BaseModel):
    predicted_price: float
    features: Dict[str, float]


class MLPredResponse(BaseModel):
    model: Dict[str, Any]
    predictions: List[MLPrediction]


# ---------- Endpoints ML ----------

@app.get("/api/v1/ml/features", tags=["ml"])
def ml_features(
    normalized: bool = Query(True, description="Usa colunas normalizadas (min-max)."),
    limit: int = Query(1000, ge=1, le=10000),
    format: str = Query("json", pattern="^(json|csv)$"),
    include_id: bool = Query(True),
):
    """
    Subconjunto de features limpas/normalizadas para consumo por modelos.
    Retorna colunas: (id opcional), x_rating, x_availability, x_category_idx, x_title_len.
    """
    df = load_df()
    feats = _build_features(df, normalized=normalized)
    used = ["x_rating", "x_availability", "x_category_idx", "x_title_len"]
    cols = (["id"] if include_id else []) + used
    feats = feats[cols].head(limit)

    if format == "csv":
        buf = io.StringIO()
        feats.to_csv(buf, index=False)
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'inline; filename="features.csv"'},
        )
    return feats.to_dict(orient="records")


@app.get("/api/v1/ml/training-data", tags=["ml"])
def ml_training_data(
    normalized: bool = Query(True, description="Usa colunas normalizadas (min-max)."),
    limit: int = Query(1000, ge=1, le=10000),
    format: str = Query("json", pattern="^(json|csv)$"),
):
    """
    Retorna dataset de treino: features + target (price).
    Features: x_rating, x_availability, x_category_idx, x_title_len
    Target: price
    """
    df = load_df()
    feats = _build_features(df, normalized=normalized)
    used = ["x_rating", "x_availability", "x_category_idx", "x_title_len", "price"]
    data = feats[used].dropna(subset=["price"]).head(limit)

    if format == "csv":
        buf = io.StringIO()
        data.to_csv(buf, index=False)
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'inline; filename="training_data.csv"'},
        )
    return data.to_dict(orient="records")


@app.post("/api/v1/ml/predictions", response_model=MLPredResponse, tags=["ml"])
def ml_predictions(payload: MLPredRequest):
    """
    Predição mock:
    - Ajusta uma regressão linear simples (em memória) usando o dataset atual.
    - Se não der para ajustar (poucos dados), usa um fallback heurístico.
    - As features usadas devem estar no mesmo espaço (normalized=True/False) escolhido no payload.
    """
    df = load_df()
    feats = _build_features(df, normalized=payload.normalized).dropna(subset=["price"])
    used = ["x_rating", "x_availability", "x_category_idx", "x_title_len"]

    # Dados para treino
    train = feats[used + ["price"]].dropna()
    if train.shape[0] >= 15:
        X = train[used].to_numpy(dtype=float)
        y = train["price"].to_numpy(dtype=float)
        beta = _fit_linear_regression(X, y)  # [intercept, b1, b2, b3, b4]
        model_info = {"type": "ols", "coefficients": beta.tolist(), "normalized": payload.normalized}
    else:
        # fallback: intercepto = mediana; pesos simples
        median_price = float(np.nanmedian(train["price"])) if train.shape[0] else 40.0
        beta = np.array([median_price, 10.0, 1.0, 0.5, 0.02], dtype=float)
        model_info = {"type": "fallback", "coefficients": beta.tolist(), "normalized": payload.normalized}

    # Mapeamento de categoria -> idx baseado no dataset atual (mesmo do treino)
    cat2idx = _category_to_index(_prepare_base(df)["category"])

    # Monta feature row para cada item de entrada
    preds: List[MLPrediction] = []
    for it in payload.items:
        title_len = float(len(it.title or ""))
        cat_idx = float(cat2idx.get((it.category or ""), -1))

        if payload.normalized:
            # normaliza com base no dataset atual
            r_min, r_max = float(feats["rating"].min()), float(feats["rating"].max())
            a_min, a_max = float(feats["availability"].min()), float(feats["availability"].max())
            tl_min, tl_max = float(feats["title_len"].min()), float(feats["title_len"].max())

            def _mm(x, mn, mx):
                if not np.isfinite(mn) or not np.isfinite(mx) or mx <= mn:
                    return 0.0
                return float((x - mn) / (mx - mn))

            x_row = np.array(
                [
                    _mm(it.rating, r_min, r_max),
                    _mm(it.availability, a_min, a_max),
                    cat_idx,  # categórica como índice
                    _mm(title_len, tl_min, tl_max),
                ],
                dtype=float,
            )
        else:
            x_row = np.array([float(it.rating), float(it.availability), cat_idx, title_len], dtype=float)

        # y = beta0 + beta1*x1 + ... + beta4*x4
        y_hat = float(beta[0] + np.dot(beta[1:], x_row))
        preds.append(
            MLPrediction(
                predicted_price=max(y_hat, 0.0),
                features={
                    "x_rating": float(x_row[0]),
                    "x_availability": float(x_row[1]),
                    "x_category_idx": float(x_row[2]),
                    "x_title_len": float(x_row[3]),
                },
            )
        )

    return MLPredResponse(model=model_info, predictions=preds)
