# models/user.py
from db import db
from flask_login import UserMixin
from datetime import datetime
from flask_bcrypt import Bcrypt

bcrypt = Bcrypt()

class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)  # Добавлен unique=True
    telegram = db.Column(db.String(100))
    role = db.Column(db.String(50), nullable=False)  # Добавлен nullable=False
    password = db.Column(db.String(255))
    is_confirmed = db.Column(db.Boolean, default=False)
    
    # Новые поля с nullable=True для обратной совместимости
    is_rejected = db.Column(db.Boolean, default=False, nullable=True)
    cmk_id = db.Column(db.Integer, db.ForeignKey('cmks.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)
    confirmed_at = db.Column(db.DateTime, nullable=True)
    rejected_at = db.Column(db.DateTime, nullable=True)
    confirmed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    rejected_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    def __init__(self, **kwargs):
        # Устанавливаем значения по умолчанию для новых полей
        kwargs.setdefault('is_rejected', False)
        kwargs.setdefault('created_at', datetime.utcnow())
        super().__init__(**kwargs)

    def set_password(self, password):
        """Устанавливает хеш пароля"""
        self.password = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        """Проверяет пароль"""
        return bcrypt.check_password_hash(self.password, password)

    # Метод для получения группы старосты
    def get_leader_group(self):
        """Возвращает группу, в которой пользователь является старостой"""
        if self.role == 'leader':
            from models.group import Group
            return Group.query.filter_by(leader_id=self.id).first()
        return None

    # Метод для получения групп куратора
    def get_curator_groups(self):
        """Возвращает группы, которые курирует пользователь"""
        if self.role == 'curator':
            from models.group import Group
            return Group.query.filter_by(curator_id=self.id).all()
        return []

    # Связи (явно определенные для ясности)
    # Уже определены через backref в модели Group:
    # - curated_groups: группы, где пользователь куратор
    # - led_groups: группы, где пользователь староста

    def __repr__(self):
        return f"<User {self.full_name}>"