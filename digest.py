import os
import time
import requests
from datetime import datetime, timedelta

# ── Настройки ──────────────────────────────────────────────────────────────
TAVILY_API_KEY     = os.environ["TAVILY_API_KEY"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
TELEGRAM_TOKEN     = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]

MODELS = [
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-3-27b-it:free",
    "openrouter/free",
]

MAX_SEARCH_RESULTS = 5
SNIPPET_LENGTH = 400

# ── Источники ──────────────────────────────────────────────────────────────
# Российские профильные сайты
RU_DOMAINS = [
    "sostav.ru",
    "adindex.ru",
    "cossa.ru",
]

# Зарубежные профильные сайты
INTL_DOMAINS = [
    "adsoftheworld.com",
    "campaignlive.com",
    "lbbonline.com",
    "contagious.com",
    "thefwa.com",
]

# ── Поисковые запросы ──────────────────────────────────────────────────────
RU_QUERIES = [
    "рекламная кампания бренд",
    "OOH DOOH наружная реклама",
    "спецпроект активация коллаборация",
]

INTL_QUERIES = [
    "brand campaign creative",
    "OOH DOOH advertising",
    "experiential activation pop-up",
    "brand collaboration campaign",
]

# ── Промпт ─────────────────────────────────────────────────────────────────
DIGEST_PROMPT = """Подготовь еженедельный дайджест рекламных кейсов за последние 7 дней для профессиональной насмотренности. Собери ровно 2 блока: Россия и Зарубежные рынки. В зарубежный блок включай США, Европу, Азию и MENA.

Включай только: брендовые имиджевые кампании, OOH и DOOH, digital / social-first спецпроекты, федеральные рекламные кампании, активации, коллаборации, pop-up / experiential проекты.
Исключай: performance-маркетинг, трейд-активации, стандартные промо-коммуникации.

В каждом блоке ровно 5 кейсов, от самых интересных к менее значимым.

Для каждого кейса укажи кратко — не больше 4-5 строк:
— Бренд, страна, тип кейса
— Одно предложение: в чём суть кампании
— Одно предложение: какой инсайт или культурный контекст поймал кейс
— Ссылка на источник

После каждого блока — 2-3 предложения: главные темы и сигналы недели.
В конце — 2-3 ключевых наблюдения по неделе.

Пиши на русском, сохраняй оригинальные названия брендов и кампаний.
Не придумывай факты — если информация не найдена в источнике, пиши «не указано»."""


def search_tavily(query: str, domains: list[str]) -> list[dict]:
    resp = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": TAVILY_API_KEY,
            "query": query,
            "search_depth": "basic",
            "max_results": MAX_SEARCH_RESULTS,
            "include_answer": False,
            "include_domains": domains,
        },
        timeout=30,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", "")[:SNIPPET_LENGTH],
        }
        for r in results
    ]


def collect_search_results() -> tuple[str, str]:
    """Возвращает два отдельных блока: российские и зарубежные материалы."""
    ru_results = []
    intl_results = []
    seen_urls = set()

    # Российские источники
    for query in RU_QUERIES:
        try:
            results = search_tavily(query, RU_DOMAINS)
            for r in results:
                if r["url"] not in seen_urls:
                    seen_urls.add(r["url"])
                    ru_results.append(
                        f"ЗАГОЛОВОК: {r['title']}\nССЫЛКА: {r['url']}\nОТРЫВОК: {r['content']}\n"
                    )
        except Exception as e:
            print(f"Ошибка поиска RU '{query}': {e}")

    # Зарубежные источники
    for query in INTL_QUERIES:
        try:
            results = search_tavily(query, INTL_DOMAINS)
            for r in results:
                if r["url"] not in seen_urls:
                    seen_urls.add(r["url"])
                    intl_results.append(
                        f"ЗАГОЛОВОК: {r['title']}\nССЫЛКА: {r['url']}\nОТРЫВОК: {r['content']}\n"
                    )
        except Exception as e:
            print(f"Ошибка поиска INTL '{query}': {e}")

    return "\n---\n".join(ru_results), "\n---\n".join(intl_results)


def call_openrouter(model: str, prompt: str) -> str | None:
    for attempt in range(3):
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/digest-bot",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4096,
                "temperature": 0.4,
            },
            timeout=300,
        )

        if resp.status_code == 429:
            wait = 60 * (attempt + 1)
            print(f"  429 Rate limit, ждём {wait}с (попытка {attempt+1}/3)...")
            time.sleep(wait)
            continue

        if resp.status_code == 404:
            print(f"  404 Модель не найдена: {model}")
            return None

        if not resp.ok:
            print(f"  Ошибка {resp.status_code}: {resp.text[:200]}")
            return None

        content = resp.json()["choices"][0]["message"]["content"]
        if content:
            return content

    return None


def generate_digest(ru_results: str, intl_results: str) -> str:
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%d.%m.%Y")
    today = datetime.now().strftime("%d.%m.%Y")

    full_prompt = f"""{DIGEST_PROMPT}

Период дайджеста: {week_ago} — {today}

=== РОССИЙСКИЕ ИСТОЧНИКИ (sostav.ru, adindex.ru, cossa.ru) ===
{ru_results}

=== ЗАРУБЕЖНЫЕ ИСТОЧНИКИ (adsoftheworld.com, campaignlive.com, lbbonline.com, contagious.com) ===
{intl_results}"""

    for model in MODELS:
        print(f"Пробуем модель: {model}")
        result = call_openrouter(model, full_prompt)
        if result:
            print(f"Успешно через {model}")
            return result
        print(f"Модель {model} не сработала, пробуем следующую...")

    raise RuntimeError("Все модели недоступны. Проверь ключ OPENROUTER_API_KEY.")


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
    print("Собираем материалы с профильных сайтов...")
    ru_results, intl_results = collect_search_results()
    print(f"Российские источники: {ru_results.count('ЗАГОЛОВОК:')} материалов")
    print(f"Зарубежные источники: {intl_results.count('ЗАГОЛОВОК:')} материалов")

    print("Генерируем дайджест...")
    digest = generate_digest(ru_results, intl_results)
    print(f"Дайджест сгенерирован ({len(digest)} символов)")

    print("Отправляем в Telegram...")
    send_to_telegram(digest)
    print("Готово!")


if __name__ == "__main__":
    main()
