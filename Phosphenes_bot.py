import getopt
import sys

from telebot import types, TeleBot, time

import datetime
from datetime import datetime

import os
import schedule
import threading
import sqlite3
import requests


class User:
    def __init__(self, user_id, name, nickname):
        self.id, self.name, self.nickname = user_id, name, nickname


class ActiveUser:
    def __init__(self, user_id):
        self.id = user_id
        self.current_func = []


class BotStorage:
    """Хранилище бота"""

    def __init__(self, bot_token_: str = None, admin_id_: int = None) -> None:
        self.db_name = "volley_bot.db"

        if bot_token_ is None and "VOLLEY_BOT_TOKEN" not in os.environ:
            raise AssertionError("Please configure VOLLEY_BOT_TOKEN as os environment variables")
        self._bot_token = os.environ["VOLLEY_BOT_TOKEN"] if bot_token_ is None else bot_token_

        if admin_id_ is None and "VOLLEY_BOT_ADMIN" not in os.environ:
            raise AssertionError("Please configure VOLLEY_BOT_ADMIN as os environment variables")
        self._admin_id = os.environ["VOLLEY_BOT_ADMIN"] if admin_id_ is None else admin_id_

        self._allowed_users = {}
        self._active_users = {}
        self._teams = set()
        self._voting_results = {}

        self.restore_state()

    def __del__(self) -> None:
        self.save_state()

    def __str__(self) -> str:
        return "bot_token = {0._bot_token}, admin_id = {0._admin_id}".format(self)

    def get_bot_token(self) -> str:
        return self._bot_token

    def get_admin_id(self) -> int:
        return self._admin_id

    def add_user_to_active_list(self, user_id: int) -> None:
        self._active_users[user_id] = ActiveUser(user_id)

    def get_active_users(self) -> {}:
        return self._active_users

    def is_user_allowed(self, user_id) -> bool:
        return user_id in self._allowed_users

    def get_allowed_users(self):
        return self._allowed_users

    def get_active_user_handle(self, user_id) -> ActiveUser:
        if user_id not in self.get_active_users():
            self.add_user_to_active_list(user_id)
        return self._active_users[user_id]

    def get_teams(self) -> set:
        return self._teams

    def add_vote(self, user_id: int, vote) -> None:
        self._voting_results[user_id] = vote

    def get_voting_results(self):
        return self._voting_results

    def clear_voting_results(self):
        return self._voting_results.clear()

    def restore_state(self) -> None:
        sql_connect = sqlite3.connect(self.db_name)
        c = sql_connect.cursor()

        for e in c.execute("select telegram_id, real_name, nickname "
                           "from main.users where allowed_access <> 0").fetchall():
            self._allowed_users[e[0]] = User(e[0], e[1], e[2])

        self._teams = c.execute("select name from teams order by id").fetchall()

        c.close()
        sql_connect.close()

    def save_state(self) -> None:
        sql_connect = sqlite3.connect(self.db_name)
        sql_connect.close()
        pass


class VolleyBot:
    """Реализация бота"""

    def __init__(self, bot_token_: str = None, admin_id_: int = None) -> None:
        self._storage = BotStorage(bot_token_=bot_token_, admin_id_=admin_id_)
        self._bot = TeleBot(self._storage.get_bot_token())

    def __str__(self) -> str:
        return str(self._storage)

    def get_bot(self) -> TeleBot:
        return self._bot

    def get_admin_id(self) -> int:
        return self._storage.get_admin_id()

    def add_user_to_active_list(self, user_id: int) -> None:
        return self._storage.add_user_to_active_list(user_id)

    def get_active_user_handle(self, user_id) -> ActiveUser:
        return self._storage.get_active_user_handle(user_id)

    def clear_voting_results(self):
        return self._storage.clear_voting_results()

    def bot_send_message_to_allowed_users(self, text):
        for user in self._storage.get_allowed_users():
            self.get_bot().send_message(user, text)

    def bot_goto_start_menu(self, user_id):
        self.get_active_user_handle(user_id).current_func = [["main_menu", "", ""]]
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(*[types.KeyboardButton(n) for n in ('Расписание', 'Соревнования')])
        kb.add(types.KeyboardButton('Голосование'))
        kb.add(types.KeyboardButton('Прогноз погоды'))
        return kb

    def bot_goto_x_menu(self, msg, next_msg_text, b_names: [], last_b_name: str, b_in_line: int):
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        for row in [(b_names[i:i + b_in_line]) for i in range(0, len(b_names), b_in_line)]:
            kb.add(*[types.KeyboardButton(c) for c in row])
        if last_b_name is not None:
            kb.add(types.KeyboardButton(last_b_name))
        if next_msg_text is not None:
            self.get_bot().send_message(msg.from_user.id, text=next_msg_text, reply_markup=kb)
        return kb

    def bot_stop(self):
        self.get_bot().stop_bot()

    def bot_start_command(self, msg):
        chat_id = msg.chat.id
        self.add_user_to_active_list(chat_id)

        user_id = msg.from_user.id
        # пока идёт проверка, отключим функциональность, ограничивающую пользователей бота
        # if not self._storage.is_user_allowed(user_id):  # проверяем, разрешённый ли это пользователь
        #     bot.send_message(chat_id, "Для доступа обратитесь к администратору")
        #     return

        kb = self.bot_goto_start_menu(user_id)

        self.get_bot().send_sticker(chat_id, open('стикер.webp', 'rb'))
        self.get_bot().send_message(chat_id,
                                    text='Hi, {0.first_name}! Click on the button below 👇'.format(msg.from_user),
                                    reply_markup=kb)  # welcome message

    def bot_message(self, msg):
        return_btn_name = 'В главное меню'
        user_id = msg.from_user.id
        current_func = self.get_active_user_handle(user_id).current_func

        if msg.text == return_btn_name:
            kb = self.bot_goto_start_menu(user_id)
            self.get_bot().send_message(msg.chat.id, 'Выберете команду', reply_markup=kb)
            return

        elif msg.text == 'Голосование':
            self.bot_goto_x_menu(msg, 'Кто будет сегодня на тренировке?', ['Буду', 'Не буду'], return_btn_name, 2)

        elif msg.text == 'total_results':
            self.bot_total_results(msg)

        elif msg.text == 'Расписание':
            self.bot_goto_x_menu(msg, 'Выберете команду', ['Каравелла'], return_btn_name, 2)

        elif msg.text == 'Соревнования':
            self.bot_goto_x_menu(msg, 'Выберете действие', ['Чемпионат г.Архангельска'],
                                 return_btn_name, 2)

        elif msg.text == 'Каравелла':
            self.bot_goto_x_menu(msg, 'Выберете день недели', ['Среда', 'Пятница', 'Воскресенье'],
                                 return_btn_name, 2)

        elif msg.text in ['Среда', 'Пятница', 'Воскресенье']:
            t = '18:00 - 21:00' if msg.text == 'Среда' \
                else ('20:00 - 22:00' if msg.text == 'Пятница' else '19:30 - 21:00')
            self.bot_goto_x_menu(msg, t, ['Среда', 'Пятница', 'Воскресенье'],
                                 return_btn_name, 2)

        elif msg.text == 'Чемпионат г.Архангельска':
            self.bot_goto_x_menu(msg, 'Выберете действие', ['Расписание и результаты'], return_btn_name, 2)

        elif msg.text == 'Расписание и результаты':
            kb = types.InlineKeyboardMarkup(row_width=2)
            for k in [types.InlineKeyboardButton(t[0], callback_data=t[0]) for t in self._storage.get_teams()]:
                kb.add(k)
            self.get_bot().send_message(msg.chat.id, "Выберите первую команду:", reply_markup=kb)

        elif msg.text == 'Прогноз погоды':
            bot.send_message(msg.from_user.id, 'Отправьте боту название города и он скажет, какая там погода')

        else:
            if len(current_func) > 1 and current_func[-1][0] == 'Прогноз погоды':
                self.bot_show_weather(city=msg.text, user_id=user_id)
                return
            else:
                kb = self.bot_goto_start_menu(user_id)
                self.get_bot().send_message(msg.chat.id, 'Я Вас не понимаю, попробуйте выбрать иное', reply_markup=kb)
                return

        current_func.append([msg.text, "", ""])

    def bot_send_all(self, msg):
        if msg.chat.id == self.get_admin_id():
            for user_id in self._storage.get_active_users():
                self._bot.send_message(user_id, msg.text[msg.text.find(' '):])
                self._bot.reply_to(msg, 'Сообщение отправлено всем пользователям.')
        else:
            self._bot.reply_to(msg, 'У вас нет доступа к этой команде.')

    def bot_record_vote_for_going(self, message):
        user_id = message.from_user.id
        if self._storage.is_user_allowed(user_id):  # проверяем, разрешённый ли пользователь
            self._storage.add_vote(user_id, message.text)
            self.get_bot().send_message(message.chat.id,
                                        text='Your answer is recorded. Click the button "Return to the main menu"')
        else:
            bot.send_message(message.chat.id, text='Sorry, you are not allowed to vote.')

    def bot_total_results(self, msg):
        user_id = msg.from_user.id  # Получаем идентификатор отправителя
        if not self._storage.is_user_allowed(user_id):
            self.get_bot().send_message(msg.chat.id, "Невозможно просмотреть результаты")
            self.bot_goto_start_menu(user_id)
            return

        user_names_with_vote1 = []
        user_names_with_vote2 = []

        for u_id, vote in self._storage.get_voting_results() .items():
            user = bot.get_chat_member(msg.chat.id, u_id)
            user_name = user.user.first_name  # Получаем имя пользователя

            if vote == "Буду":
                user_names_with_vote1.append(user_name)
            elif vote == "Не буду":
                user_names_with_vote2.append(user_name)

        result_message = "Будут участвовать:\n" + "\n".join(user_names_with_vote1)
        result_message += "\n\nПропустят тренировку:\n" + "\n".join(user_names_with_vote2)

        self.get_bot().send_message(msg.chat.id, result_message)

    def bot_show_schedule(self, msg, user_id):
        current_func = self.get_active_user_handle(user_id).current_func
        if len(current_func) < 2 or current_func[-1][0] != 'Расписание и результаты':
            self.bot_goto_start_menu(user_id)
            return

        teams_func = current_func[-1]  # new_func[1] == first_team, new_func[2] == second_team
        if teams_func[1] and teams_func[2] == "":
            keyboard = types.InlineKeyboardMarkup(row_width=2)
            for team in self._storage.get_teams():
                if team[0] != teams_func[1]:
                    button = types.InlineKeyboardButton(team[0], callback_data=team[0])
                    keyboard.add(button)
            self.get_bot().send_message(msg.chat.id, "Выберите вторую команду:", reply_markup=keyboard)

    # Обработчик выбора inline кнопок
    def bot_handle_button_click(self, call):
        user_id = call.from_user.id
        current_func = self.get_active_user_handle(user_id).current_func
        if len(current_func) < 2 or current_func[-1][0] != 'Расписание и результаты':
            self.bot_goto_start_menu(user_id)
            return

        teams_func = current_func[-1]  # new_func[1] == first_team, new_func[2] == second_team
        if teams_func[1] == "":
            teams_func[1] = call.data
            self.bot_show_schedule(call.message, user_id)  # Call another function for selecting the second team
        elif teams_func[2] == "":
            teams_func[2] = call.data

            sql_connect = sqlite3.connect(self._storage.db_name)
            cursor = sql_connect.cursor()

            query = ("SELECT s.date, s.time, s.result, s.winner, t1.name, t2.name "
                     "FROM schedule s, teams t1, teams t2 "
                     "WHERE t1.name in (?, ?) AND t2.name in (?, ?) and s.team1 = t1.id and s.team2 = t2.id")

            cursor.execute(query, (teams_func[1], teams_func[2], teams_func[1], teams_func[2]))
            results = cursor.fetchall()

            if results is not None and len(results) != 0:
                if results[0][2] is None:
                    self.get_bot().send_message(call.message.chat.id,
                                                f"📅 Дата: {results[0][0]}\n⌛ Время: {results[0][1]}")
                else:
                    self.get_bot().send_message(call.message.chat.id,
                                                f"📅 Дата: {results[0][0]}\n⌛ Время: {results[0][1]}\n"
                                                f"Результат встречи: {results[0][2]}\nПобедитель: {results[0][3]}")
            else:
                self.get_bot().send_message(call.message.chat.id, "Информация о матче не найдена.")

            cursor.close()
            sql_connect.close()

            # Reset the selected teams
            teams_func[1] = teams_func[2] = ""

    def bot_show_weather(self, city: str, user_id) -> None:
        try:
            url = 'https://api.openweathermap.org/data/2.5/weather?q=' + city + (
                '&units=metric&lang=ru&appid=852e6d01a0e4164726ba6652877ff78d')
            weather_data = requests.get(url).json()

            if 'cod' in weather_data and weather_data['cod'] == '404':
                self.get_bot().send_message(user_id, weather_data['message'])
                return

            temperature = round(weather_data['main']['temp'])
            temperature_feels = round(weather_data['main']['feels_like'])
            wind = round(weather_data['wind']['speed'])
            if wind < 5:
                sss = '✅ Погода хорошая, ветра почти нет'
            elif wind < 10:
                sss = '🤔 На улице ветрено, оденьтесь чуть теплее'
            elif wind < 20:
                sss = '❗️ Ветер очень сильный, будьте осторожны, выходя из дома'
            else:
                sss = '❌ На улице шторм, на улицу лучше не выходить'
            humidity = round(weather_data['main']['humidity'])
            temperature_max = round(weather_data['main']['temp_max'])
            temperature_min = round(weather_data['main']['temp_min'])
            w_now = 'Сейчас в городе ' + city + ' ' + str(temperature) + ' °C'
            w_feels = 'Ощущается как ' + str(temperature_feels) + ' °C'
            sunrise_timestamp = datetime.fromtimestamp(weather_data["sys"]["sunrise"])
            sunset_timestamp = datetime.fromtimestamp(weather_data["sys"]["sunset"])
            length_of_the_day = datetime.fromtimestamp(
                weather_data["sys"]["sunset"]) - datetime.fromtimestamp(weather_data["sys"]["sunrise"])
            code_to_smile = {
                "Clear": "Ясно \U00002600",
                "Clouds": "Облачно \U00002601",
                "Rain": "Дождь \U00002614",
                "Drizzle": "Дождь \U00002614",
                "Thunderstorm": "Гроза \U000026A1",
                "Snow": "Снег \U0001F328",
                "Mist": "Туман \U0001F32B"
            }
            weather_description = weather_data["weather"][0]["main"]
            if weather_description in code_to_smile:
                wd = code_to_smile[weather_description]
            else:
                wd = " "
            self.get_bot().send_message(user_id,
                                        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}\n{w_now}\n{wd}\n{w_feels}\n"
                                        f"Ветер: {wind} м/с\n{sss}\n"
                                        f"Влажность: {humidity}%\n"
                                        f"Максимальная температура: {temperature_max}°C\n"
                                        f"Минимальная температура: {temperature_min}°C\n"
                                        f"Восход солнца: {sunrise_timestamp}\n"
                                        f"Заход солнца: {sunset_timestamp}\n"
                                        f"Продолжительность дня: {length_of_the_day}\n"
                                        f"Хорошего дня!")
        except Exception as _:
            self.get_bot().send_message(user_id, "Не удалось получить данные о погоде")


opt = dict(getopt.getopt(sys.argv[1:], "b:a", ["bot_token=", "admin_id="])[0])
volleyBot = VolleyBot(bot_token_=opt["--bot_token"], admin_id_=int(opt["--admin_id"]))
bot = volleyBot.get_bot()


@volleyBot.get_bot().message_handler(commands=['stop'])
def stop(): volleyBot.bot_stop()


@volleyBot.get_bot().message_handler(commands=['start'])
def start(msg): volleyBot.bot_start_command(msg)


@bot.message_handler(commands=['send_all'])
def send_all(msg): volleyBot.bot_send_all(msg)


@bot.message_handler(func=lambda msg: msg.text in ['Буду', 'Не буду'])
def record_vote_for_going(msg): volleyBot.bot_record_vote_for_going(msg)


@bot.message_handler(commands=['total_results'])
def total_results(msg): volleyBot.bot_total_results(msg)


@bot.message_handler(content_types=['text'])
def message_handler(msg): volleyBot.bot_message(msg)


@bot.message_handler(func=lambda message: message.text == 'Расписание и результаты')
def show_schedule(msg): volleyBot.bot_show_schedule(msg, msg.from_user.id)


@bot.callback_query_handler(func=lambda call: True)
def handle_button_click(call): volleyBot.bot_handle_button_click(call)


# функция для сброса результатов голосования в определенные дни
def reset_voting_results_weekly():
    # список, содержащий номера дней недели, в которые происходит сброс результатов голосования
    if datetime.datetime.now().weekday() in [0, 3, 5]:
        volleyBot.clear_voting_results()


# Функция 'send_scheduled_message' для отправки сообщения каждому пользователю из списка user_ids
def send_scheduled_message():
    volleyBot.bot_send_message_to_allowed_users("You need to take the survey. Click on the 'Голосование' button.")


# расписываем определенные дни и время, в которые будет выполняться функция send_scheduled_message()
schedule.every().wednesday.at('10:00').do(send_scheduled_message)
schedule.every().friday.at('10:00').do(send_scheduled_message)
schedule.every().sunday.at('10:00').do(send_scheduled_message)


# Эта функция запускает запланированные задачи с помощью метода schedule.run_pending()
# и включает небольшую задержку с помощью time.sleep(1)
def schedule_messages():
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    scheduling_thread = threading.Thread(target=schedule_messages)
    scheduling_thread.start()
    volleyBot.get_bot().infinity_polling()
