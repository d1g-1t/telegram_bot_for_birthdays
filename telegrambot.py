import os
import time
import logging
from logging.handlers import RotatingFileHandler
from json.decoder import JSONDecodeError

import requests
from dotenv import load_dotenv
import telegram

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def init_logger() -> logging.Logger:
    """Настройки логера."""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s, %(levelname)s, %(message)s, %(name)s'
    )
    file_handler = RotatingFileHandler(
        'homework.log', mode='w', maxBytes=50000000, backupCount=5
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    return logger


logger = init_logger()


def check_tokens() -> bool:
    """Функция проверки доступности переменных окружения."""
    if not any([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
        logger.critical('Отсутвует переменная окружения.')
        return False
    return True


def send_message(bot: telegram.Bot, message: str) -> None:
    """Функция отправки сообщений в чат Telegram."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug('Telegram бот запущен.')
    except telegram.TelegramError as error:
        logger.error(f'Ошибка отправки сообщения в чат: {error}.')


def get_api_answer(timestamp: float) -> dict:
    """Функция направления запроса к API 'Яндекс.Домашка'."""
    params = {'from_date': int(round(timestamp))}
    try:
        homework_status = requests.get(ENDPOINT,
                                       headers=HEADERS,
                                       params=params
                                       )
        if homework_status.status_code != 200:
            error_message = (
                f'Ошибка при запросе к API "Яндекс.Домашка". '
                f'Статус код: {homework_status.status_code}'
            )
            logger.error(error_message)
            raise Exception(error_message)
        homework_status.raise_for_status()
    except requests.exceptions.RequestException as error:
        error_message = (
            f'Ошибка направления запроса к API "Яндекс.Домашка": {error}.'
        )
        logger.error(error_message)
        raise Exception(error_message)

    try:
        return homework_status.json()
    except JSONDecodeError as response_error:
        error_message = f'Ошибка при получении ответа: {response_error}'
        logger.error(error_message)
        raise JSONDecodeError(error_message)


def check_response(response: dict) -> dict:
    """Функция проверки правильности ответа."""
    if not isinstance(response, dict):
        raise TypeError('Полученный ответ не является словарем.')
    if 'homeworks' not in response:
        raise KeyError('В ответе отсутствует информация о домашних заданиях.')
    if 'current_date' not in response:
        raise KeyError('В ответе отсутствует информация о текущей дате.')
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError('Значение ключа homeworks не является списком.')
    if not homeworks:
        return None
    return homeworks[0]


def parse_status(homework):
    """Проверка статуса конкретной домашней работы."""
    homework_name = homework.get('homework_name')
    if homework_name is None:
        raise KeyError('Ключ "homework_name" отсутствует.')
    if 'status' not in homework:
        raise KeyError('Ключ "status" отсутствует.')
    homework_status = homework['status']
    if homework_status not in HOMEWORK_VERDICTS:
        raise SystemError('Неизвестный статус')
    verdict = HOMEWORK_VERDICTS.get(homework_status)
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main() -> None:
    """Основная логика работы бота."""
    if not check_tokens():
        exit()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    send_message(bot, 'Telegram бот запущен.')
    timestamp = time.time()
    while True:
        try:
            response = get_api_answer(timestamp)
            homework = check_response(response)
            if homework:
                message = parse_status(homework)
                send_message(bot, message)
            else:
                logger.debug('Статус проверки работы не изменён.')
            timestamp = time.time()
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            send_message(bot, message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
