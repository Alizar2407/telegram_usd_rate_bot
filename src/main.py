import redis
import asyncio
import aiohttp

from src.settings import settings

from icecream import ic
from xml.etree import ElementTree

from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.utils.token import TokenValidationError

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage


async def get_usd_rate():

    url = "https://www.cbr.ru/scripts/XML_daily.asp"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                xml_data = await response.text()
                root = ElementTree.fromstring(xml_data)

                for item in root.findall("Valute"):
                    code = item.find("CharCode").text
                    if code == "USD":
                        value = float(item.find("Value").text.replace(",", "."))
                        return value

    except aiohttp.ClientError as e:
        print(f"Ошибка при запросе к API: {e}")
        return None

    except ElementTree.ParseError:
        print("Ошибка при разборе XML-ответа.")
        return None

    except Exception as e:
        print(f"Произошла непредвиденная ошибка: {e}")
        return None

    return None


async def show_usd_rate(message: Message, state: FSMContext, name: str):
    success_message_pattern = (
        "Рад знакомству, {name}!\n" + "Курс доллара сегодня {usd_to_rub:0.2f} р."
    )
    success_message_pattern_cached = (
        "Рад знакомству, {name}!\n"
        "Курс доллара сегодня {usd_to_rub:0.2f} р. (Использовано значение из кеша)"
    )
    failure_message_pattern = (
        "Рад знакомству, {name}!\n"
        "К сожалению, не удалось получить актуальный курс доллара."
    )

    # Try to get usd rate from cache
    usd_to_rub_cached = None
    if redis_cache is not None:
        usd_to_rub_cached = redis_cache.get("usd_to_rub")

    # If success, display it
    if usd_to_rub_cached:
        usd_to_rub = float(usd_to_rub_cached)

        await message.answer(
            success_message_pattern_cached.format(name=name, usd_to_rub=usd_to_rub)
        )

    # Otherwise, get value from CBR API
    else:
        usd_to_rub = await get_usd_rate()

        # Success
        if usd_to_rub:
            # Update Redis cache
            if redis_cache is not None:
                redis_cache.set("usd_to_rub", usd_to_rub, ex=60)  # 1 min
            await message.answer(
                success_message_pattern.format(name=name, usd_to_rub=usd_to_rub)
            )

        # Failure
        else:
            await message.answer(failure_message_pattern.format(name=name))


# ------------------------------------------------------------------------------
bot = Bot(token=settings.BOT_API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()


def connect_to_redis():

    try:
        redis_instance = redis.from_url(settings.REDIS_URL)
        redis_instance.ping()  # exception if redis is not available
        return redis_instance

    except Exception:
        print(f"Не удалось подключиться к Redis.")
        return None


# Connect to Redis, if it is available
redis_cache = connect_to_redis()
ic(redis_cache is not None)


class Form(StatesGroup):
    name = State()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    ic(message.chat.username, message.text)

    await message.answer("Добрый день. Как вас зовут?")
    await state.set_state(Form.name)


@router.message(Command("usd"))
async def cmd_usd_to_rub(message: Message, state: FSMContext):
    ic(message.chat.username, message.text)

    # Check if user's name is stored
    user_data = await state.get_data()
    name = user_data.get("name")

    if not name:
        await message.answer("Пожалуйста, укажите свое имя. Для этого введите /start.")
        return

    # Display USD rate
    await show_usd_rate(message, state, name)


@router.message(Form.name)
async def process_name(message: Message, state: FSMContext):
    ic(message.chat.username, message.text)

    # Get user name
    name = message.text

    # Save user's name
    await state.update_data(name=name)

    # Display USD rate
    await show_usd_rate(message, state, name)


async def main():
    dp.include_router(router)
    await dp.start_polling(bot)


# ------------------------------------------------------------------------------
if __name__ == "__main__":

    try:
        asyncio.run(main())

    except TokenValidationError as error:
        print(f"Произошла ошибка при валидации токена:\n{error}")

    except Exception as error:
        print(f"Произошла непредвиденная ошибка:\n{error}")
