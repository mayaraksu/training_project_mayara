from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Admin(db.Model):
    __tablename__ = "admins"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class Customer(db.Model):
    __tablename__ = "customers"
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # helpers
    from werkzeug.security import generate_password_hash, check_password_hash
    def set_password(self, raw_password: str):
        self.password_hash = self.generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return self.check_password_hash(self.password_hash, raw_password)


class RequestModel(db.Model):
    __tablename__ = "requests"
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"))
    title = db.Column(db.String(200))
    district = db.Column(db.String(100))
    request_type = db.Column(db.String(100))
    status = db.Column(db.String(20), default="pending")  # pending/approved/rejected/under_review
    notes = db.Column(db.Text)
    tracking_code = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)