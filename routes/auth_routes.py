# routes/auth_routes.py
from flask_login import logout_user
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from db import db
from models.user import User
from models.group import Group
from flask_bcrypt import Bcrypt
from flask_login import login_user
from datetime import datetime

bcrypt = Bcrypt()
auth_bp = Blueprint('auth', __name__)

# Безопасный доступ к атрибутам пользователя
def safe_getattr(user, attr, default=None):
    """Безопасно получаем атрибут пользователя"""
    try:
        return getattr(user, attr, default)
    except:
        return default

# 🔹 Регистрация старосты (студента) - ИСПРАВЛЕННЫЙ ВЕРСИЯ
@auth_bp.route('/register/student', methods=['GET', 'POST'])
def register_student():
    if request.method == 'GET':
        # Получаем список групп для выбора
        groups = Group.query.order_by(Group.name).all()
        return render_template('register_student.html', groups=groups)
    
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        phone = request.form.get('phone')
        telegram = request.form.get('telegram', '')
        password = request.form.get('password')
        group_id = request.form.get('group_id')  # Новое поле!

        # Проверяем, не занят ли телефон
        existing_user = User.query.filter_by(phone=phone).first()
        if existing_user:
            flash('❌ Пользователь с таким номером телефона уже существует.', 'danger')
            groups = Group.query.order_by(Group.name).all()
            return render_template('register_student.html', groups=groups)

        # Проверяем, существует ли группа
        group = Group.query.get(group_id)
        if not group:
            flash('❌ Выбранная группа не существует.', 'danger')
            groups = Group.query.order_by(Group.name).all()
            return render_template('register_student.html', groups=groups)

        # Проверяем, нет ли уже старосты в этой группе
        existing_leader = Group.query.filter_by(leader_id=group_id).first()
        if existing_leader and existing_leader.leader_id:
            flash('❌ В этой группе уже есть староста.', 'danger')
            groups = Group.query.order_by(Group.name).all()
            return render_template('register_student.html', groups=groups)

        user = User(
            full_name=full_name, 
            phone=phone, 
            telegram=telegram if telegram else None,
            role='leader', 
            password=bcrypt.generate_password_hash(password).decode('utf-8'),
            is_confirmed=False,
            is_rejected=False
        )
        
        db.session.add(user)
        db.session.flush()  # Получаем ID пользователя
        
        # Привязываем старосту к группе
        if group:
            group.leader_id = user.id
        
        db.session.commit()
        
        flash('✅ Регистрация прошла успешно! Ожидайте подтверждения администратора.', 'success')
        return redirect(url_for('auth.login'))

    groups = Group.query.order_by(Group.name).all()
    return render_template('register_student.html', groups=groups)

# 🔹 Регистрация куратора - ИСПРАВЛЕННЫЙ ВЕРСИЯ
@auth_bp.route('/register/curator', methods=['GET', 'POST'])
def register_curator():
    if request.method == 'GET':
        # Получаем список групп для выбора
        groups = Group.query.order_by(Group.name).all()
        return render_template('register_curator.html', groups=groups)
    
    if request.method == 'POST':
        full_name = request.form['full_name']
        phone = request.form['phone']
        telegram = request.form['telegram']
        password = request.form['password']
        group_ids = request.form.getlist('groups')  # Список групп

        # Проверяем, не занят ли телефон
        existing_user = User.query.filter_by(phone=phone).first()
        if existing_user:
            flash('❌ Пользователь с таким номером телефона уже существует.', 'danger')
            groups = Group.query.order_by(Group.name).all()
            return render_template('register_curator.html', groups=groups)

        user = User(
            full_name=full_name, 
            phone=phone, 
            telegram=telegram, 
            role='curator', 
            password=bcrypt.generate_password_hash(password).decode('utf-8'),
            is_confirmed=False,
            is_rejected=False
        )
        
        db.session.add(user)
        db.session.flush()  # Получаем ID пользователя
        
        # Привязываем куратора к выбранным группам
        for group_id in group_ids:
            group = Group.query.get(group_id)
            if group:
                group.curator_id = user.id
        
        db.session.commit()
        
        flash('✅ Куратор зарегистрирован! Ожидайте подтверждения администратора.', 'success')
        return redirect(url_for('auth.login'))

    groups = Group.query.order_by(Group.name).all()
    return render_template('register_curator.html', groups=groups)

# 🔹 Вход в систему (защищённая версия) - БЕЗ ИЗМЕНЕНИЙ
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phone = request.form.get("username")
        password = request.form.get("password")

        user = User.query.filter_by(phone=phone).first()

        if user and bcrypt.check_password_hash(user.password, password):
            # Безопасная проверка статуса пользователя
            is_rejected = safe_getattr(user, 'is_rejected', False)
            is_confirmed = safe_getattr(user, 'is_confirmed', False)
            
            if is_rejected:
                flash('❌ Ваша заявка была отклонена администратором.', 'danger')
                return redirect(url_for('auth.login'))
                
            if user.role in ['leader', 'curator'] and not is_confirmed:
                flash('⏳ Ваш аккаунт ожидает подтверждения администратора.', 'warning')
                return redirect(url_for('auth.login'))
                
            login_user(user)
            flash("✅ Добро пожаловать!", "success")
            return redirect(url_for('dashboard.index'))
        else:
            flash("❌ Неверный телефон или пароль", "danger")

    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    logout_user()
    flash('Вы вышли из системы.', 'info')
    return redirect(url_for('auth.login'))

# ==========================================
# ✅ Регистрация администратора (скрытая страница) - БЕЗ ИЗМЕНЕНИЙ
# ==========================================
@auth_bp.route('/register_admin', methods=['GET', 'POST'])
def register_admin():
    # 🔒 Секретный ключ
    secret_key = request.args.get('key')
    if secret_key != "rinx2025":
        abort(403)

    if request.method == 'POST':
        full_name = request.form.get('full_name')
        phone = request.form.get('phone')
        password = request.form.get('password')

        # Проверка на уникальность
        if User.query.filter_by(phone=phone).first():
            flash('Пользователь с таким номером уже существует!', 'danger')
            return redirect(url_for('auth.register_admin', key=secret_key))

        # Создаём админа
        new_admin = User(
            full_name=full_name,
            phone=phone,
            password=bcrypt.generate_password_hash(password).decode('utf-8'),
            role='admin',
            is_confirmed=True,
            is_rejected=False
        )
        db.session.add(new_admin)
        db.session.commit()
        flash('✅ Администратор успешно создан!', 'success')
        return redirect(url_for('auth.login'))

    return render_template('register_admin.html')