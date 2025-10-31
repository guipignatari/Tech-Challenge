# Arquitetura & Pipeline

```mermaid
flowchart LR
  A[Books.toscrape.com] -->|requests+BS4| B[Scraper (scripts/scrape_books.py)]
  B -->|CSV| C[(data/books.csv)]
  C -->|pandas| D[FastAPI (api/v1.py)]
  D -->|Vercel Serverless| E[API Pública]
  E --> F[Clientes: Cientistas/ML/Apps]