import asyncio
import logging
import os
import socket
import time
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.exceptions import (
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand,
    BotCommandScopeDefault,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from config import BOT_TOKEN, UPLOADS_DIR
import postmypost_uploader

logging.basicConfig(level=logging.INFO)

router = Router()
scheduler = AsyncIOScheduler()


class RetryMiddleware(BaseRequestMiddleware):
    async def __call__(self, make_request, bot, method):
        for attempt in range(15):
            try:
                return await make_request(bot, method)
            except TelegramRetryAfter as exc:
                logging.warning("retry_after: жду %ss", exc.retry_after)
                await asyncio.sleep(exc.retry_after + 1)
            except (TelegramServerError, TelegramNetworkError) as exc:
                if attempt == 14:
                    raise
                wait = min(2 ** attempt, 30)
                logging.warning(
                    "%s — повтор %s/15 через %ss",
                    type(exc).__name__, attempt + 1, wait,
                )
                await asyncio.sleep(wait)
        return await make_request(bot, method)

TIME_FORMAT = "%Y-%m-%d %H:%M"

PLATFORMS = {
    "postmypost": {
        "label": "PostMyPost (все площадки)",
        "uploader": postmypost_uploader.upload_short,
    },
}


def platforms_keyboard(selected: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for key, info in PLATFORMS.items():
        mark = "✅" if key in selected else "☑️"
        rows.append(
            [InlineKeyboardButton(text=f"{mark} {info['label']}", callback_data=f"plat:{key}")]
        )
    rows.append(
        [InlineKeyboardButton(text="✅ Готово", callback_data="plat:done")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


class ShortForm(StatesGroup):
    video = State()
    platforms = State()
    title = State()
    description = State()
    publish_time = State()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ShortForm.video)
    await message.answer("Привет! Отправь вертикальное видео до 60 секунд")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Действие отменено. Нажми /start, чтобы начать заново.")


async def set_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="🚀 Начать — загрузить Shorts"),
            BotCommand(command="cancel", description="❌ Отменить действие"),
        ],
        scope=BotCommandScopeDefault(),
    )


@router.message(ShortForm.video)
async def on_video(message: Message, state: FSMContext) -> None:
    video = message.video
    if video is None:
        await message.answer("Это не видео. Отправь именно видео-файл.")
        return

    if video.duration is None or video.duration > 60:
        await message.answer("Видео длиннее 60 секунд. Отправь Shorts до 60 секунд.")
        return

    if video.width >= video.height:
        await message.answer(
            "Видео не вертикальное. Отправь вертикальное видео (ширина меньше высоты)."
        )
        return

    file = await message.bot.get_file(video.file_id)
    file_name = f"short_{message.from_user.id}_{int(time.time())}.mp4"
    dest = Path(UPLOADS_DIR) / file_name
    await message.bot.download_file(file.file_path, destination=dest)

    await state.update_data(video_path=str(dest))
    await state.set_state(ShortForm.platforms)
    await state.update_data(selected_platforms=[])
    await message.answer(
        "Видео сохранено ✅ Куда выложить?",
        reply_markup=platforms_keyboard([]),
    )


@router.callback_query(F.data.startswith("plat:"))
async def on_platform_choice(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    await callback.answer()
    data = await state.get_data()
    selected: list[str] = data.get("selected_platforms", [])

    choice = callback.data.split(":", 1)[1]
    if choice == "done":
        if not selected:
            await callback.message.answer("Выбери хотя бы одну платформу.")
            return
        await state.set_state(ShortForm.title)
        await callback.message.answer(
            "Отлично! Теперь отправь заголовок видео."
        )
        return

    if choice in selected:
        selected.remove(choice)
    elif len(selected) < len(PLATFORMS):
        selected.append(choice)

    await state.update_data(selected_platforms=selected)
    await callback.message.edit_reply_markup(
        reply_markup=platforms_keyboard(selected)
    )


@router.message(ShortForm.title)
async def on_title(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Отправь заголовок текстом.")
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(ShortForm.description)
    await message.answer("Теперь отправь описание видео.")


@router.message(ShortForm.description)
async def on_description(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Отправь описание текстом.")
        return
    await state.update_data(description=message.text.strip())
    await state.set_state(ShortForm.publish_time)
    await message.answer(
        "Во сколько опубликовать?\n"
        "Формат: ГГГГ-ММ-ДД ЧЧ:ММ (например, 2026-08-11 18:00)"
    )


@router.message(ShortForm.publish_time)
async def on_publish_time(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Отправь время текстом в формате ГГГГ-ММ-ДД ЧЧ:ММ.")
        return

    try:
        publish_at = datetime.strptime(message.text.strip(), TIME_FORMAT)
    except ValueError:
        await message.answer("Неверный формат. Пример: 2026-08-11 18:00")
        return

    if publish_at <= datetime.now():
        await message.answer("Это время уже прошло. Укажи будущее время.")
        return

    data = await state.get_data()
    selected: list[str] = data.get("selected_platforms", [])
    if not selected:
        await message.answer("Не выбрана платформа. Начни заново — /start")
        return

    scheduler.add_job(
        publish_job,
        trigger=DateTrigger(run_date=publish_at),
        args=[
            message.bot,
            message.from_user.id,
            data["video_path"],
            data["title"],
            data["description"],
            selected,
        ],
        id=f"upload_{int(time.time())}",
    )

    platform_labels = ", ".join(PLATFORMS[p]["label"] for p in selected)
    await state.clear()
    await message.answer(
        "✅ Видео запланировано на "
        f"{publish_at.strftime(TIME_FORMAT)}\n\n"
        f"📱 Куда: {platform_labels}\n"
        f"🎬 {data['title']}\n"
        f"📝 {data['description']}"
    )


async def publish_job(
    bot: Bot, chat_id: int, video_path: str, title: str, description: str, platforms: list[str]
) -> None:
    logging.info("Публикую видео: %s", video_path)
    success_lines = []
    fail_lines = []
    buttons = []
    for key in platforms:
        label = PLATFORMS[key]["label"]
        try:
            uploader = PLATFORMS[key]["uploader"]
            url = await asyncio.to_thread(uploader, video_path, title, description)
            success_lines.append(f"✅ {label}: {url}")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                buttons.append(
                    [InlineKeyboardButton(text=f"▶️ Открыть: {label}", url=url)]
                )
            logging.info("%s: %s", label, url)
        except Exception as exc:
            logging.exception("Ошибка в %s: %s", label, exc)
            fail_lines.append(f"❌ {label}: {exc}")

    Path(video_path).unlink(missing_ok=True)

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    message_text = "\n".join(success_lines + fail_lines) or "Ничего не опубликовано."
    await bot.send_message(
        chat_id, f"🎉 Результат публикации:\n{message_text}", reply_markup=keyboard
    )


async def main() -> None:
    logging.info("bot.py started, main() entered")
    telegram_api_ip = os.getenv("TELEGRAM_API_IP")
    if telegram_api_ip:
        original_getaddrinfo = socket.getaddrinfo

        def patched_getaddrinfo(host, *args, **kwargs):
            if host == "api.telegram.org":
                host = telegram_api_ip
            return original_getaddrinfo(host, *args, **kwargs)

        socket.getaddrinfo = patched_getaddrinfo
        logging.info("api.telegram.org -> %s", telegram_api_ip)

    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", 47583))
        lock.listen(1)
        logging.info("lock acquired")
    except OSError:
        logging.error("Бот уже запущен (порт 47583 занят). Завершение.")
        return

    bot = Bot(token=BOT_TOKEN)
    bot.session.middleware(RetryMiddleware())
    dp = Dispatcher()
    dp.include_router(router)
    await set_bot_commands(bot)
    scheduler.start()
    logging.info("starting polling")
    while True:
        try:
            await dp.start_polling(bot)
            break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logging.error("polling error: %s; retry in 10s", exc)
            await asyncio.sleep(10)
    logging.info("polling stopped")


if __name__ == "__main__":
    asyncio.run(main())