from http import HTTPStatus
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import time

from dotenv import load_dotenv
import requests
import telebot

from exceptions import IncorrectAPIRequest, IncorrectStatusRequest


load_dotenv()


BASE_DIR = Path(__file__).resolve().parent
Path(BASE_DIR / "logs").mkdir(exist_ok=True)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = RotatingFileHandler(
    BASE_DIR / 'logs/my_logger.log',
    mode='a',
    maxBytes=50 * 1024 * 1024,
    backupCount=5)
logger.addHandler(handler)

PRACTICUM_TOKEN = os.getenv('PRAKTIKUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверяет доступность переменных окружения."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID
    }
    none_tokens = [name_token
                   for name_token, value in tokens.items()
                   if value is None]
    if none_tokens:
        logger.critical('Ошибка работы программы: '
                        f'мало переменных окружения {", ".join(none_tokens)}'
                        'Программа остановлена.')
        return False
    return True


def send_message(bot, message):
    """Отправляет сообщение в Telegram-чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except telebot.apihelper.ApiException as error:
        logger.error(f'Ошибка отправки сообщения: {error}')
    else:
        logger.debug('Отправлено сообщение')


def get_api_answer(timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса."""
    payload = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
    except requests.RequestException as error:
        raise IncorrectAPIRequest(f'Ошибка при выполнении запроса: {error}')
    if response.status_code != HTTPStatus.OK:
        raise IncorrectStatusRequest('Статус запроса не 200')
    return response.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError(f'Неверный тип данных,'
                        f'полученный тип данных ответа {type(response)}')
    elif 'homeworks' not in response:
        raise IncorrectAPIRequest('В ответе API отсутствует ключ "homeworks"')
    elif not isinstance(response['homeworks'], list):
        raise TypeError(f'Неверный тип данных по ключу homework,'
                        f'полученный тип данных {type(response)}')
    return response.get('homeworks')


def parse_status(homework):
    """Извлекает из информации о конкретной домешней работе ее статус."""
    homework_name = homework.get('homework_name')
    if not homework_name:
        raise KeyError('Отсуствует название домашней работы.')
    homework_status = homework.get('status')
    if not homework_status:
        raise KeyError('Отсуствует статус домашней работы.')
    verdict = HOMEWORK_VERDICTS.get(homework_status)
    if not verdict:
        raise ValueError('Ответ последней домашней'
                         'не соответствует стандартным или отсуствует.')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    logging.Formatter('%(asctime)s, %(levelname)s, %(message)s, %(name)s')
    logger.debug('Бот запущен')
    bot = telebot.TeleBot(token=TELEGRAM_TOKEN)
    if not check_tokens():
        os._exit()
    timestamp = int(time.time())
    last_message = ''
    while True:
        try:
            api_answer = get_api_answer(timestamp)
            last_homework = check_response(api_answer)
            timestamp = api_answer.get('current_date', timestamp)
            if last_homework:
                current_homework = last_homework[0]
                message = parse_status(current_homework)
                if message != last_message:
                    last_message = message
                    send_message(bot, message)
        except telebot.apihelper.ApiException as error:
            logger.error(f'Ошибка отправки сообщения: {error}')
        except Exception as error:
            message = f'Ошибка работы программы: {error}'
            if message != last_message:
                last_message = message
                logger.error(message)
                send_message(bot, message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
