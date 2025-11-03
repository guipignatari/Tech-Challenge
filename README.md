# Books to Scrape – Data Pipeline & Public API

API e pipeline de dados para coletar livros do site **https://books.toscrape.com** e servir dados via **FastAPI** (deploy em **Vercel**). Pensado para reuso por cientistas de dados e serviços de recomendação.

> Produção: **https://tech-challenge-7ch9zqdhf-guilhermes-projects-ad7e50b0.vercel.app/**
>
> Swagger: adicione `/docs` ao final da URL de produção (ou local) para abrir a documentação interativa.

---

## Sumário
- [Arquitetura (visão macro)](#arquitetura-visão-macro)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Instalação e execução local](#instalação-e-execução-local)
- [Variáveis de ambiente (local e Vercel)](#variáveis-de-ambiente-local-e-vercel)
- [Documentação da API](#documentação-da-api)
  - [Core](#core)
  - [Insights](#insights)
  - [Admin (protegido)](#admin-protegido)
  - [ML‑ready (bônus)](#mlready-bônus)
- [Exemplos de chamadas](#exemplos-de-chamadas)
- [Testes automatizados](#testes-automatizados)
- [Boas práticas e notas](#boas-práticas-e-notas)
- [Licença](#licença)

---

## Arquitetura (visão macro)

```
               ┌──────────────┐
               │  Web target  │  books.toscrape.com
               └──────┬───────┘
                      │  (requests + parsing)
                ┌─────▼───────┐        
                │  Scraper    │        ┌─────────────────────────┐           
                │ (scripts/)  │  --->  │     data/books.csv      │ 
                └─────┬───────┘        └───────────┬─────────────┘
                      │                            │
               ┌──────▼───────┐                    │
               │   FastAPI    │  <── lê/transforma │
               │  (api/v1.py) │                    │
               └──────┬───────┘                    │
                      │                            │
      ┌───────────────▼─────────────────────────────────────────┐
      │               Endpoints públicos e protegidos           │
      │  Core, Insights, Auth(JWT), Admin(trigger), ML-ready    │
      └─────────────────────────────────────────────────────────┘

Deploy: **Vercel** (Serverless). Em produção o filesystem é efêmero – o endpoint
de *trigger* é apenas demonstrativo. Coleta real deve ser feita localmente.
```

### Fluxo resumido
1. **Scraper** (`scripts/scrape_books.py`) coleta e salva **`data/books.csv`**.
2. **API (FastAPI)** lê o CSV, expõe endpoints REST (listagem, busca, estatísticas, ML‑ready).
3. **JWT** protege rotas sensíveis (ex.: `/api/v1/scraping/trigger`, `/auth/*` utilitários).
4. **Vercel** hospeda a API para acesso público (read‑only).

---

## Estrutura do repositório

```
webscraping-tech-challenge/
├─ api/
│  ├─ __init__.py
│  └─ v1.py                 # FastAPI app (endpoints + auth + ML-ready)
├─ scripts/
│  └─ scrape_books.py       # Scraper (requests + parsing) -> data/books.csv
├─ data/
│  └─ books.csv             # Dataset local (gerado/atualizado pelo scraper)
├─ docs/
│  └─ architecture.md       # Desenho/explicação da arquitetura
├─ tests/
│  ├─ test_api.py           # Saúde/listagens/estatísticas
│  ├─ test_auth.py          # Login/refresh/whoami (JWT)
│  ├─ test_categories.py    # Categorias
│  └─ test_ml_endpoints.py  # Endpoints ML-ready
├─ requirements.txt
├─ vercel.json
└─ README.md
```

---

## Instalação e execução local

```bash
# 1) Clonar e criar venv
git clone https://github.com/guipignatari/Tech_Challenge.git
cd Tech_Challenge
python -m venv .venv && source .venv/bin/activate  # (Windows: .venv\Scripts\activate)

# 2) Instalar dependências
pip install -r requirements.txt

# 3) Executar o scraper (gera/atualiza data/books.csv)
python scripts/scrape_books.py --limit 100

# 4) Subir a API
uvicorn api.v1:app --reload --port 8000

# 5) Abrir docs
open http://127.0.0.1:8000/docs
```

> Dica: a rota raiz `/` redireciona para `/docs` automaticamente.

---

## Variáveis de ambiente (local e Vercel)

| Variável             | Default     | Uso                                                                 |
|----------------------|-------------|----------------------------------------------------------------------|
| `SECRET_KEY`         | `dev-secret`| Chave para assinar tokens JWT.                                      |
| `ADMIN_USER`         | `admin`     | Usuário para `/api/v1/auth/login`.                                  |
| `ADMIN_PASSWORD`     | `admin`     | Senha para `/api/v1/auth/login`.                                    |
| `ALLOW_SCRAPER_WRITE`| `false`     | **true** permite escrever `data/books.csv` pelo *trigger* (local).  |

No **Vercel**: defina em *Project → Settings → Environment Variables*.  
Em produção (serverless) o *trigger* é somente **demonstrativo**.

---

## Documentação da API

### Core
| Método | Rota                            | Descrição                                       |
|-------:|---------------------------------|--------------------------------------------------|
| GET    | `/api/v1/health`                | Status e linhas do dataset.                      |
| GET    | `/api/v1/books`                 | Lista livros (filtros/ordenação/limite).         |
| GET    | `/api/v1/books/{id}`            | Detalhe de um livro por ID.                      |
| GET    | `/api/v1/books/search`          | Busca por título e/ou categoria.                 |
| GET    | `/api/v1/categories`            | Lista categorias únicas.                         |

### Insights
| Método | Rota                          | Descrição                                                               |
|-------:|-------------------------------|-------------------------------------------------------------------------|
| GET    | `/api/v1/stats/overview`      | Estatísticas gerais (total, preço médio, distribuição de ratings etc.). |
| GET    | `/api/v1/stats/categories`    | Estatísticas por categoria (qtd, min/med/max de preço, rating médio).   |
| GET    | `/api/v1/books/top-rated`     | **(Opcional)** Livros com melhor avaliação (rating mais alto).          |
| GET    | `/api/v1/books/price-range`   | **(Opcional)** Livros dentro de uma faixa de preço `min..max`.          |

### Auth
| Método | Rota                     | Descrição                                              |
|-------:|--------------------------|--------------------------------------------------------|
| POST   | `/api/v1/auth/login`     | Retorna `access_token` (JWT).                          |
| POST   | `/api/v1/auth/refresh`   | Renova o token.                                        |
| GET    | `/api/v1/auth/whoami`    | Testa token (precisa header `Authorization: Bearer`).  |

> **Swagger – botão “Authorize”**: cole exatamente `Bearer <seu_token>` (com o prefixo).

### Admin (protegido)
| Método | Rota                      | Descrição                                                                 |
|-------:|---------------------------|---------------------------------------------------------------------------|
| POST   | `/api/v1/scraping/trigger`| Executa o scraper. **Local** escreve `data/books.csv`. **Vercel**: demo. |

### ML‑ready (bônus)
| Método | Rota                         | Descrição                                                                                         |
|-------:|------------------------------|---------------------------------------------------------------------------------------------------|
| GET    | `/api/v1/ml/features`        | Subconjunto de features normalizadas (`json`/`csv`).                                              |
| GET    | `/api/v1/ml/training-data`   | Features + target **price** para treino (`json`/`csv`).                                          |
| POST   | `/api/v1/ml/predictions`     | Recebe itens e retorna **predição mock** via regressão linear OLS (em memória).                  |

---

## Exemplos de chamadas

> Utilize diretamente a **URL de produção** abaixo (ou altere `BASE` para `http://127.0.0.1:8000` quando rodar local).

```bash
BASE="https://tech-challenge-7ch9zqdhf-guilhermes-projects-ad7e50b0.vercel.app"
```

### 1) Saúde e listagens
```bash
curl -s "$BASE/api/v1/health" | jq

# Livros (ordenar por preço desc, pegar só o primeiro id)
curl -s "$BASE/api/v1/books?limit=5&order_by=price&order=desc" | jq '.[0]'

# Busca por título + filtro de categoria
curl -s "$BASE/api/v1/books/search?title=world&category=Travel" | jq length

# Categorias
curl -s "$BASE/api/v1/categories" | jq

# Stats geral
curl -s "$BASE/api/v1/stats/overview" | jq
```

### 2) Autenticação (JWT)
```bash
# Credenciais padrão: admin / admin (podem ser alteradas via variáveis de ambiente)
TOKEN=$(curl -s -X POST "$BASE/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | jq -r .access_token)

# Teste do token
curl -s "$BASE/api/v1/auth/whoami" -H "Authorization: Bearer $TOKEN" | jq
```

### 3) Admin (trigger do scraper — local)
```bash
# Produção (Vercel) responde mensagem demonstrativa
# Local (ALLOW_SCRAPER_WRITE=true) escreve data/books.csv
curl -s -X POST "$BASE/api/v1/scraping/trigger?limit=50&verbose=true" \
  -H "Authorization: Bearer $TOKEN" | jq
```

### 4) Insights opcionais
```bash
# Top rated
curl -s "$BASE/api/v1/books/top-rated?limit=5" | jq

# Faixa de preço
curl -s "$BASE/api/v1/books/price-range?min=20&max=30&limit=5" | jq
```

### 5) ML‑ready
```bash
# Features (json)
curl -s "$BASE/api/v1/ml/features?normalized=true&limit=5&format=json" | jq '.[0]'
# Training data (csv)
curl -s "$BASE/api/v1/ml/training-data?normalized=true&limit=10&format=csv" | head

# Predições mock
curl -s -X POST "$BASE/api/v1/ml/predictions" \
  -H "Content-Type: application/json" \
  -d '{
        "normalized": true,
        "items": [
          {"rating": 4, "availability": 12, "category": "Travel",  "title": "A Fun Journey"},
          {"rating": 5, "availability": 3,  "category": "History", "title": "Ancient Worlds"}
        ]
      }' | jq
```

---

## Testes automatizados

```bash
# Rodar todos os testes
pytest -q
```

**O que é coberto (exemplos):**
- `/health` responde com status “ok” e número de linhas.
- `/books` retorna lista com colunas esperadas.
- `/books/{id}` retorna 404 para ID inexistente e 200 para ID válido.
- `/auth/login` devolve token com credenciais padrão/local.
- (Quando aplicável) checks básicos de ML endpoints e insights.

---

## Boas práticas e notas
- **JWT** curto e *Bearer* no header `Authorization`.
- **Cache leve** em `load_df()` com `@lru_cache` para evitar I/O repetido.
- **Tratamento de tipos** no carregamento do CSV (numéricos com `errors="coerce"`).
- **Swagger** sempre disponível em `/docs` (raiz `/` redireciona automaticamente).
- **Serverless**: em Vercel o filesystem é efêmero. Use o *trigger* apenas como **demo**;
  para coletar dados reais, rode o `scripts/scrape_books.py` localmente.
- **ML‑ready**: features normalizadas simples (min‑max) e predição mock via OLS em memória.

---

## 📜 Licença

MIT — livre para uso acadêmico/profissional.  
Dataset: **books.toscrape.com** (uso educacional).

---

## 👤 Autor

LinkedIn: [linkedin.com/in/guilhermepignatari](https://linkedin.com/in/guilhermepignatari)
GitHub: [github.com/guipignatari](https://github.com/guipignatari)
