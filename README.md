# Телеграмм бот регистрации на турнире

## Начало работы


Установка bot-а
````
cd /opt
git clone https://github.com/m-larin/tbot-ttclub-etalon.git
cd tbot-ttclub-etalon
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp instance/config.py.example instance/config.py 
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
