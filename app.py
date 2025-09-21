# -*- coding: utf-8 -*-
<<<<<<< HEAD
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Blueprint,current_app
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.inspection import inspect
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, Admin, Customer, RequestModel
from functools import wraps
import re, os
from datetime import datetime ,timedelta , time
from sqlalchemy.inspection import inspect
from sqlalchemy import or_ , text , func , and_

# ================= إعداد التطبيق =================
app = Flask(__name__)
app.config["SECRET_KEY"] = "change-me-123"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = "CHANGE_ME_SECRET_KEY"
db.init_app(app)


# ================= Regex =================
PHONE_RE = re.compile(r"^\d{10}$")
PWD_RE   = re.compile(r"^(?=.*[A-Z])[A-Za-z0-9]{6,}$")

# ================= Blueprint =================
customers_bp = Blueprint("customers", __name__)
# ===================== أدوات مساعدة =====================
# ====== one-time patch for missing columns in sqlite ======
def _add_column_if_missing(table: str, column: str, ddl: str) -> None:
    """
    يضيف عمودًا إلى جدول SQLite إن كان غير موجود.
    - table: اسم الجدول.
    - column: اسم العمود المراد التأكد منه.
    - ddl: جملة ALTER TABLE المناسبة لإضافة العمود.
    """
    # نستخدم اتصالًا على مستوى المحرك لضمان تنفيذ الـ DDL
    with db.engine.begin() as conn:
        # PRAGMA table_info يعيد: (cid, name, type, notnull, dflt_value, pk)
        cols = [row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")]
        if column not in cols:
            conn.exec_driver_sql(ddl)

with app.app_context():
    # إنشاء الجداول إن لم تكن موجودة
    db.create_all()

    # ترقيع جدول customers
    _add_column_if_missing(
        "customers", "created_at",
        "ALTER TABLE customers ADD COLUMN created_at DATETIME"
    )

    # ترقيع جدول requests
    _add_column_if_missing(
        "requests", "title",
        "ALTER TABLE requests ADD COLUMN title VARCHAR(200)"
    )
    _add_column_if_missing(
        "requests", "status",
        "ALTER TABLE requests ADD COLUMN status VARCHAR(20) DEFAULT 'pending'"
    )
    _add_column_if_missing(
        "requests", "tracking_code",
        "ALTER TABLE requests ADD COLUMN tracking_code VARCHAR(50)"
    )
    _add_column_if_missing(
        "requests", "created_at",
        "ALTER TABLE requests ADD COLUMN created_at DATETIME"
    )

# ====== مساعدات عامة ======
def notifications_data(cid=None):
    """
    ترجع هيكل إشعارات موحّد:
      count: عدد الإشعارات
      list:  قائمة عناصر: {title, time, text}
    """
    # تقدر لاحقاً تربطها بجدول حقيقي
    demo = [
        {"title": "تم استلام طلبك", "time": "قبل دقيقة", "text": "رقم التتبع #1005"},
        {"title": "تم تحديث الحالة", "time": "اليوم", "text": "طلب #1002 تحت المراجعة"},
    ]
    return {"count": len(demo), "list": demo}

# يمرّر البيانات الافتراضية لكل القوالب
@app.context_processor
def inject_defaults():
    role = "customer"
    cid  = session.get("customer_id")
    return {
        "role": role,
        # مهم: نمرر (نتيجة) الدالة، مو مرجع الدالة
        "notifications": notifications_data(cid)
    }

def _require_customer() -> bool:
    """
    تحقّق سريع أن العميل مسجّل دخول.
    """
    return "customer_id" in session
# ====== end patch ====
def _status_col(Model):
    # يحاول إيجاد اسم عمود الحالة الموجود فعلاً في الموديل
    candidates = ["status", "state", "request_status", "case_status", "status_ar"]
    cols = {c.key for c in inspect(Model).columns}
    for name in candidates:
        if name in cols:
            return getattr(Model, name)
    return None

def counts_for_customer(cid: int):
    total = RequestModel.query.filter_by(customer_id=cid).count()
    col = _status_col(RequestModel)
    if not col:
        return total, 0, 0, 0
    PENDING  = ["pending", "قيد المراجعة", "قيد المراجعه"]
    APPROVED = ["approved", "مقبولة", "مقبول"]
    REJECTED = ["rejected", "مرفوضة", "مرفوض"]
    base = RequestModel.query.filter_by(customer_id=cid)
    return (
        total,
        base.filter(col.in_(PENDING)).count(),
        base.filter(col.in_(APPROVED)).count(),
        base.filter(col.in_(REJECTED)).count()
)

def customer_login_required(view):
    @wraps(view)
    def _wrap(*args, **kwargs):
        if session.get("role") != "customer" or "customer_id" not in session:
            return redirect(url_for("customer_login"))
        return view(*args, **kwargs)
    return _wrap

def ensure_db():
    with app.app_context():
        db.create_all()
        email = "admin@example.com"
        if not Admin.query.filter_by(email=email).first():
            a = Admin(name="المسؤول", email=email,
                      password_hash=generate_password_hash("123456"))
            db.session.add(a)
            db.session.commit()
            print("✅ Admin created:", email, "/ 123456")
        else:
            print("ℹ️ Admin already exists.")

# ديكوريتر تأكيد دخول الأدمن
def admin_login_required(view):
    @wraps(view)
    def _wrap(*args, **kwargs):
        if session.get("role") != "admin" or "admin_id" not in session:
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return _wrap

#========================

# ===== Context واحد يحقن المتغيرات للقوالب =====

# إحصائيات سريعة
def counters_q():
    total    = RequestModel.query.count()
    approved = RequestModel.query.filter_by(Request_status="approved").count()
    pending  = RequestModel.query.filter_by(Request_status="pending").count()
    rejected = RequestModel.query.filter_by(Request_status="rejected").count()
    return dict(total=total, approved=approved, pending=pending, rejected=rejected)

def monthly_series():
    rows = (
        db.session.query(
            db.extract('year',  RequestModel.created_at).label('y'),
            db.extract('month', RequestModel.created_at).label('m'),
            db.func.count(RequestModel.id)
        )
        .group_by('y', 'm')
        .order_by('y', 'm')
        .all()
    )
    labels, data = [], []
    for y, m, c in rows:
        labels.append(f"{int(y):04d}-{int(m):02d}")
        data.append(int(c))
    return labels, data



def _require_customer():
    """حماية صفحات العميل: لو ما فيه جلسة يرجع للّوج إن."""
    if "customer_id" not in session:
        flash("الرجاء تسجيل الدخول أولاً.", "warn")
        return False
    return True

def _generate_tracking_code(req_id: int) -> str:
    """كود تتبّع بسيط: WT + رقم مُصفّر (مثلاً WT0012)."""
    return f"WT{req_id:04d}"

def _next_tracking_code():
    last_id = db.session.query(func.max(RequestModel.id)).scalar() or 0
    return f"WT-{last_id + 1:04d}"

# ===================== الراوتات العامة =====================
@app.route("/")
def splash():
    return render_template("splash.html", title="بدء", hide_nav=True,hide_logo=True)

@app.route("/auth")
def auth_choose():
    return render_template("auth_choose.html", title="اختيار نوع الدخول", hide_nav=True, hide_logo=True)


# ===================== مسؤولين =====================
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    title = "دخول المسؤولين"

    if request.method == "POST":
        # 1) جمع المدخلات بأمان
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()

        # 2) تحقق من الفراغ
        if not email or not password:
            flash("الرجاء إدخال البريد وكلمة المرور.", "err")
            return render_template("admin_login.html",
                                   title=title, hide_nav=True,
                                   email=email)

        # 3) جلب المستخدم والتحقق من كلمة المرور
        admin = Admin.query.filter_by(email=email).first()
        if not admin or not check_password_hash(admin.password_hash, password):
            flash("بيانات الدخول غير صحيحة.", "err")
            return render_template("admin_login.html",
                                   title=title, hide_nav=True,
                                   email=email)

        # 4) نجاح — إعداد الجلسة
        session.clear()
        session["role"] = "admin"
        session["admin_id"] = admin.id
        session["admin_name"] = getattr(admin, "name", "مسؤول")
        return render_template("admin_login.html",
                               title=title, hide_nav=True,
                               success_redirect=url_for("admin_home"))

    # GET
    return render_template("admin_login.html", title=title, hide_nav=True)
#===============================================
@app.route("/admin")
@app.route("/admin/dashboard")
@admin_login_required
def admin_dashboard():
    cnt = counters_q()
    labels, data = monthly_series()
    return render_template(
        "admin_dashboard.html",
        title="الرئيسية",
        counters=cnt,
        chart_labels=labels,
        chart_data=data)

@app.route("/admin/manage")
@admin_login_required
def admin_manage():
    pending = (
        RequestModel.query
        .filter_by(Request_status="pending")
        .order_by(RequestModel.created_at.desc())
        .all()
    )
    return render_template(
        "admin_manage.html",
        title="إدارة الطلبات",
        pending=pending
    )

@app.route("/admin/archive")
@admin_login_required
def admin_archive():
    archived = (
        RequestModel.query
        .filter(RequestModel.Request_status.in_(["approved", "rejected"]))
        .order_by(RequestModel.created_at.desc())
        .all()
    )
    return render_template("admin_archive.html", title="الأرشيف", requests=archived)

@app.route("/admin/home")
@admin_login_required
def admin_home():
    return render_template("admin_home.html", title="لوحة التحكم", hide_nav=False)

# ====== تسجيل خروج المسؤول ======
@app.route("/admin/logout")
@admin_login_required
def admin_logout():
    session.clear()
    flash("تم تسجيل الخروج.", "ok")
    return redirect(url_for("admin_login"))

# API: قبول طلب
@app.post("/admin/requests/<int:req_id>/approve")
@admin_login_required
def api_approve(req_id):
    r = RequestModel.query.get_or_404(req_id)
    r.Request_status = "approved"
    r.Rejected_reason = None
    db.session.commit()
    return jsonify({"ok": True, "status": r.Request_status})

@app.post("/admin/requests/<int:req_id>/reject")
@admin_login_required
def api_reject(req_id):
    reason = (request.json or {}).get("reason", "").strip()
    if not reason:
        return jsonify({"ok": False, "error": "سبب الرفض مطلوب"}), 400
    r = RequestModel.query.get_or_404(req_id)
    r.Request_status = "rejected"
    r.Rejected_reason = reason
    db.session.commit()
    return jsonify({"ok": True, "status": r.Request_status})

# ===================== العملاء =====================
@app.route("/customer/login", methods=["GET", "POST"])
def customer_login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()
        if not email or not password:
            flash("الرجاء إدخال البريد وكلمة المرور.", "err")
            return redirect(url_for("customer_login"))

        user = Customer.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash("البريد أو كلمة المرور غير صحيحة.", "err")
            return redirect(url_for("customer_login"))

        session.clear()
        session["customer_id"] = user.id
        session["customer_name"] = user.full_name
        flash("تم تسجيل الدخول بنجاح.", "ok")
        return redirect(url_for("customer_home"))

    return render_template("login_customer.html", body_class="auth-login-page")

@app.route("/customer/signup", methods=["GET", "POST"])
def customer_signup():
    if request.method == "POST":
        full_name = (request.form.get("full_name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()
        confirm = (request.form.get("confirm_password") or "").strip()

        if not full_name or not email or not password or not confirm:
            flash("يجب تعبئة جميع الحقول.", "err")
            return redirect(url_for("customer_signup"))
        if password != confirm:
            flash("تأكيد كلمة المرور غير مطابق.", "err")
            return redirect(url_for("customer_signup"))
        if Customer.query.filter_by(email=email).first():
            flash("هذا البريد مسجل مسبقاً.", "err")
            return redirect(url_for("customer_signup"))

        user = Customer(full_name=full_name, email=email)
        user.password_hash = generate_password_hash(password)
        db.session.add(user)
        db.session.commit()

        flash("تم إنشاء الحساب بنجاح، يمكنك تسجيل الدخول الآن.", "ok")
        return redirect(url_for("customer_login"))

    return render_template("signup_customer.html", body_class="auth-signup-page")

# ====== الرئيسية (لوحة العميل) ======
@app.route("/customer/home")
def customer_home():
    # تأكد أن المستخدم مسجّل دخول
    if "customer_id" not in session:
        return redirect(url_for("customer_login"))

    cid = session["customer_id"]

    # القيم الافتراضية
    counts = {"pending": 0, "under_review": 0, "approved": 0, "rejected": 0, "total": 0}

    # إجمالي الحالات حسب حالة الطلب
    rows = (
        db.session.query(RequestModel.status, func.count(RequestModel.id))
        .filter(RequestModel.customer_id == cid)
        .group_by(RequestModel.status)
        .all()
    )

    for st, n in rows:
        key = (st or "").strip().lower()
        if key in counts:
            counts[key] = n

    counts["total"] = counts["pending"] + counts["under_review"] + counts["approved"] + counts["rejected"]

    # لاحظ: الاستدعاء الصحيح بدون template_name_or_list:
    return render_template("customer_home.html", counts=counts, body_class="customer-home-page")

# ====== إضافة طلب جديد ======
@app.route("/customer/request/new", methods=["GET", "POST"])
def customer_request_new():
    if not _require_customer():
        return redirect(url_for("customer_login"))

    if request.method == "POST":
        title     = (request.form.get("title") or "").strip()
        district  = (request.form.get("district") or "").strip()
        # دعم القيمتين: other أو "أخرى"
        if district.lower() == "other" or district == "أخرى":
            district = (request.form.get("district_other") or "").strip()
        req_type  = (request.form.get("request_type") or "").strip()
        notes     = (request.form.get("notes") or "").strip()

        if not title or not district or not req_type:
            msg = "فضلاً أكمل الحقول المطلوبة."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify(success=False, message=msg), 400
            flash(msg, "danger")
            return redirect(url_for("customer_request_new"))

        r = RequestModel(
            customer_id = session["customer_id"],
            title       = title,
            district    = district,
            request_type= req_type,
            notes       = notes,
            status      = "pending",
            tracking_code = _next_tracking_code(),
            created_at  = datetime.utcnow(),
        )
        db.session.add(r)
        db.session.commit()

        msg = f"تم حفظ طلبك بنجاح، رقم الطلب #{r.tracking_code}"
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or \
           "application/json" in (request.headers.get("Accept") or ""):
            return jsonify(success=True, message=msg)
        flash(msg, "success")
        return redirect(url_for("customer_home"))

    return render_template(
        "customer_request_new.html",
        notifications=notifications_data(session.get("customer_id")),
    )

# ====== الاستعلام عن حالة الطلب ======
@app.route("/customer/requests", methods=["GET", "POST"])
def customer_requests_status():
    if not _require_customer():
        return redirect(url_for("customer_login"))

    cid = session.get("customer_id")

    # نجمع فلاتر البحث من GET أو POST
    v = request.values  # يدعم الاثنين
    code   = (v.get("tracking_code") or "").strip()
    title  = (v.get("title") or "").strip()
    dist   = (v.get("request_district") or "").strip()
    rtype  = (v.get("request_type") or "").strip()
    stat   = (v.get("request_status") or "").strip()
    date_s = (v.get("request_date") or "").strip()     # yyyy-mm-dd
    time_s = (v.get("request_time") or "").strip()     # HH:MM (اختياري)

    q = RequestModel.query.filter_by(customer_id=cid)

    if code:
        q = q.filter(or_(RequestModel.tracking_code == code,
                         RequestModel.id == code))
    if title:
        q = q.filter(RequestModel.title.ilike(f"%{title}%"))
    if dist:
        q = q.filter(RequestModel.district == dist)
    if rtype:
        q = q.filter(RequestModel.request_type == rtype)
    if stat:
        q = q.filter(RequestModel.status == stat)

    # تصفية بالتاريخ (+ ساعة اختيارية)
    try:
        if date_s:
            day = datetime.strptime(date_s, "%Y-%m-%d").date()
            if time_s:
                hh, mm = map(int, time_s.split(":"))
                start_dt = datetime.combine(day, time(hh, mm))
                end_dt   = start_dt + timedelta(minutes=59, seconds=59)
            else:
                start_dt = datetime.combine(day, time.min)
                end_dt   = datetime.combine(day, time.max)

            q = q.filter(and_(RequestModel.created_at >= start_dt,
                              RequestModel.created_at <= end_dt))
    except Exception:
        # نتجاهل فورمات خاطئ بدل ما نكسر الصفحة
        pass

    result = q.order_by(RequestModel.created_at.desc()).all()

    return render_template(
        "customer_requests_status.html",
        result=result,
        # القيم المُختارة نرجعها عشان تظل في الفورم
        f_tracking_code=code, f_title=title, f_dist=dist,
        f_rtype=rtype, f_stat=stat, f_date=date_s, f_time=time_s,
        body_class="customer-shell",
        notifications=notifications_data(session.get("customer_id")),
    )

@app.route("/customer/archive")
def customer_archive():
    if not _require_customer():
        return redirect(url_for("customer_login"))

    cid = session.get("customer_id")
    rows = (
        RequestModel.query
        .filter_by(customer_id=cid)
        .order_by(RequestModel.created_at.desc())
        .all()
    )
    return render_template(
        "customer_archive.html",
        body_class="customer-shell",
        rows=rows,
        notifications=notifications_data(session.get("customer_id")),
    )


# ====== حسابي / خروج ======

@app.route("/customer/account", methods=["GET","POST"])
def customer_account():
    if not _require_customer():
        return redirect(url_for("customer_login"))
    cid = session.get("customer_id")
    customer = db.session.get(Customer, cid)   # استبدل Customer بالاسم عندك (CustomerModel مثلاً)

    if request.method == "POST" and request.form.get("action") == "password":
        # .. منطق التحقق والتحديث ..
        flash("تم تحديث بياناتك بنجاح ✅", "success")
        return redirect(url_for("customer_account"))

    return render_template("customer_account.html", customer=customer)



@app.route("/customer/account/delete", methods=["POST", "GET"])
def customer_account_delete():
    # تأكد من تسجيل الدخول
    if not _require_customer():
        return redirect(url_for("customer_login"))

    # احذف الحساب الحالي
    cid = session.get("customer_id")
    customer = db.session.get(Customer, cid)  # غيّر Customer إلى اسم موديلك الفعلي إذا كان CustomerModel
    if customer:
        db.session.delete(customer)
        db.session.commit()

    # انهِ الجلسة وأعد التوجيه
    session.clear()
    flash("تم حذف حسابك ✅", "success")
    return redirect(url_for("customer_login"))







@app.route("/customer/logout")
def customer_logout():
    session.clear()
    flash(message="تم تسجيل الخروج", category="ok")
    return redirect(url_for("customer_login"))

#----------------البوكس السفلي ---------------


@app.route("/terms")
def terms():
    return render_template("terms.html", title="الشروط والأحكام", hide_nav=True)

@app.route("/privacy")
def privacy():
    return render_template("privacy.html", title="سياسة الخصوصية", hide_nav=True)

@app.route("/faq")
def faq():
    return render_template("faq.html", title="الأسئلة الشائعة", hide_nav=True)

@app.route("/complaints")
def complaints():
    return render_template("complaints.html", title="الشكاوى والاقتراحات", hide_nav=True)

@app.route("/usage")
def usage():
    return render_template("usage.html", title="سياسة الاستخدام")

@app.cli.command("seed-admin")
def seed_admin():
    email = "admin@example.com"
    if not Admin.query.filter_by(email=email).first():
        a = Admin(
            name="المسؤول",
            email=email,
            password_hash=generate_password_hash("123456")
        )
        db.session.add(a)
        db.session.commit()
        print("✅ Admin created:", email, " / 123456")
    else:
        print("ℹ️ Admin already exists.")
#-=============================================
        app.register_blueprint(customers_bp)
# ===================== تشغيل =====================
=======
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
>>>>>>> 4ecbedc0c0d94090bfd8a85754327e566da579eb
if __name__ == "__main__":
    with app.app_context():
        ensure_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
<<<<<<< HEAD
=======

>>>>>>> 4ecbedc0c0d94090bfd8a85754327e566da579eb
