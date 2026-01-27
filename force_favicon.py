#!/usr/bin/env python3
"""
Скрипт для принудительной установки favicon
Запустите этот скрипт и откройте test_favicon.html
"""
import os
from flask import Flask, send_from_directory

app = Flask(__name__)

# Самый простой маршрут для favicon
@app.route('/favicon.ico')
def favicon():
    return send_from_directory('.', 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/')
def index():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Тест Favicon</title>
        <link rel="icon" href="/favicon.ico" type="image/x-icon">
    </head>
    <body>
        <h1>Тестируем favicon!</h1>
        <p>Если вы видите иконку выше - всё работает!</p>
        <p>Затем используйте этот же код в своем проекте.</p>
    </body>
    </html>
    '''

if __name__ == '__main__':
    app.run(debug=True, port=5050)  # другой порт, чтобы не конфликтовал