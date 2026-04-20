import os
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Настройки ──────────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
TELEGRAM_TOKEN     = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]

MODEL = "anthropic/claude-haiku-4-5"

# ── RSS-источники ──────────────────────────────────────────────────────────
RSS_FEEDS = {
    "ru": [
        ("Sostav.ru",  "https://www.sostav.ru/rss/news.xml"),
        ("Adindex.ru", "https://adindex.ru/rss/news.xml"),
        ("Cossa.ru",   "https://www.cossa.ru/rss/"),
    ],
    "intl": [
        ("Ads of the World",  "https://www.adsoftheworld.com/feed"),
        ("Campaign Live",     "https://www.campaignlive.com/rss"),
        ("LBBonline",         "https://lbbonline.com/feed"),
    ],
}

HEADERS = {"User-Agent": "Mozilla/5.0 (digest-bot/1.0)"}

# ── Промпт ─────────────────────────────────────────────────────────────────
DIGEST_PROMPT = """Подготовь еженедельный дайджест рекламных кейсов для профессиональной насмотренности. Собери ровно 2 блока: Россия и Зарубежные рынки.

Включай только: брендовые имиджевые кампании, OOH и DOOH, digital / social-first спецпроекты, активации, коллаборации, pop-up / experiential проекты.
Исключай: performance-маркетинг, трейд-активации, стандартные промо.

В каждом блоке ровно 5 кейсов, от самых интересных к менее значимым.

Для каждого кейса — не больше 4 строк:
— **Бренд** · страна · тип кейса
— Суть кампании одним предложением
— Инсайт: какой культурный контекст поймал кейс
— Источник: [название](ссылка)

После каждого блока — 2 предложения о главных темах и сигналах недели.
В конце — 2-3 ключевых наблюдения по неделе.

Пиши на русском, сохраняй оригинальные названия брендов и кампаний.
Не придумывай факты — используй только то, что есть в материалах."""


def fetch_rss(name: str, url: str, days: int = 7) -> list[dict]:
    """Забирает статьи из RSS за последние N дней."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    articles = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        # Поддержка Atom и RSS
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)

        for item in items:
            # Заголовок
            title_el = item.find("title")
            title = title_el.text.strip() if title_el is not None and title_el.text else ""

            # Ссылка
            link_el = item.find("link")
            if link_el is not None:
                link = link_el.text.strip() if link_el.text else link_el.get("href", "")
            else:
                link = ""

            # Дата
            date_el = item.find("pubDate") or item.find("atom:published", ns) or item.find("dc:date")
            pub_date = None
            if date_el is not None and date_el.text:
                try:
                    pub_date = parsedate_to_datetime(date_el.text.strip())
                except Exception:
                    try:
                        pub_date = datetime.fromisoformat(date_el.text.strip().replace("Z", "+00:00"))
                    except Exception:
                        pass

            # Фильтр по дате
            if pub_date and pub_date < cutoff:
                continue

            # Описание
            desc_el = item.find("description") or item.find("atom:summary", ns)
            description = ""
            if desc_el is not None and desc_el.text:
                # Убираем HTML-теги простым способом
                import re
                description = re.sub(r"<[^>]+>", "", desc_el.text).strip()[:500]

            if title and link:
                articles.append({
                    "source": name,
                    "title": title,
                    "link": link,
                    "description": description,
                    "date": pub_date.strftime("%d.%m.%Y") if pub_date else "дата неизвестна",
                })

    except Exception as e:
        print(f"Ошибка RSS {name}: {e}")

    return articles


def collect_articles() -> tuple[list[dict], list[dict]]:
    """Параллельно забирает статьи из всех RSS-источников."""
    ru_articles = []
    intl_articles = []

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {}

        for lang, feeds in RSS_FEEDS.items():
            for name, url in feeds:
                future = executor.submit(fetch_rss, name, url)
                futures[future] = lang

        for future in as_completed(futures):
            lang = futures[future]
            articles = future.result()
            if lang == "ru":
                ru_articles.extend(articles)
            else:
                intl_articles.extend(articles)

    # Сортируем по дате (свежие первые)
    ru_articles.sort(key=lambda x: x["date"], reverse=True)
    intl_articles.sort(key=lambda x: x["date"], reverse=True)

    return ru_articles, intl_articles


def format_articles(articles: list[dict]) -> str:
    """Форматирует статьи для передачи в промпт."""
    lines = []
    for a in articles:
        lines.append(
            f"[{a['date']}] {a['source']}\n"
            f"Заголовок: {a['title']}\n"
            f"Ссылка: {a['link']}\n"
            f"Описание: {a['description']}\n"
        )
    return "\n---\n".join(lines)


def generate_digest(ru_articles: list[dict], intl_articles: list[dict]) -> str:
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%d.%m.%Y")
    today = datetime.now().strftime("%d.%m.%Y")

    ru_text = format_articles(ru_articles) if ru_articles else "Материалов не найдено."
    intl_text = format_articles(intl_articles) if intl_articles else "Материалов не найдено."

    full_prompt = f"""{DIGEST_PROMPT}

Период: {week_ago} — {today}

=== РОССИЙСКИЕ ИСТОЧНИКИ ===
{ru_text}

=== ЗАРУБЕЖНЫЕ ИСТОЧНИКИ ===
{intl_text}"""

    for attempt in range(3):
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/digest-bot",
            },
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": full_prompt}],
                "max_tokens": 4096,
                "temperature": 0.4,
            },
            timeout=120,
        )

        if resp.status_code == 429:
            wait = 30 * (attempt + 1)
            print(f"429 Rate limit, ждём {wait}с...")
            time.sleep(wait)
            continue

        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    raise RuntimeError("Не удалось получить ответ от модели.")


def split_message(text: str, limit: int = 4096) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts = []
    while text:
        if len(text) <= limit:
            parts.append(text)
            break
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        parts.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return parts


def send_to_telegram(text: str):
    parts = split_message(text)
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    for i, part in enumerate(parts):
        prefix = "📢 *Еженедельный дайджест рекламных кейсов*\n\n" if i == 0 else ""
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": prefix + part,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        resp = requests.post(url, json=payload, timeout=30)
        if not resp.ok:
            payload["parse_mode"] = None
            resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        print(f"Часть {i+1}/{len(parts)} отправлена.")


def main():
    print("Парсим RSS-ленты...")
    ru_articles, intl_articles = collect_articles()
    print(f"Российские источники: {len(ru_articles)} статей")
    print(f"Зарубежные источники: {len(intl_articles)} статей")

    if not ru_articles and not intl_articles:
        print("Нет материалов — дайджест не отправляем.")
        return

    print(f"Генерируем дайджест через {MODEL}...")
    digest = generate_digest(ru_articles, intl_articles)
    print(f"Готово ({len(digest)} символов)")

    print("Отправляем в Telegram...")
    send_to_telegram(digest)
    print("Дайджест отправлен!")


if __name__ == "__main__":
    main()
