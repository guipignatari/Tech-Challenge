import csv
import re
import time
import os
import argparse
import logging
from typing import Dict, List, Tuple, Optional
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

BASE_URL = "https://books.toscrape.com/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Scraper academic/educational use; contact: example@example.com)"
}

def build_session(retries: int = 5, backoff: float = 0.6) -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=backoff,  # 0.6, 1.2, 1.8, ...
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update(HEADERS)
    return s

RATING_MAP = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}

def get_soup(url: str, session: requests.Session, retries: int = 2, verbose: bool = False, backoff: float = 0.5) -> BeautifulSoup:
    for attempt in range(retries + 1):
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
            return BeautifulSoup(r.content, "html.parser")
        except Exception as e:
            if attempt < retries:
                if verbose:
                    logging.warning(f"[WARN] GET fail ({attempt+1}/{retries}) {url}: {e}. Retrying...")
                time.sleep(backoff * (attempt + 1))
            else:
                raise

def parse_book_detail(url: str, session: requests.Session, retries: int = 2, verbose: bool = False) -> Dict:
    soup = get_soup(url, session=session, retries=retries, verbose=verbose)
    title = soup.select_one(".product_main h1").get_text(strip=True)

    price_text = soup.select_one(".product_main .price_color").get_text(strip=True)
    price_text = price_text.replace(",", ".")
    m_price = re.search(r"(\d+(?:\.\d+)?)", price_text)
    price = float(m_price.group(1)) if m_price else 0.0

    rating_class = soup.select_one(".product_main p.star-rating")["class"]
    rating_word = next((c for c in rating_class if c in RATING_MAP), "One")
    rating = RATING_MAP.get(rating_word, 1)

    avail_text = soup.select_one(".product_main .availability").get_text(" ", strip=True)
    m = re.search(r"(\d+)", avail_text)
    availability = int(m.group(1)) if m else 0

    breadcrumb = soup.select("ul.breadcrumb li")
    category = breadcrumb[-2].get_text(strip=True) if len(breadcrumb) >= 2 else "Unknown"

    img_src = soup.select_one("#product_gallery img")["src"]
    image_url = urljoin(url, img_src)

    return {
        "title": title,
        "price": price,
        "rating": rating,
        "availability": availability,
        "category": category,
        "image_url": image_url,
        "product_page_url": url,
    }

def iterate_category_pages(category_url: str, session: requests.Session, retries: int = 2, verbose: bool = False) -> List[str]:
    """Retorna todas as URLs de página daquela categoria (paginadas)."""
    pages = []
    next_url = category_url
    while next_url:
        pages.append(next_url)
        soup = get_soup(next_url, session=session, retries=retries, verbose=verbose)
        next_link = soup.select_one("li.next a")
        if next_link:
            next_url = urljoin(next_url, next_link.get("href"))
        else:
            next_url = None
    return pages

def get_all_categories(session: requests.Session, retries: int = 2, verbose: bool = False) -> List[Tuple[str, str]]:
    """Retorna lista de (nome, url) de cada categoria."""
    soup = get_soup(BASE_URL, session=session, retries=retries, verbose=verbose)
    cats: List[Tuple[str, str]] = []
    for a in soup.select(".side_categories ul li ul li a"):
        name = a.get_text(strip=True)
        href = a.get("href")
        cats.append((name, urljoin(BASE_URL, href)))
    return cats

def setup_logging(log_file: Optional[str], verbose: bool) -> None:
    level = logging.INFO if verbose else logging.WARNING
    handlers = [logging.StreamHandler()]
    if log_file:
        os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
        force=True,  # garante que reconfigure mesmo se já tiver logging ativo
    )

def run(
    output_csv: str = "data/books.csv",
    polite_delay: float = 0.25,
    verbose: bool = False,
    retries: int = 4,
    limit: int | None = None,
    checkpoint_every: int = 100,
    resume: bool = True,
    log_file: Optional[str] = None,
):
    setup_logging(log_file, verbose)

    os.makedirs(os.path.dirname(output_csv) or ".", exist_ok=True)
    start = time.time()
    rows: List[Dict] = []
    success = 0
    fail = 0
    book_id = 1
    seen = set()

    fieldnames = [
        "id", "title", "price", "rating", "availability",
        "category", "image_url", "product_page_url"
    ]

    # RESUME: carrega progresso existente, se houver
    if resume and os.path.exists(output_csv):
        try:
            with open(output_csv, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    rows.append(row)
                    seen.add(row.get("product_page_url", ""))
                    try:
                        book_id = max(book_id, int(row.get("id", 0)) + 1)
                    except Exception:
                        pass
            logging.info(f"[INFO] Resume: carregados {len(rows)} registros existentes de {output_csv}")
        except Exception as e:
            logging.warning(f"[WARN] Não foi possível retomar de {output_csv}: {e}")

    session = build_session(retries=max(3, retries + 2), backoff=0.8)

    categories = get_all_categories(session=session, retries=retries, verbose=verbose)
    logging.info(f"[INFO] Encontradas {len(categories)} categorias")

    for cidx, (cat_name, cat_url) in enumerate(categories, start=1):
        logging.info(f"[INFO] Categoria {cidx}/{len(categories)} — {cat_name} → {cat_url}")
        cat_t0 = time.time()
        cat_success0 = success
        try:
            for page in iterate_category_pages(cat_url, session=session, retries=retries, verbose=verbose):
                logging.info(f"  [PAGE] {page}")
                soup = get_soup(page, session=session, retries=retries, verbose=verbose)
                for a in soup.select("article.product_pod h3 a"):
                    product_rel = a.get("href")
                    product_url = urljoin(page, product_rel)
                    if product_url in seen:
                        continue
                    try:
                        book = parse_book_detail(product_url, session=session, retries=retries, verbose=verbose)
                        book["id"] = book_id
                        rows.append(book)
                        seen.add(product_url)
                        success += 1
                        if success % 20 == 0:
                            logging.info(f"    [OK] {success} livros coletados...")
                        book_id += 1

                        # CHECKPOINT periódico
                        if checkpoint_every and success % checkpoint_every == 0:
                            with open(output_csv, "w", newline="", encoding="utf-8") as f:
                                w = csv.DictWriter(f, fieldnames=fieldnames)
                                w.writeheader()
                                w.writerows(rows)
                            logging.info(f"    [CKPT] salvo {len(rows)} linhas em {output_csv}")

                        if limit is not None and success >= limit:
                            raise StopIteration
                    except Exception as e:
                        fail += 1
                        logging.warning(f"[WARN] Falha ao parsear {product_url}: {e}")
                    time.sleep(polite_delay)
        except StopIteration:
            pass  # só sai do loop externo depois do summary da categoria
        except Exception as e:
            # se uma categoria cair (ex.: Connection refused), pula e segue
            logging.warning(f"[WARN] Categoria falhou e será pulada: {cat_url} → {e}")
            time.sleep(5)
        finally:
            cat_delta = time.time() - cat_t0
            cat_new = success - cat_success0
            logging.info(f"[CAT] {cat_name}: +{cat_new} items em {round(cat_delta,2)}s")

        # se estourou o limit, sai de vez
        if limit is not None and success >= limit:
            break

    # Salva final
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    elapsed = round(time.time() - start, 2)
    logging.info(f"OK! Salvo {len(rows)} livros em {output_csv} (sucesso={success}, falhas={fail}, tempo={elapsed}s)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape Books to Scrape → data/books.csv")
    parser.add_argument("--output", default="data/books.csv", help="Caminho do CSV de saída")
    parser.add_argument("--delay", type=float, default=0.25, help="Delay entre requisições (segundos)")
    parser.add_argument("--retries", type=int, default=4, help="Tentativas de retry por requisição")
    parser.add_argument("--verbose", action="store_true", help="Exibe logs detalhados")
    parser.add_argument("--limit", type=int, default=None, help="Limita quantidade de livros coletados")
    parser.add_argument("--checkpoint-every", type=int, default=100, help="Salva CSV a cada N registros")
    parser.add_argument("--resume", action="store_true", help="Retoma do CSV existente (se houver)")
    parser.add_argument("--log-file", default=None, help="Arquivo de log (ex.: logs/scrape.log)")
    args = parser.parse_args()

    run(
        output_csv=args.output,
        polite_delay=args.delay,
        verbose=args.verbose,
        retries=args.retries,
        limit=args.limit,
        checkpoint_every=args.checkpoint_every,
        resume=args.resume,
        log_file=args.log_file,
    )
