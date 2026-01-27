from db import db

class Absence(db.Model):
    __tablename__ = 'absences'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)  # 🟢 связь с таблицей students
    date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(255))
    lessons_count = db.Column(db.Integer, default=1)

    student = db.relationship('Student', back_populates='absences')
