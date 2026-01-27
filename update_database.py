# update_database.py
from app import app, db
from sqlalchemy import text
from models.group import Group  # ДОБАВИТЬ ЭТОТ ИМПОРТ

with app.app_context():
    # Проверяем, какие столбцы уже существуют
    conn = db.engine.connect()
    
    # Получаем информацию о таблице users
    result = conn.execute(text("PRAGMA table_info(users)"))
    existing_columns = [row[1] for row in result]  # Имя столбца находится в позиции 1
    
    print("Существующие столбцы в таблице users:")
    for col in existing_columns:
        print(f"  - {col}")
    
    # Список новых столбцов, которые нужно добавить
    new_columns = [
        ('is_rejected', 'BOOLEAN DEFAULT FALSE'),
        ('created_at', 'DATETIME'),
        ('confirmed_at', 'DATETIME'),
        ('rejected_at', 'DATETIME'),
        ('confirmed_by_id', 'INTEGER'),
        ('rejected_by_id', 'INTEGER')
    ]
    
    added_count = 0
    for column_name, column_type in new_columns:
        if column_name not in existing_columns:
            print(f"\nДобавляем столбец: {column_name} ({column_type})")
            try:
                # Для SQLite ALTER TABLE ADD COLUMN
                sql = f"ALTER TABLE users ADD COLUMN {column_name} {column_type}"
                conn.execute(text(sql))
                print(f"✅ Столбец '{column_name}' добавлен успешно!")
                added_count += 1
            except Exception as e:
                print(f"❌ Ошибка при добавлении столбца '{column_name}': {e}")
    
    # Создаём таблицу audit_logs если её нет
    result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_logs'"))
    if not result.fetchone():
        print("\nСоздаём таблицу audit_logs...")
        conn.execute(text("""
            CREATE TABLE audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action VARCHAR(100),
                description TEXT,
                ip_address VARCHAR(50),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """))
        print("✅ Таблица audit_logs создана успешно!")
    
    conn.close()
    
    print(f"\n{'='*50}")
    print(f"✅ Обновление завершено! Добавлено столбцов: {added_count}")
    print("Теперь можно запускать приложение без удаления базы данных!")
    print("="*50)
    
    # ==============================================
    # ДОБАВЛЯЕМ ГРУППЫ ЕСЛИ ИХ НЕТ
    # ==============================================
    print("\n" + "="*50)
    print("ПРОВЕРКА И СОЗДАНИЕ УЧЕБНЫХ ГРУПП")
    print("="*50)
    
    # Проверяем, есть ли группы в базе
    groups_count = db.session.query(Group).count()
    print(f"Текущее количество групп в базе: {groups_count}")
    
    if groups_count == 0:
        print("Группы не найдены. Создаем тестовые группы...")
        
        # Список тестовых групп (ИЗМЕНИТЕ НА СВОИ)
        test_groups = [
            "Э-101", "Э-102", "Э-103",
            "Б-101", "Б-102", "Б-103", 
            "Ф-101", "Ф-102",
            "К-101", "К-102"
        ]
        
        for group_name in test_groups:
            # Проверяем, не существует ли уже такая группа
            existing = Group.query.filter_by(name=group_name).first()
            if not existing:
                new_group = Group(name=group_name)
                db.session.add(new_group)
                print(f"✅ Создана группа: {group_name}")
            else:
                print(f"⚠️  Группа уже существует: {group_name}")
        
        try:
            db.session.commit()
            print(f"\n✅ Создано {len(test_groups)} учебных групп")
        except Exception as e:
            db.session.rollback()
            print(f"❌ Ошибка при создании групп: {e}")
    else:
        print(f"✅ В базе уже есть {groups_count} групп. Пропускаем создание.")
    
    # Выводим список всех групп
    print("\n📋 Список всех групп в базе:")
    all_groups = Group.query.order_by(Group.name).all()
    for group in all_groups:
        leader_info = f" (Староста: {group.leader.full_name})" if group.leader else ""
        curator_info = f" (Куратор: {group.curator.full_name})" if group.curator else ""
        print(f"  • {group.name}{leader_info}{curator_info}")
    
    print("\n" + "="*50)
    print("✅ ОБНОВЛЕНИЕ БАЗЫ ДАННЫХ ЗАВЕРШЕНО!")
    print("="*50)