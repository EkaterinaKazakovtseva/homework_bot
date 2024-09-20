from http import HTTPStatus
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import time

from dotenv import load_dotenv
import requests
import telebot

from exceptions import IncorrectAPIRequest, IncorrectStatusRequest


load_dotenv()


logging.basicConfig(
    level=logging.DEBUG,
    filename='program.log',
    format='%(asctime)s, %(levelname)s, %(message)s, %(name)s'
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = RotatingFileHandler(
    'my_logger.log', maxBytes=50000000, backupCount=5)
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
    tokens = (
        PRACTICUM_TOKEN,
        TELEGRAM_CHAT_ID,
        TELEGRAM_TOKEN,
    )
    return all(tokens)


def send_message(bot, message):
    """Отправляет сообщение в Telegram-чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug('Отправлено сообщение')
    except Exception as error:
        logger.error(f'Ошибка отправки сообщения: {error}')


def get_api_answer(timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса."""
    payload = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
    except requests.RequestException:
        raise IncorrectAPIRequest('Некорректный API')
    if response.status_code != HTTPStatus.OK:
        raise IncorrectStatusRequest('Статус запроса не 200')
    return response.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError(f'Неверный тип данных,'
                        f'полученный тип данных ответа {type(response)}')
    keys = ('homeworks',
            'current_date',
            )
    if not all(key in response for key in keys):
        raise KeyError('В ответе API отсуствует один из ключей')
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise TypeError(f'Неверный тип данных по ключу homework,'
                        f'полученный тип данных {type(homeworks)}')
    if not homeworks:
        raise IndexError('Список домашних работ пустой')
    last_homework = homeworks[0]
    return last_homework


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
        raise KeyError('Ответ последней домашней'
                       'не соответствует стандартным или отсуствует.')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    logger.debug('Бот запущен')
    if not check_tokens():
        logger.critical('Ошибка работы программы: '
                        'нехватает переменных окружения\n'
                        'Программа остановлена.')
        sys.exit()
    bot = telebot.TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_message = ''
    while True:
        try:
            api_answer = get_api_answer(timestamp)
            last_homework = check_response(api_answer)
            message = parse_status(last_homework)
        except Exception as error:
            message = f'Ошибка работы программы: {error}'
            logger.error(f'Ошибка работы программы: {error}')
        finally:
            if message != last_message:
                send_message(bot, message)
                last_message = message
            else:
                logger.debug('В телеграмм ничего не отправлено.')
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
