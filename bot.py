import asyncio
import logging
import socket
import time
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from config import BOT_TOKEN, UPLOADS_DIR
import instagram_uploader
import tiktok_uploader
import upload_post_uploader
import youtube_uploader

logging.basicConfig(level=logging.INFO)

router = Router()
scheduler = AsyncIOScheduler()

TIME_FORMAT = "%Y-%m-%d %H:%M"

PLATFORMS = {
    "youtube": {"label": "YouTube", "uploader": youtube_uploader.upload_short},
    "tiktok": {"label": "TikTok", "uploader": tiktok_uploader.upload_short},
    "reels": {"label": "Instagram Reels", "uploader": instagram_uploader.upload_short},
    "upload_post": {
        "label": "Upload-Post (все площадки)",
        "uploader": upload_post_uploader.upload_short,
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
    auth_code = State()
    video = State()
    platforms = State()
    title = State()
    description = State()
    publish_time = State()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    if youtube_uploader.credentials_valid():
        await state.set_state(ShortForm.video)
        await message.answer("Привет! Отправь вертикальное видео до 60 секунд")
        return

    flow = youtube_uploader.build_auth_flow()
    url = youtube_uploader.get_auth_url(flow)
    await state.update_data(auth_flow=flow)
    await state.set_state(ShortForm.auth_code)
    await message.answer(
        "Для публикации нужна авторизация YouTube.\n\n"
        "1️⃣ Открой ссылку (можно на телефоне):\n"
        f"{url}\n\n"
        "2️⃣ Войди в аккаунт Google и разреши доступ.\n"
        "3️⃣ Откроется страница с ошибкой localhost — это нормально. "
        "Скопируй из адресной строки всё, что идёт после code=, и пришли сюда."
    )


@router.message(ShortForm.auth_code)
async def on_auth_code(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    flow = data.get("auth_flow")
    if flow is None:
        await message.answer("Что-то пошло не так. Напиши /start.")
        return

    code = youtube_uploader.extract_code(message.text or "")
    if not code:
        await message.answer(
            "Код пустой. Открой ссылку, разреши доступ и скопируй код из адресной строки."
        )
        return

    try:
        youtube_uploader.save_token_from_code(flow, code)
    except Exception as exc:
        await message.answer(f"Ошибка авторизации: {exc}\nПопробуй ещё раз — /start")
        return

    await state.set_state(ShortForm.video)
    await message.answer("Привет! Отправь вертикальное видео до 60 секунд")


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
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", 47583))
        lock.listen(1)
        logging.info("lock acquired")
    except OSError:
        logging.error("Бот уже запущен (порт 47583 занят). Завершение.")
        return

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    scheduler.start()
    logging.info("starting polling")
    await dp.start_polling(bot)
    logging.info("polling stopped")


if __name__ == "__main__":
    asyncio.run(main())