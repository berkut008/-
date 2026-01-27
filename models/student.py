from db import db


class Student(db.Model):
    __tablename__ = 'students'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'))
    phone = db.Column(db.String(20))

    absences = db.relationship('Absence', back_populates='student', cascade="all, delete-orphan")  # 🟢
