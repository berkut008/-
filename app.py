from dotenv import load_dotenv
load_dotenv()
from flask import Flask, redirect, url_for, send_from_directory
from flask_login import LoginManager
from db import db
from routes.auth_routes import auth_bp
from routes.dashboard_routes import dashboard_bp
from config import Config
from models.user import User
from models.group import Group
from models.student import Student
from models.absence import Absence
from models.cmk import Cmk
from models.audit_log import AuditLog
from sqlalchemy import inspect, text
import sys
import os

# ДОБАВЛЕНО: импорт blueprint Ollama
from routes.ollama_routes import ollama_bp

# === Создание приложения ===
app = Flask(__name__)
app.config.from_object(Config)

# === Инициализация базы ===
db.init_app(app)

# === Настройка Flask-Login ===
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except Exception as e:
        app.logger.error(f"Ошибка при загрузке пользователя {user_id}: {e}")
        return None

# === Регистрация блюпринтов ===
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(dashboard_bp, url_prefix='/dashboard')

# ДОБАВЛЕНО: регистрация Ollama blueprint
app.register_blueprint(ollama_bp)

# === Главная страница ===
@app.route('/')
def home():
    return redirect(url_for('auth.login'))

# === Favicon ===
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )

# === Проверка и обновление структуры БД ===
def check_and_update_database():
    try:
        with app.app_context():
            inspector = inspect(db.engine)
            
            # Проверяем существующие таблицы
            tables = inspector.get_table_names()
            print("\n" + "="*60)
            print("ПРОВЕРКА СТРУКТУРЫ БАЗЫ ДАННЫХ")
            print("="*60)
            
            if 'users' in tables:
                columns = [col['name'] for col in inspector.get_columns('users')]
                print(f"Таблица 'users' содержит {len(columns)} столбцов.")
                
                # Проверяем наличие критических полей
                critical_columns = ['id', 'full_name', 'phone', 'role', 'password']
                missing_critical = [col for col in critical_columns if col not in columns]
                
                if missing_critical:
                    print(f"⚠️  Отсутствуют критические столбцы: {missing_critical}")
                    print("Рекомендуется удалить базу данных и создать заново.")
                else:
                    print("✅ Структура таблицы 'users' корректна!")
            
            if 'groups' in tables:
                columns = [col['name'] for col in inspector.get_columns('groups')]
                print(f"\nТаблица 'groups' содержит {len(columns)} столбцов.")
                
                # Проверяем наличие поля leader_id
                if 'leader_id' not in columns:
                    print("⚠️  Отсутствует поле 'leader_id' в таблице 'groups'")
                    print("Запустите create_migration.py для добавления поля")
                else:
                    print("✅ Поле 'leader_id' присутствует!")
    
    except Exception as e:
        print(f"❌ Ошибка при проверке базы данных: {e}")
        print("Создаём таблицы заново...")
        db.create_all()
        print("✅ Таблицы созданы успешно!")

# === Функция создания групп по умолчанию ===
def init_default_groups():
    """Создает группы по умолчанию если база пустая"""
    with app.app_context():
        if Group.query.count() == 0:
            print("Создаем группы по умолчанию...")
            default_groups = ["Э-101", "Э-102", "Б-101", "Б-102", "Ф-101"]
            
            for name in default_groups:
                group = Group(name=name)
                db.session.add(group)
            
            try:
                db.session.commit()
                print(f"✅ Создано {len(default_groups)} групп")
            except Exception as e:
                db.session.rollback()
                print(f"❌ Ошибка при создании групп: {e}")
        else:
            print(f"✅ В базе уже есть {Group.query.count()} групп")

# === Инициализация приложения ===
def init_app():
    """Инициализация приложения с созданием таблиц и групп"""
    with app.app_context():
        # Создаем все таблицы если их нет
        try:
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            
            if not tables:
                print("Создаем таблицы базы данных...")
                db.create_all()
                print("✅ Таблицы созданы успешно!")
            else:
                print(f"✅ База данных уже содержит {len(tables)} таблиц")
            
            # Создаем группы по умолчанию
            init_default_groups()
            
        except Exception as e:
            print(f"❌ Ошибка инициализации: {e}")
            # Попробуем создать таблицы принудительно
            db.create_all()
            print("✅ Таблицы созданы принудительно")
            init_default_groups()

# === Запуск приложения ===
if __name__ == '__main__':
    # Проверяем аргументы командной строки
    if len(sys.argv) > 1 and sys.argv[1] == '--check-db':
        check_and_update_database()
    elif len(sys.argv) > 1 and sys.argv[1] == '--init':
        init_app()
    else:
        # Автоматическая инициализация при запуске
        init_app()
        app.run(debug=True, host='0.0.0.0', port=5000)