# Webscraping Tech Challenge — Books to Scrape API

API pública construída com **FastAPI** para servir os dados coletados via **web scraping** do site [books.toscrape.com](https://books.toscrape.com/).  
O projeto entrega um **pipeline ponta‑a‑ponta**: *extração → armazenamento (CSV) → publicação via API → consumo por aplicações/ML*.

> 🔗 **Produção (Vercel)**: https://tech-challenge-7ch9zqdhf-guilhermes-projects-ad7e50b0.vercel.app/  
> 📖 **Swagger em produção**: https://tech-challenge-7ch9zqdhf-guilhermes-projects-ad7e50b0.vercel.app/docs  
> 🧾 **OpenAPI (JSON)**: https://tech-challenge-7ch9zqdhf-guilhermes-projects-ad7e50b0.vercel.app/openapi.json

---

## 📌 Sumário

- [Arquitetura](/api/v1/stats/categories)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Pré‑requisitos](#pré-requisitos)
- [Instalação e execução local](#instalação-e-execução-local)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [Scraper (CLI)](#scraper-cli)
- [Documentação da API (Swagger)](#documentação-da-api-swagger)
- [Endpoints](#endpoints)
  - [Core](#core)
  - [Insights](#insights)
  - [Autenticação (Desafio 1)](#autenticação-desafio-1)
  - [Admin / Scraping](#admin--scraping)
  - [ML‑ready (Bônus/Desafio 2)](#ml-ready-bônusdesafio-2)
- [Exemplos de chamadas](#exemplos-de-chamadas)
- [Testes](#testes)
- [Deploy na Vercel](#deploy-na-vercel)
- [Limitações e próximos passos](#limitações-e-próximos-passos)
- [Licença](#licença)

---

## 🧱 Arquitetura

1. **Ingestão (web scraping)**  
   `scripts/scrape_books.py` percorre categorias/páginas, extrai **título, preço, rating, disponibilidade, categoria, URL da imagem e da página do produto** e grava em `data/books.csv`.  
   Possui *retry* com backoff, checkpoints e opção de *resume*.

2. **Camada de dados (CSV local)**  
   O arquivo `data/books.csv` é a *fonte de dados* da API local. Em produção (Vercel) o filesystem é efêmero, por isso o trigger de *scraping* é **demonstrativo**.

3. **API Pública (FastAPI)**  
   `api/v1.py` expõe endpoints REST para leitura, busca, estatísticas e (bônus) endpoints **ML‑ready**.  
   Há **autenticação JWT** para rotas sensíveis (admin/trigger).

4. **Deploy**  
   Publicação na **Vercel**, com documentação automática via **Swagger** (`/docs`) e **OpenAPI** (`/openapi.json`).

> Para um diagrama, veja `docs/architecture.md` (quando aplicável).

---

## 🗂️ Estrutura do repositório

```
webscraping-tech-challenge/
├─ api/
│  ├─ __init__.py
│  └─ v1.py                 # FastAPI app (endpoints + auth + ML-ready)
├─ scripts/
│  └─ scrape_books.py       # Web scraper (CLI)
├─ data/
│  └─ books.csv             # Dataset (gerado/atualizado pelo scraper)
├─ docs/
│  └─ architecture.md       # Desenho/explicação da arquitetura (opcional)
├─ tests/
│  ├─ test_api.py           # Saúde/listagens/estatísticas
│  ├─ test_auth.py          # Login/refresh/whoami (JWT)
│  ├─ test_categories.py    # Categorias
│  └─ test_ml_endpoints.py  # Endpoints ML-ready (bônus)
├─ requirements.txt
├─ vercel.json
└─ README.md
```

---

## 🧰 Pré-requisitos

- **Python 3.11+** (recomendado 3.12)  
- `pip` / `venv`  
- (dev) **curl** e **jq** para exemplos via terminal

---

## ▶️ Instalação e execução local

```bash
# 1) Clone
git clone https://github.com/<seu-usuario>/webscraping-tech-challenge.git
cd webscraping-tech-challenge

# 2) Ambiente virtual
python -m venv .venv
source .venv/bin/activate  # (Windows) .venv\\Scripts\\activate

# 3) Dependências
pip install -r requirements.txt

# 4) Executar API local (porta 8000)
uvicorn api.v1:app --reload --port 8000
# Abra http://127.0.0.1:8000/docs
```

---

## 🔐 Variáveis de ambiente

| Variável               | Default       | Uso                                                                                  |
|------------------------|---------------|--------------------------------------------------------------------------------------|
| `SECRET_KEY`           | `dev-secret`  | Chave para assinar tokens JWT                                                        |
| `ADMIN_USER`           | `admin`       | Usuário do endpoint `/auth/login`                                                    |
| `ADMIN_PASSWORD`       | `admin`       | Senha do endpoint `/auth/login`                                                      |
| `ALLOW_SCRAPER_WRITE`  | `false`       | **true** habilita `/scraping/trigger` a gravar `data/books.csv` (modo local)        |

> Em produção (Vercel), defina em **Project → Settings → Environment Variables**.  
> Recomenda-se alterar o par usuário/senha e o `SECRET_KEY` para valores próprios.

---

## 🕷️ Scraper (CLI)

```bash
python scripts/scrape_books.py \
  --output data/books.csv \
  --delay 0.10 \
  --retries 2 \
  --verbose \
  --limit 1000 \
  --checkpoint-every 100 \
  --resume
```

**Parâmetros**  
- `--output`: caminho do CSV (default `data/books.csv`)  
- `--delay`: atraso entre requisições (segundos)  
- `--retries`: tentativas extras por request  
- `--verbose`: logs detalhados  
- `--limit`: limite de livros (None = tudo)  
- `--checkpoint-every`: salva CSV a cada N livros  
- `--resume`: retoma do CSV existente

---

## 📚 Documentação da API (Swagger)

- **Local**: `http://127.0.0.1:8000/docs`  
- **Produção**: https://tech-challenge-7ch9zqdhf-guilhermes-projects-ad7e50b0.vercel.app/docs

> Dica: após logar em `/api/v1/auth/login`, copie o `access_token` e clique no **cadeado “Authorize”** do Swagger para testar rotas protegidas com `Bearer <token>`.

---

## 🚏 Endpoints

### Core

| Método | Rota                                 | Descrição                                                                               |
|-------:|--------------------------------------|-----------------------------------------------------------------------------------------|
| GET    | `/api/v1/health`                     | Status da API e total de linhas                                                         |
| GET    | `/api/v1/books`                      | Lista livros (filtros: `category`, ordenação, `limit`)                                  |
| GET    | `/api/v1/books/{id}`                 | Detalhes de um livro por `id`                                                           |
| GET    | `/api/v1/books/search`               | Busca por `title` (substring) e/ou `category`                                           |
| GET    | `/api/v1/categories`                 | Lista de categorias únicas                                                              |

### Insights

| Método | Rota                                 | Descrição                                                                               |
|-------:|--------------------------------------|-----------------------------------------------------------------------------------------|
| GET    | `/api/v1/stats/overview`             | Estatísticas gerais (total, preço médio, dist. ratings, soma de disponibilidade)        |
| GET    | `/api/v1/stats/categories`           | Estatísticas por categoria (qtd, min/med/max de preço, rating médio)                    |

### Autenticação (Desafio 1)

| Método | Rota                         | Descrição                                    |
|-------:|------------------------------|----------------------------------------------|
| POST   | `/api/v1/auth/login`         | Retorna `access_token` (JWT)                  |
| POST   | `/api/v1/auth/refresh`       | Renova o token                                |
| GET    | `/api/v1/auth/whoami`        | Retorna o usuário do token (`admin`)          |

- **Header**: `Authorization: Bearer <token>`  
- **Expiração padrão**: 60 minutos

### Admin / Scraping

| Método | Rota                         | Protegido | Descrição                                                                 |
|-------:|------------------------------|:--------:|---------------------------------------------------------------------------|
| POST   | `/api/v1/scraping/trigger`  | ✅       | Dispara o scraper local e atualiza `data/books.csv` (se permitido)        |

> Em produção (Vercel) o FS é efêmero — o endpoint retorna **apenas uma mensagem**; utilize storage externo para persistência real.

### ML‑ready (Bônus/Desafio 2)

| Método | Rota                           | Descrição                                                                                 |
|-------:|--------------------------------|-------------------------------------------------------------------------------------------|
| GET    | `/api/v1/ml/features`          | Retorna features normalizadas/limpas (`x_rating`, `x_availability`, `x_category_idx`, `x_title_len`) |
| GET    | `/api/v1/ml/training-data`     | Retorna **features + target** (`price`) em **JSON** ou **CSV**                            |
| POST   | `/api/v1/ml/predictions`       | Recebe itens e retorna **predição mock** (regra simples) e as features usadas            |

**Parâmetros comuns**  
- `normalized` (bool) — calcula features normalizadas (default `true`)  
- `limit` (int) — limita quantidade de linhas (default 100)  
- `format` (`json`|`csv`) — em `/training-data` para escolher o formato

---

## 🧪 Exemplos de chamadas

> Utilize diretamente a URL de produção abaixo.

```bash
BASE="https://tech-challenge-7ch9zqdhf-guilhermes-projects-ad7e50b0.vercel.app"

# 1) Saúde e listagens
curl -s "$BASE/api/v1/health" | jq
curl -s "$BASE/api/v1/books?limit=5&order_by=price&order=desc" | jq '.[0]'
curl -s "$BASE/api/v1/books/search?title=world&category=Travel" | jq length
curl -s "$BASE/api/v1/categories" | jq
curl -s "$BASE/api/v1/stats/overview" | jq

# 2) Autenticação (JWT)
TOKEN=$(curl -s -X POST "$BASE/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"ChangeMe!2025"}' | jq -r .access_token)

curl -s "$BASE/api/v1/auth/whoami" -H "Authorization: Bearer $TOKEN" | jq

# 3) Admin (trigger do scraper – local)
curl -s -X POST "$BASE/api/v1/scraping/trigger?limit=50&verbose=true" \
  -H "Authorization: Bearer $TOKEN" | jq

# 4) ML-ready
curl -s "$BASE/api/v1/ml/features?normalized=true&limit=5&format=json" | jq '.[0]'
curl -s "$BASE/api/v1/ml/training-data?normalized=true&limit=10&format=csv" | head
curl -s -X POST "$BASE/api/v1/ml/predictions" \
  -H 'Content-Type: application/json' \
  -d '{
        "normalized": true,
        "items": [
          {"rating": 4, "availability": 12, "category": "Travel", "title": "A Fun Journey"},
          {"rating": 5, "availability": 3,  "category": "History","title": "Ancient Worlds"}
        ]
      }' | jq
```

---

## ✅ Testes

### Como rodar

```bash
pytest -q
```

### O que cada arquivo cobre

- **`tests/test_api.py`**  
  - `GET /api/v1/health` retorna status OK e contagem  
  - `GET /api/v1/books` e `GET /api/v1/books/{id}` funcionam  
  - `GET /api/v1/stats/overview` contém as chaves esperadas

- **`tests/test_auth.py`**  
  - `POST /api/v1/auth/login` retorna `access_token` válido  
  - `GET /api/v1/auth/whoami` com Bearer token retorna `{"user":"admin"}`  
  - `POST /api/v1/auth/refresh` gera novo token

- **`tests/test_categories.py`**  
  - `GET /api/v1/categories` retorna lista consistente

- **`tests/test_ml_endpoints.py`**  
  - `GET /api/v1/ml/features` retorna as features mínimas  
  - `GET /api/v1/ml/training-data?format=csv` retorna CSV com cabeçalho correto  
  - `POST /api/v1/ml/predictions` retorna `predicted_price` e ecoa `features`

> **Dica**: em ambientes CI, é possível mockar a leitura do CSV para testes determinísticos.

---

## 🚀 Deploy na Vercel

1. **Importe o repositório** (GitHub → Vercel).  
2. **Framework Preset**: *FastAPI* (ou “Other”).  
3. **Root Directory**: `./`.  
4. **Environment Variables**: `SECRET_KEY`, `ADMIN_USER`, `ADMIN_PASSWORD`, `ALLOW_SCRAPER_WRITE=false`.  
5. **Deploy** e valide em `/docs`.

`vercel.json` (apenas se você usar um *adapter* custom `api/index.py`; caso a sua implantação atual já funcione, mantenha como está):

```json
{
  "functions": { "api/index.py": { "runtime": "python3.11" } },
  "routes": [{ "src": "/(.*)", "dest": "/api/index.py" }]
}
```

---

## 📜 Licença

MIT — livre para uso acadêmico/profissional.  
Dataset: **books.toscrape.com** (uso educacional).

---

## 👤 Autor

LinkedIn: [linkedin.com/in/guilhermepignatari](https://linkedin.com/in/guilhermepignatari)
GitHub: [github.com/guipignatari](https://github.com/guipignatari)
