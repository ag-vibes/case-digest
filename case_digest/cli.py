from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .checks import check_integrations
from .config import Settings
from .pipeline import Pipeline
from .publishing import TelegramPublisher


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Case Digest")
    parser.add_argument("--mode", choices=("check", "dry-run", "publish"), default="dry-run")
    parser.add_argument("--sources", type=Path, default=Path("sources.yaml"))
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--without-telegram", action="store_true")
    parser.add_argument("--confirm-channel", default="")
    parser.add_argument("--log-level", default="INFO")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = Settings.from_env()
    include_telegram = not args.without_telegram
    if args.mode == "check":
        for message in check_integrations(settings, include_telegram):
            print(f"✓ {message}")
        print("Проверка завершена без публикации.")
        return

    report = Pipeline(settings, args.sources, args.artifacts).run(include_telegram, args.days)
    for source in report.source_health:
        marker = "✓" if source.status == "ok" else "!"
        detail = f" — {source.detail}" if source.detail else ""
        print(f"{marker} {source.source_name}: {source.status}, {source.candidates}{detail}")
    print(
        f"Собрано: {report.collected_count}; извлечено: {report.extracted_count}; "
        f"после дедупликации: {report.deduplicated_count}; отобрано: {len(report.selected)}"
    )
    print(f"Предпросмотр: {args.artifacts / 'preview.md'}")
    if args.mode == "dry-run":
        print("Dry-run завершён. В Telegram ничего не отправлено.")
        return

    if not (settings.telegram_token and settings.telegram_chat_id):
        raise RuntimeError("Для публикации нужны TELEGRAM_TOKEN и TELEGRAM_CHAT_ID")
    if args.confirm_channel != settings.telegram_chat_id:
        raise RuntimeError("Публикация требует --confirm-channel со значением TELEGRAM_CHAT_ID")
    ids = TelegramPublisher(settings.telegram_token, settings.telegram_chat_id).publish(
        report.selected, report.period_start, report.period_end
    )
    print(f"Опубликовано сообщений: {len(ids)}")


if __name__ == "__main__":
    main()
