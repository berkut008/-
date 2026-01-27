from db import db

class Cmk(db.Model):
    __tablename__ = 'cmks'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)

    # связь с кураторами
    curators = db.relationship('User', backref='cmk', lazy=True, foreign_keys='User.cmk_id')


    def __repr__(self):
        return f"<CMK {self.name}>"
