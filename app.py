# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, text, func, and_
from sqlalchemy.inspection import inspect
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, Admin, Customer, RequestModel
from datetime import datetime, timedelta, time
from dateutil.relativedelta import relativedelta
import re, os
from functools import wraps

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
# ===================== أدوات مساعدة =====================
# ====== one-time patch for missing columns in sqlite ======

def _add_column_if_missing(table: str, column: str, ddl: str) -> None:
    with db.engine.begin() as conn:
        cols = [row[1] for row in conn.exec_driver_sql(f'PRAGMA table_info("{table}")')]
        if column not in cols:
            conn.exec_driver_sql(ddl)

with app.app_context():
    # إنشاء الجداول إن لم تكن موجودة
    db.create_all()

    # ===== أعمدة جدول requests (تضاف فقط إذا كانت غير موجودة) =====
    _add_column_if_missing(
        table="requests",
        column="created_at",
        ddl="ALTER TABLE requests ADD COLUMN created_at DATETIME DEFAULT (CURRENT_TIMESTAMP)"
    )

    _add_column_if_missing(
        table="requests",
        column="notes",
        ddl="ALTER TABLE requests ADD COLUMN notes TEXT"
    )

    _add_column_if_missing(
        table="requests",
        column="rejected_reason",
        ddl="ALTER TABLE requests ADD COLUMN rejected_reason TEXT"
    )

    _add_column_if_missing(
        table="requests",
        column="status",
        ddl="ALTER TABLE requests ADD COLUMN status TEXT NOT NULL DEFAULT 'under_review'"
    )

    _add_column_if_missing(
        table="requests",
        column="tracking_code",
        ddl="ALTER TABLE requests ADD COLUMN tracking_code TEXT"
    )

    # ===== توحيد/تصحيح القيم القديمة للحالة (اختياري لكنه مفيد) =====
    with db.engine.begin() as conn:
        conn.exec_driver_sql("""
            UPDATE requests
               SET status = 'under_review'
             WHERE status IS NULL
                OR TRIM(status) = ''
                OR status IN ('pending','in_review','new')
        """)
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
        base.filter(col.in_(REJECTED)).count())

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


with app.app_context():
    try:
        db.session.execute(db.text('ALTER TABLE requests ADD COLUMN rejected_reason TEXT'))
        db.session.commit()
    except Exception:
        pass  # العمود موجود مسبقًا
# ديكوريتر تأكيد دخول الأدمن
def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            flash("الرجاء تسجيل الدخول كمسؤول.", category="err")
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


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

#===========================================================
@app.before_request
def guard_areas():
    ep = request.endpoint or ""

    # حماية مسارات العملاء فقط
    if ep.startswith("customer_"):
        if ep not in ("customer_login", "customer_signup", "customer_logout", "static"):
            if "customer_id" not in session:
                return redirect(url_for("customer_login"))

    # حماية مسارات المسؤولين فقط
    if ep.startswith("admin_"):
        if ep not in ("admin_login", "admin_logout", "static"):
            if "admin_id" not in session:
                return redirect(url_for("admin_login"))





# ===================== الراوتات العامة =====================
@app.route("/")
def index():
    return redirect(url_for("splash"))

# 2) السبلاش
@app.route("/splash")
def splash():
    return render_template(
        "splash.html",
        title="جارٍ التحميل…",
        hide_nav=True,
        hide_logo=True,
    )

# 3) شاشة اختيار نوع الدخول (صلّحي المسار هنا)
@app.route("/auth/choose")
def auth_choose():
    return render_template(
        "auth_choose.html",
        title="اختيار نوع الدخول",
        hide_nav=True,
        hide_logo=True,
    )
# ===================== مسؤولين =====================
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    title = "تسجيل دخول المسؤول"
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()

        if not email or not password:
            flash("الرجاء إدخال البريد وكلمة المرور", category="err")
            return render_template("admin_login.html", title=title, hide_nav=True, email=email)

        admin = Admin.query.filter_by(email=email).first()
        if not admin or not check_password_hash(admin.password_hash, password):
            flash("بيانات الدخول غير صحيحة", category="err")
            return render_template("admin_login.html", title=title, hide_nav=True, email=email)

        # تهيئة الجلسة
        session.clear()
        session["role"] = "admin"
        session["admin_id"] = admin.id
        session["admin_name"] = getattr(admin, "name", "مسؤول")

        return redirect(url_for("admin_home"))

    return render_template("admin_login.html", title=title, hide_nav=True)
#===============================================
@app.route("/admin")
@app.route("/admin/dashboard")
@admin_required
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
@admin_required
def admin_manage():
    pending = (
        RequestModel.query
        .filter_by(Request_status="pending")
        .order_by(RequestModel.created_at.desc())
        .all()
    )
    return render_template(
        "admin_requests.html",
        title="إدارة الطلبات",
        pending=pending
    )

@app.get("/admin/archive")
@admin_required
def admin_archive():
    items = (RequestModel.query
             .filter(RequestModel.status.in_(["approved", "rejected"]))
             .order_by(RequestModel.created_at.desc())
             .all())
    return render_template("admin_archive.html", items=items, is_admin=True)
#====================
@app.get("/admin/home")
def admin_home():
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    # إحصاءات أعلى الصفحة
    total        = db.session.query(func.count(RequestModel.id)).scalar() or 0
    approved_cnt = db.session.query(func.count(RequestModel.id)).filter(RequestModel.status == "approved").scalar() or 0
    review_cnt   = db.session.query(func.count(RequestModel.id)).filter(RequestModel.status == "under_review").scalar() or 0
    rejected_cnt = db.session.query(func.count(RequestModel.id)).filter(RequestModel.status == "rejected").scalar() or 0

    # بيانات الرسم الشهري لآخر 12 شهر
    from datetime import datetime, timedelta
    today = datetime.utcnow().replace(day=1)  # أول يوم في الشهر الحالي
    months = []
    for i in range(11, -1, -1):  # 12 شهر للخلف
        start = (today - relativedelta(months=i))
        end   = (start + relativedelta(months=1))
        label = start.strftime("%Y-%m")
        months.append((label, start, end))

    labels = []
    series_approved = []
    series_review   = []
    series_rejected = []

    for label, start, end in months:
        labels.append(start.strftime("%b %Y"))  # مثال: Jan 2025
        series_approved.append(
            db.session.query(func.count(RequestModel.id))
            .filter(RequestModel.created_at >= start, RequestModel.created_at < end,
                    RequestModel.status == "approved").scalar() or 0
        )
        series_review.append(
            db.session.query(func.count(RequestModel.id))
            .filter(RequestModel.created_at >= start, RequestModel.created_at < end,
                    RequestModel.status == "under_review").scalar() or 0
        )
        series_rejected.append(
            db.session.query(func.count(RequestModel.id))
            .filter(RequestModel.created_at >= start, RequestModel.created_at < end,
                    RequestModel.status == "rejected").scalar() or 0
        )

    return render_template(
        "admin_home.html",
        is_admin=True,
        cards=dict(
            total=total,
            approved=approved_cnt,
            under_review=review_cnt,
            rejected=rejected_cnt,
        ),
        monthly_labels=labels,
        monthly_approved=series_approved,
        monthly_under_review=series_review,
        monthly_rejected=series_rejected,
    )
# ====== تسجيل خروج المسؤول ======
@app.post("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

@app.get("/admin/requests")
def admin_requests():
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    # الطلبات قيد المراجعة أولاً
    pending = (RequestModel.query
               .filter(RequestModel.status == "under_review")
               .order_by(RequestModel.created_at.desc())
               .all())

    # لو تحب تعرض المقبولة/المرفوضة هنا بشكل مختصر
    accepted = (RequestModel.query
                .filter(RequestModel.status == "accepted")
                .order_by(RequestModel.created_at.desc())
                .limit(10).all())

    rejected = (RequestModel.query
                .filter(RequestModel.status == "rejected")
                .order_by(RequestModel.created_at.desc())
                .limit(10).all())

    return render_template(
        "admin_requests.html",
        is_admin=True,
        pending=pending,
        approved=accepted,
        rejected=rejected,
        notifications=notifications_data() if 'notifications_data' in globals() else {}
    )
# API: قبول طلب
@app.post("/admin/requests/<int:req_id>/approve")
@admin_required
def api_approve(req_id):
    r = RequestModel.query.get_or_404(req_id)
    r.status = "accepted"
    r.decision_reason = None
    db.session.commit()
    return jsonify({"ok": True, "status": r.status})

@app.post("/admin/requests/<int:req_id>/reject")
@admin_required
def api_reject(req_id):
    data   = request.get_json() or {}
    reason = (data.get("reason") or "").strip()
    if not reason:
        return jsonify({"ok": False, "error": "اكتبي سبب الرفض."}), 400

    r = RequestModel.query.get_or_404(req_id)
    r.status = "rejected"
    r.decision_reason = reason
    db.session.commit()
    return jsonify({"ok": True, "status": r.status, "reason": r.decision_reason})
#====================================================
@app.route("/admin/account", methods=["GET", "POST"])
def admin_account():
    # حماية منطقة الأدمن
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    admin = Admin.query.get(session["admin_id"])

    if request.method == "POST":
        curr = (request.form.get("curr_password") or "").strip()
        new1 = (request.form.get("new_password") or "").strip()
        new2 = (request.form.get("new_password_confirm") or "").strip()

        if not curr or not new1 or not new2:
            flash("الرجاء تعبئة جميع الحقول.", "err")
        elif not check_password_hash(admin.password_hash, curr):
            flash("كلمة المرور الحالية غير صحيحة.", "err")
        elif new1 != new2:
            flash("تأكيد كلمة المرور غير مطابق.", "err")
        else:
            admin.password_hash = generate_password_hash(new1)
            db.session.commit()
            flash("تم تحديث كلمة المرور بنجاح.", "success")

    # مهم: تمرير admin والإشارة إلى أن الصفحة للأدمن
    return render_template("admin_account.html", admin=admin, is_admin=True)


@app.route("/admin/update_status", methods=["POST"])
def admin_update_status():
    data = request.get_json()
    req_id = data.get("id")
    action = data.get("action")
    reason = data.get("reason", "")

    # عدّل اسم الموديل/الحقول حسب مشروعك
    r = RequestModel.query.get(req_id)
    if not r:
        return {"success": False, "message": "الطلب غير موجود"}

    if action == "approve":
        r.status = "approved"
        r.rejected_reason = None
    elif action == "reject":
        r.status = "rejected"
        r.rejected_reason = reason
    else:
        return {"success": False, "message": "إجراء غير صحيح"}

    db.session.commit()
    return {"success": True}


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
    if "customer_id" not in session:
        return redirect(url_for("customer_login"))

    cid = session["customer_id"]

    # قيَم ابتدائية
    counts = {"under_review": 0, "approved": 0, "rejected": 0}

    # تجميع حسب الحالة
    rows = (
        db.session.query(RequestModel.status, func.count(RequestModel.id))
        .filter(RequestModel.customer_id == cid)
        .group_by(RequestModel.status)
        .all()
    )
    for st, c in rows:
        if st in counts:
            counts[st] = c

    total = counts["under_review"] + counts["approved"] + counts["rejected"]

    # بيانات الدونات (ترتيب: قيد المراجعة, مقبولة, مرفوضة)
    donut_data = [
        counts["under_review"],
        counts["approved"],
        counts["rejected"],
    ]

    return render_template(
        "customer_home.html",
        counts=counts,
        total=total,
        donut_data=donut_data,
        notifications=notifications_data(session.get("customer_id")),
    )
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
        notes = (request.form.get("notes") or "").strip()

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
            status      = "under_review",
            tracking_code = _next_tracking_code(),
            created_at  = datetime.utcnow(),

        )
        r.status = "under_review"
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

#===========================



@app.route("/customer/requests/<int:req_id>/delete", methods=["POST"])
def customer_request_delete(req_id):
    # لازم يكون مسجّل
    if "customer_id" not in session:
        return redirect(url_for("customer_login"))

    cid = session["customer_id"]

    # نجيب الطلب ويتأكد أنه لنفس العميل
    r = RequestModel.query.filter_by(id=req_id, customer_id=cid).first_or_404()

    # (اختياري) امنع الحذف لو الحالة ليست قيد المراجعة
    # if r.status not in ("under_review", "pending"):
    #     flash("لا يمكن حذف الطلب بعد بدء معالجته.", "danger")
    #     return redirect(url_for("customer_requests_status"))

    db.session.delete(r)
    db.session.commit()

    flash("تم حذف الطلب بنجاح.", "success")
    return redirect(url_for("customer_requests_status"))



@app.route("/customer/logout", methods=["POST"])
def customer_logout():
    session.pop("customer_id", None)
    flash("تم تسجيل الخروج.", "success")
    return redirect(url_for("auth_choose"))
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

@app.route("/contact")
def contact():
    return render_template("contact.html", title="تواصل معنا")



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
# ---------------- تشغيل ----------------
if __name__ == "__main__":
    with app.app_context():
        ensure_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
