# create_migration.py
import os
import sys

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from sqlalchemy import text

with app.app_context():
    print("="*60)
    print("МИГРАЦИЯ БАЗЫ ДАННЫХ ДЛЯ ПРИВЯЗКИ СТАРОСТ К ГРУППАМ")
    print("="*60)
    
    # Проверяем существующие таблицы
    conn = db.engine.connect()
    
    # Проверяем структуру таблицы groups
    print("\n📊 Проверка таблицы 'groups'...")
    try:
        result = conn.execute(text("PRAGMA table_info(groups)"))
        columns = [row[1] for row in result]
        
        print(f"Найдено столбцов: {len(columns)}")
        for col in columns:
            print(f"  - {col}")
        
        # Если нет поля leader_id, добавляем его
        if 'leader_id' not in columns:
            print("\n➕ Добавляем поле leader_id в таблицу groups...")
            try:
                conn.execute(text("ALTER TABLE groups ADD COLUMN leader_id INTEGER"))
                print("✅ Поле leader_id добавлено успешно!")
            except Exception as e:
                print(f"❌ Ошибка при добавлении поля: {e}")
        else:
            print("✅ Поле leader_id уже существует!")
        
        # Проверяем наличие curator_id
        if 'curator_id' not in columns:
            print("\n➕ Добавляем поле curator_id в таблицу groups...")
            try:
                conn.execute(text("ALTER TABLE groups ADD COLUMN curator_id INTEGER"))
                print("✅ Поле curator_id добавлено успешно!")
            except Exception as e:
                print(f"❌ Ошибка при добавлении поля: {e}")
        else:
            print("✅ Поле curator_id уже существует!")
            
    except Exception as e:
        print(f"❌ Ошибка при проверке таблицы groups: {e}")
        print("Создаём таблицу groups...")
        try:
            conn.execute(text("""
                CREATE TABLE groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(100) NOT NULL UNIQUE,
                    curator_id INTEGER,
                    leader_id INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("✅ Таблица groups создана успешно!")
        except Exception as e:
            print(f"❌ Ошибка при создании таблицы: {e}")
    
    # Создаём индексы для быстрого поиска
    print("\n🔍 Создаём индексы для ускорения поиска...")
    try:
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_groups_leader_id ON groups(leader_id)"))
        print("✅ Индекс idx_groups_leader_id создан!")
    except Exception as e:
        print(f"⚠️  Ошибка создания индекса leader_id: {e}")
    
    try:
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_groups_curator_id ON groups(curator_id)"))
        print("✅ Индекс idx_groups_curator_id создан!")
    except Exception as e:
        print(f"⚠️  Ошибка создания индекса curator_id: {e}")
    
    # Проверяем таблицу users
    print("\n📊 Проверка таблицы 'users'...")
    try:
        result = conn.execute(text("PRAGMA table_info(users)"))
        columns = [row[1] for row in result]
        
        print(f"Найдено столбцов: {len(columns)}")
        
        # Проверяем необходимые поля
        required_fields = ['is_rejected', 'created_at', 'confirmed_at', 'rejected_at', 
                          'confirmed_by_id', 'rejected_by_id', 'cmk_id']
        
        for field in required_fields:
            if field not in columns:
                print(f"⚠️  Отсутствует поле: {field}")
            else:
                print(f"✅ Поле {field} присутствует")
                
    except Exception as e:
        print(f"❌ Ошибка при проверке таблицы users: {e}")
    
    conn.close()
    
    print("\n" + "="*60)
    print("МИГРАЦИЯ ЗАВЕРШЕНА!")
    print("="*60)
    print("\n🎯 Структура базы данных готова для:")
    print("   • Привязки старост к группам через leader_id")
    print("   • Привязки кураторов к группам через curator_id")
    print("   • Регистрации с выбором группы")
    print("\n✅ Теперь можно запускать приложение!")
    print("="*60)