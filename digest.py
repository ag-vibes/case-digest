import os
import time
import requests
from datetime import datetime, timedelta

# ── Настройки ──────────────────────────────────────────────────────────────
TAVILY_API_KEY    = os.environ["TAVILY_API_KEY"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
TELEGRAM_TOKEN    = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID  = os.environ["TELEGRAM_CHAT_ID"]

# Бесплатные модели на OpenRouter (можно менять):
# - deepseek/deepseek-chat-v3-0324:free     — отлично пишет на русском
# - meta-llama/llama-3.3-70b-instruct:free  — мощная альтернатива
# - google/gemini-2.0-flash-exp:free        — Gemini через OpenRouter
MODEL = "deepseek/deepseek-chat-v3-0324:free"

MAX_SEARCH_RESULTS = 5
SNIPPET_LENGTH = 300

# ── Промпт ─────────────────────────────────────────────────────────────────
DIGEST_PROMPT = """Подготавливай свежий еженедельный дайджест рекламных кейсов за последние 7 дней для профессиональной насмотренности. Собирай 3 блока: Россия, СНГ и зарубежные рынки. В зарубежный блок включай США, Европу, Азию и MENA. Включай только брендовые имиджевые кампании, OOH и DOOH, digital / social-first спецпроекты, федеральные рекламные кампании, активации, коллаборации, pop-up / experiential проекты. Исключай performance-маркетинг, трейд-активации и стандартные тактические промо-коммуникации. Для каждого кейса указывай: бренд, страна, название кампании, тип кейса, краткую идею, формат / механику, каналы, агентство / продакшн, какой инсайт, культурный код или общественный контекст кейс поймал, ссылку на источник. Пиши на русском, сохраняя оригинальные названия брендов, кампаний, агентств и проектов. Оформляй ответ как структурированный дайджест со ссылками: минимум 10 кейсов по России, минимум 5 по СНГ и минимум 10 по зарубежным рынкам, внутри блоков располагай кейсы от самых интересных к менее значимым. После каждого блока добавляй короткий вывод о заметных темах, визуальных кодах, механиках и культурных сигналах. В конце дай 3-5 ключевых наблюдений по неделе и укажи, какие идеи и форматы стоит отдельно отслеживать дальше. Не придумывай факты, агентства или детали; если информация не найдена, пиши, что она не указана в источнике."""

SEARCH_QUERIES = [
    "рекламные кампании бренды Россия 2025 неделя",
    "OOH DOOH наружная реклама Россия 2025",
    "рекламные кейсы СНГ Казахстан Беларусь 2025",
    "brand campaign experiential activation 2025",
    "OOH DOOH advertising campaign 2025",
    "digital social campaign brand 2025",
    "pop-up experiential brand activation Europe USA 2025",
    "brand collaboration campaign MENA Asia 2025",
]


def search_tavily(query: str) -> list[dict]:
    resp = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": TAVILY_API_KEY,
            "query": query,
            "search_depth": "basic",
            "max_results": MAX_SEARCH_RESULTS,
            "include_answer": False,
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


def collect_search_results() -> str:
    all_results = []
    seen_urls = set()

    for query in SEARCH_QUERIES:
        try:
            results = search_tavily(query)
            for r in results:
                if r["url"] not in seen_urls:
                    seen_urls.add(r["url"])
                    all_results.append(
                        f"ЗАГОЛОВОК: {r['title']}\nССЫЛКА: {r['url']}\nОТРЫВОК: {r['content']}\n"
                    )
        except Exception as e:
            print(f"Ошибка поиска '{query}': {e}")

    return "\n---\n".join(all_results)


def generate_digest(search_results: str) -> str:
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%d.%m.%Y")
    today = datetime.now().strftime("%d.%m.%Y")

    full_prompt = f"""{DIGEST_PROMPT}

Период дайджеста: {week_ago} — {today}

Ниже — результаты поиска. Используй только реальные кейсы из этих источников:

{search_results}"""

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
                "max_tokens": 8192,
                "temperature": 0.4,
            },
            timeout=180,
        )

        if resp.status_code == 429:
            wait = 60 * (attempt + 1)
            print(f"429 Too Many Requests, ждём {wait}с (попытка {attempt+1}/3)...")
            time.sleep(wait)
            continue

        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    raise RuntimeError("OpenRouter вернул 429 три раза подряд.")


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
            # Если Markdown сломался — отправляем plain text
            payload["parse_mode"] = None
            resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        print(f"Часть {i+1}/{len(parts)} отправлена.")


def main():
    print(f"Модель: {MODEL}")

    print("Собираем результаты поиска...")
    search_results = collect_search_results()
    print(f"Найдено материалов: {search_results.count('ЗАГОЛОВОК:')}")

    print("Генерируем дайджест...")
    digest = generate_digest(search_results)
    print(f"Дайджест сгенерирован ({len(digest)} символов)")

    print("Отправляем в Telegram...")
    send_to_telegram(digest)
    print("Готово!")


if __name__ == "__main__":
    main()
