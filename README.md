# MAX и Telegramm Bot для регистрации на турниры

Бот для MAX и Telegramm, позволяющий регистрировать участников на турниры, просматривать списки и отменять регистрации.

## 📋 Функциональность

### Для всех пользователей:
- `/start` - начать работу
- `/help` - справка по командам
- `/register` - зарегистрировать участника на турнир
- `/participants` - посмотреть участников турнира
- `/my_registrations` - показать мои регистрации
- `/cancel_registration` - отменить свою регистрацию

### Для администраторов:
- `/add_tournament` - добавить новый турнир
- `/delete_tournament` - удалить турнир

## 🚀 Установка

Установка bot-а в директорию /opt/bot/tbot-ttclub-etalon

````
cd /opt
mkdir bot
cd bot
git clone https://github.com/m-larin/tbot-ttclub-etalon.git
cd tbot-ttclub-etalon
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp instance/config.py.example instance/config.py
groupadd -r tbot
useradd -r -g tbot -d /opt/bot -s /sbin/nologin tbot
mkdir data
chmod tbot:tbot data
````

Внести правки в конфиг файл instance/config.py
Запустить бот командой 
````
python3 bot.py
````

Для запуска бота как сервиса необходимо скопировать файл bot.service в директорию /etc/systemd/system и запустить бота командами
````
systemctl enable bot
systemctl start bot
````