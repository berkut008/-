# models/group.py
from db import db
from models.student import Student  # Добавлен импорт Student

class Group(db.Model):
    __tablename__ = 'groups'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    curator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    leader_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Связь с Student
    students = db.relationship('Student', backref='group', lazy=True)
    
    # Исправленные отношения с User
    curator = db.relationship('User', 
                             foreign_keys=[curator_id], 
                             backref='curated_groups',
                             lazy=True)
    
    leader = db.relationship('User', 
                            foreign_keys=[leader_id], 
                            backref='led_groups',  # Исправлено: led_group → led_groups
                            lazy=True)

    def __repr__(self):
        return f"<Group {self.name}>"

    @property
    def students_count(self):
        """Количество студентов в группе"""
        return len(self.students)

    @property
    def absences_count(self):
        """Общее количество пропусков в группе"""
        from models.absence import Absence
        total = 0
        for student in self.students:
            total += Absence.query.filter_by(student_id=student.id).count()
        return total

    def get_absences_by_period(self, start_date=None, end_date=None):
        """Пропуски в группе за период"""
        from models.absence import Absence
        from datetime import datetime
        
        query = Absence.query.join(Student).filter(Student.group_id == self.id)
        
        if start_date:
            query = query.filter(Absence.date >= start_date)
        if end_date:
            query = query.filter(Absence.date <= end_date)
            
        return query.all()