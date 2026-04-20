# 📰 Еженедельный дайджест рекламных кейсов

Бот автоматически собирает дайджест рекламных кейсов каждый понедельник в 10:16 МСК и публикует в Telegram-канал.

**Стек:** Tavily (поиск) → Gemini 2.0 Flash (анализ) → Telegram Bot API

---

## Структура репозитория

```
├── digest.py
└── .github/
    └── workflows/
        └── digest.yml
```

---

## Настройка (один раз)

### 1. Создай Telegram-бота

1. Напиши @BotFather в Telegram
2. Отправь `/newbot`, придумай имя
3. Скопируй **токен** вида `7123456789:AAF...`
4. Добавь бота в свой канал как **администратора** с правом публикации
5. Узнай `CHAT_ID` канала:
   - Для публичного канала: `@username_канала`
   - Для приватного: перейди на `https://api.telegram.org/bot<TOKEN>/getUpdates` после пересылки любого сообщения из канала — найди `"chat":{"id":...}`

### 2. Добавь секреты в GitHub

Репозиторий → **Settings → Secrets and variables → Actions → New repository secret**

| Имя секрета | Значение |
|---|---|
| `TAVILY_API_KEY` | ключ с tavily.com |
| `GEMINI_API_KEY` | ключ с aistudio.google.com |
| `TELEGRAM_TOKEN` | токен бота от @BotFather |
| `TELEGRAM_CHAT_ID` | `@username` или `-100xxxxxxxxxx` |

### 3. Залей файлы в репозиторий

```bash
git add digest.py .github/workflows/digest.yml
git commit -m "add weekly digest bot"
git push
```

### 4. Проверь вручную

GitHub → вкладка **Actions** → **Weekly Ad Digest** → **Run workflow**

---

## Расписание

Каждый **понедельник в 10:16 МСК** (07:16 UTC).

Чтобы изменить время — отредактируй строку `cron` в `digest.yml`.
Конвертер: https://crontab.guru

---

## Как работает

1. Tavily выполняет 8 поисковых запросов по рекламным кейсам (Россия, СНГ, зарубежье)
2. Все результаты передаются в Gemini 2.0 Flash вместе с промптом
3. Gemini формирует структурированный дайджест на русском
4. Бот публикует дайджест в канал (разбивает на части если > 4096 символов)

## Стоимость

При запуске раз в неделю — **бесплатно** в пределах лимитов Gemini и Tavily free tier.
