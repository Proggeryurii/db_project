import telebot
from telebot import types
import psycopg2
from random import shuffle
TOKEN = ''
bot = telebot.TeleBot(TOKEN)

# Подключение к базе данных PostgreSQL
conn = psycopg2.connect(database="clients_db", user="postgres", password="123")
cursor = conn.cursor()

# Создание таблиц, если они еще не созданы

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    password TEXT NOT NULL
);
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS words (
    id SERIAL PRIMARY KEY,
    word TEXT NOT NULL,
    translation TEXT NOT NULL
);
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS user_words (
    id SERIAL PRIMARY KEY,
    word TEXT NOT NULL,
    translation TEXT NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id)
);
''')


cursor.execute('''
CREATE TABLE IF NOT EXISTS deleted_words (
    id SERIAL PRIMARY KEY,
    word TEXT NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id)
);
''')
conn.commit()

# Добавление начального набора слов
# initial_words = [
#     ('red', 'красный'), ('blue', 'синий'), ('green', 'зеленый'),
#     ('yellow', 'желтый'), ('black', 'черный'), ('white', 'белый'),
#     ('he', 'он'), ('she', 'она'), ('it', 'оно'), ('they', 'они')
# ]
# cursor.executemany('INSERT INTO words (word, translation) VALUES (%s, %s)', initial_words)
# conn.commit()


# Функции для работы с базой данных

# Функция для получения трех случайных неправильных переводов
def get_wrong_translations(correct_word, correct_translation):
    cursor.execute('''
    SELECT translation FROM words
    WHERE word != %s AND translation != %s
    ORDER BY RANDOM() LIMIT 3
    ''', (correct_word, correct_translation))
    return [tr[0] for tr in cursor.fetchall()]


def get_correct_translation(word):
    cursor.execute('SELECT translation FROM words WHERE word = %s', (word,))
    result = cursor.fetchone()
    return result[0] if result else None


def get_random_word(user_id):
    cursor.execute('''
    SELECT word, translation FROM words
    WHERE word NOT IN (
        SELECT word FROM deleted_words WHERE user_id = %s
    )
    ''', (user_id,))
    words = cursor.fetchall()
    cursor.execute('''
        SELECT word, translation FROM user_words WHERE user_id = %s
        AND word NOT IN (
            SELECT word FROM deleted_words WHERE user_id = %s
        )
        ''', (user_id, user_id))
    words2 = cursor.fetchall()
    words.extend(words2)
    shuffle(words)
    return words[0] if words else None

@bot.message_handler(func=lambda message: message.text == 'Добавить слово')
def add_word(message):
    msg = bot.reply_to(message, 'Введите слово и его перевод через запятую (например: cat,кошка).')
    bot.register_next_step_handler(msg, process_word_addition)

def process_word_addition(message):
    word_data = message.text.split(',')
    if len(word_data) != 2:
        bot.reply_to(message, 'Неправильный формат. Попробуйте еще раз.')
        return
    word, translation = word_data
    cursor.execute('INSERT INTO user_words (word, translation, user_id) VALUES (%s, %s, %s)', (word, translation, message.chat.id))
    conn.commit()
    bot.reply_to(message, 'Слово добавлено!')

# Функция для удаления слова
@bot.message_handler(func=lambda message: message.text == 'Удалить слово')
def remove_word(message):
    msg = bot.reply_to(message, 'Введите слово по английский, которое вы хотите удалить.')
    bot.register_next_step_handler(msg, process_word_removal)

def process_word_removal(message):
    cursor.execute('DELETE FROM user_words WHERE user_id = %s AND word = %s', (message.chat.id, message.text))
    cursor.execute('INSERT INTO deleted_words (word, user_id) VALUES (%s, %s)', (message.text, message.chat.id))
    conn.commit()
    bot.reply_to(message, 'Слово удалено!')


# Функция для обработки команды /start
# Функция для обработки команды /start и добавления дополнительных кнопок
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    start_button = types.KeyboardButton('Начать')
    add_button = types.KeyboardButton('Добавить слово')
    remove_button = types.KeyboardButton('Удалить слово')
    markup.add(start_button, add_button, remove_button)
    bot.send_message(message.chat.id, 'Привет! Давай учить английские слова.', reply_markup=markup)


current_question = None

# Функция для начала теста
@bot.message_handler(func=lambda message: message.text == 'Начать')
def start_test(message):
    global current_question
    # Получаем случайное слово из базы данных
    random_word = get_random_word(message.from_user.id)
    if random_word:
        word, translation = random_word
        # Сохраняем правильный перевод в глобальной переменной
        current_question = {'word': word, 'translation': translation}
        # Получаем неправильные переводы
        wrong_translations = get_wrong_translations(word, translation)
        # Создаем кнопки с вариантами перевода
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
        translations = [translation] + wrong_translations
        shuffle(translations)
        for tr in translations:
            markup.add(types.KeyboardButton(tr))
        add_button = types.KeyboardButton('Добавить слово')
        remove_button = types.KeyboardButton('Удалить слово')
        markup.add(add_button, remove_button)
        # Отправляем сообщение с вопросом
        bot.send_message(message.chat.id, f'Как переводится слово "{word}"?', reply_markup=markup)
    else:
        bot.send_message(message.chat.id, 'Извините, слова для изучения закончились.')

def offer_next_action(chat_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    next_button = types.KeyboardButton('Следующее слово')
    add_button = types.KeyboardButton('Добавить слово')
    remove_button = types.KeyboardButton('Удалить слово')
    markup.add(next_button, add_button, remove_button)
    bot.send_message(chat_id, 'Что вы хотите сделать дальше?', reply_markup=markup)
# func=lambda message: current_question and message.text in [current_question['translation']] + get_wrong_translations(current_question['word'], current_question['translation'])
# Обработка ответа пользователя
@bot.message_handler(func=lambda message: current_question is not None)
def check_answer(message):
    global current_question
    # Проверяем правильность ответа
    if message.text == current_question['translation']:
        response = 'Правильно!'
    else:
        response = f'Неправильно {current_question['word']} это {current_question['translation']}'
    bot.reply_to(message, response)
    # Обнуляем текущий вопрос
    current_question = None
    # Предлагаем следующее действие
    offer_next_action(message.chat.id)

@bot.message_handler(func=lambda message: message.text == 'Следующее слово')
def handle_next_word(message):
    start_test(message)

if __name__ == "__main__":
    bot.polling(none_stop=True)


conn.close()

