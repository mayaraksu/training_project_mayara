# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from datetime import datetime
from functools import wraps
from collections import Counter

from flask import Flask, render_template, request, redirect, url_for,session, flash
from flask_sqlalchemy import SQLAlchemy
# ---------------- الإعدادات العامة ----------------
THEME = {"brand": "#1f6b57"}  # لون العلامة

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-me-strong-key"

# مسار قاعدة البيانات داخل مجلد instance
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_DIR = os.path.join(BASE_DIR, "instance")
DB_PATH = os.path.join(DB_DIR, "water_quality.db")
os.makedirs(DB_DIR, exist_ok=True)

app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ---------------- الموديلات ----------------
class AppUser(db.Model):
    __tablename__ = "app_users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AppRequest(db.Model):
    __tablename__ = "app_requests"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    req_type = db.Column(db.String(120), nullable=False)  # نوع الطلب
    req_status = db.Column(db.String(50), nullable=False, default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("app_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    user = db.relationship("AppUser", backref="requests")

# ---------------- وظائف مساعدة ----------------
def ensure_db():
    """إنشاء الجداول + إضافة مستخدم/بيانات تجريبية لو كانت القاعدة جديدة."""
    first_time = not os.path.exists(DB_PATH)
    db.create_all()
    if first_time:
        # مستخدم تجريبي
        u = AppUser(name="مدير النظام", email="admin@example.com", password="1234")
        db.session.add(u)
        # 4 طلبات بأربع حالات
        samples = [
            AppRequest(title="تقرير لجنة المياه - حي الندى", req_type="لجنة المياه", req_status="under_review", user=u),
            AppRequest(title="تحليل المياه - بئر 18", req_type="تحليل المياه", req_status="approved", user=u),
            AppRequest(title="اعتراض نتيجة التحليل", req_type="تحليل المياه", req_status="rejected", user=u),
            AppRequest(title="طلب فحص بئر مزرعة الشمال", req_type="فحص المياه", req_status="pending", user=u),
        ]
        db.session.add_all(samples)
        db.session.commit()

def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if "uid" not in session:
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapper

@app.context_processor
def inject_now():
    return {"now": datetime.utcnow, "theme": THEME}

# ---------------- السبلاش ----------------
@app.route("/")
def splash():
    # لو مسجلة دخول روّح للهوم
    if session.get("uid"):
        return redirect(url_for("home"))
    return render_template("splash.html", title="")

# ---------------- تسجيل الدخول/الخروج ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()
        u = AppUser.query.filter_by(email=email, password=password).first()
        if u:
            session["uid"] = u.id
            session["uname"] = u.name
            flash("تم تسجيل دخولك", "ok")
            return redirect(url_for("home"))
        flash("بيانات الدخول غير صحيحة", "bad")
        return redirect(url_for("login"))
    return render_template("login.html", title="تسجيل الدخول", hide_nav=True)

@app.route("/logout")
def logout():
    session.clear()
    flash("تم تسجيل الخروج", "ok")
    return redirect(url_for("login"))

# ---------------- الرئيسية ----------------
@app.route("/home")
@login_required
def home():
    # إحصائيات الحالات
    qset = AppRequest.query.order_by(AppRequest.created_at.desc())
    items = qset.all()
    c = Counter([r.req_status for r in items])
    counters = {
        "total": len(items),
        "pending": c.get("pending", 0),
        "under_review": c.get("under_review", 0),
        "approved": c.get("approved", 0),
        "rejected": c.get("rejected", 0),
    }

    # بيانات الأشهر (تجريبية صفرية إن ما فيه باك إند يرسلها)
    monthly_labels = [str(i) for i in range(1, 13)]
    monthly_values = [0]*12  # غيّريها لاحقًا لو صار عندك بيانات شهرية

    return render_template(
        "home.html",
        title="الرئيسية",
        counters=counters,
        items=items,
        monthly_labels=monthly_labels,
        monthly_values=monthly_values,
    )

# ---------------- صفحات إضافية (اختياري) ----------------
@app.route("/archive")
@login_required
def archive():
    items = AppRequest.query.order_by(AppRequest.created_at.desc()).all()
    return render_template("archive.html", title="الأرشيف", items=items)

@app.route("/status")
def status_page():
    # القوائم الثابتة لخيارات الفلاتر
    req_types  = ["تحليل المياه", "فحص المياه", "تقرير لجنة المياه"]
    statuses   = [
        ("",             "الكل"),
        ("pending",      "معلّقة"),
        ("under_review", "قيد المراجعة"),
        ("approved",     "مقبولة"),
        ("rejected",     "مرفوضة"),
    ]

    # خرائط للعرض و الـ CSS بدون if/elif داخل القالب
    status_label = {
        "pending":      "معلّقة",
        "under_review": "قيد المراجعة",
        "approved":     "مقبولة",
        "rejected":     "مرفوضة",
    }
    status_class = {
        "pending":      "badge pending",
        "under_review": "badge under_review",
        "approved":     "badge approved",
        "rejected":     "badge rejected",
    }

    # قراءة فلاتر الاستعلام
    s = (request.args.get("status") or "").strip()
    t = (request.args.get("type")   or "").strip()
    q = (request.args.get("q")      or "").strip()

    # بناء الاستعلام
    query = AppRequest.query
    if s:
        query = query.filter_by(req_status=s)
    if t:
        query = query.filter_by(req_type=t)
    if q:
        query = query.filter(AppRequest.title.contains(f"%{q}%"))

    items = query.order_by(AppRequest.created_at.desc()).all()

    # تجهيز صفوف جاهزة للعرض (بدون شروط في القالب)
    rows = []
    for r in items:
        rows.append({
            "title":        r.title,
            "req_type":     r.req_type,
            "status_key":   r.req_status,
            "status_label": status_label.get(r.req_status, "غير معروفة"),
            "status_class": status_class.get(r.req_status, "badge"),
            "created_at":   r.created_at,
        })

    return render_template(
        "status.html",
        title="حالة الطلب",
        req_types=req_types,
        selected_status=s,
        selected_type=t,
        q=q,
        rows=rows
    )


# ---------------- إضافة طلب ----------------
@app.route("/add", methods=["GET", "POST"], endpoint="add_request")
@login_required
def add_request():
    # القوائم المعروضة في الفorm
    req_types = [
        "تحليل المياه",
        "تقرير لجنة المياه",
        "طلب فحص المياه",
        "اعتراض نتيجة التحليل",
    ]
    districts = ["الريان", "الندى", "الياسمين", "الملقى", "أخرى"]

    if request.method == "POST":
        # قراءات الـ form
        req_type = (request.form.get("req_type") or "").strip()
        district = (request.form.get("district") or "").strip()
        district_other = (request.form.get("district_other") or "").strip()
        salt_cat = (request.form.get("salt_cat") or "").strip()
        details = (request.form.get("details") or "").strip()

        # إلزاميات بسيطة
        if not req_type or not district:
            flash("الرجاء اختيار نوع الطلب والحي.", "bad")
            return redirect(url_for("add_request"))

        # لو اختارت "أخرى" استخدم النص المكتوب
        district_final = district_other.strip() if district == "أخرى" and district_other else district

        # عنوان تلقائي إذا ما وصل عنوان مخفي من الواجهة
        title = (request.form.get("title") or "").strip()
        if not title:
            title = f"{req_type} - حي {district_final}" if req_type and district_final else (req_type or district_final or "طلب")

        # إنشاء السجل
        new_r = AppRequest(
            title=title,
            req_type=req_type,
            req_status="pending",
            user_id=session.get("uid"),
        )

        # حفظ الحقول الإضافية فقط لو الأعمدة موجودة في الموديل
        optional_fields = {
            "district": district_final,
            "salt_cat": salt_cat or None,
            "details": details or None,
        }
        for col, val in optional_fields.items():
            if hasattr(AppRequest, col):
                setattr(new_r, col, val)

        # حفظ في الداتابيس
        db.session.add(new_r)
        db.session.commit()

        flash("تمت إضافة الطلب بنجاح.", "ok")
        return redirect(url_for("home"))

    # GET
    return render_template("add.html", title="إضافة طلب", req_types=req_types, districts=districts)
# ---------------- تشغيل ----------------
if __name__ == "__main__":
    with app.app_context():
        ensure_db()
    app.run(host="127.0.0.1", port=5000, debug=True)

