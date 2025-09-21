from datetime import datetime, date, time
from flask import (Flask, render_template, request, redirect, url_for,session, flash, jsonify)
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import or_, and_
from models import db, Customer, RequestModel  # تأكد من صحة الأسماء
import re

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "change-me"

db.init_app(app)

@app.context_processor
def inject_helpers():
    from flask import current_app
    def has_endpoint(name: str) -> bool:
        return name in current_app.view_functions
    return dict(has_endpoint=has_endpoint)
# ======================== أدوات مساعدة ========================

PHONE_RE = re.compile(r"^\d{10}$")
PWD_RE   = re.compile(r"^(?=.*[A-Z])[A-Za-z0-9]{6,}$")
# ================= Regex =================
def _require_customer() -> bool:
    return bool(session.get("customer_id"))

def _current_customer():
    cid = session.get("customer_id")
    if not cid:
        return None
    try:
        return db.session.get(Customer, cid)
    except Exception:
        return None

def notifications_data(customer_id):
    # لو تحتاج بيانات إشعارات لاحقًا
    return []

def _next_tracking_code(prefix="WT-"):
    last = (
        db.session.query(RequestModel)
        .filter(RequestModel.tracking_code.like(f"{prefix}%"))
        .order_by(RequestModel.id.desc())
        .first()
    )
    n = 0
    if last and last.tracking_code:
        try:
            n = int(last.tracking_code.split("-")[-1])
        except Exception:
            n = 0
    return f"{prefix}{n+1:04d}"

# ======================== صفحات عامة / سبلاش ========================
@app.route("/")
def index():
    return redirect(url_for("splash"))

@app.route("/splash")
def splash():
    # صفحة البداية (Splash)
    return render_template("splash.html", body_class="splash-page")

@app.route("/auth/choose")
def auth_choose():
    # شاشة اختيار نوع الدخول
    return render_template("auth_choose.html", body_class="auth-choose-page")
#==========================================================================================

@app.route("/login/customer", methods=["GET", "POST"])
def customer_login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        user = db.session.query(Customer).filter(Customer.email == email).first()
        if user and check_password_hash(user.password_hash, password):
            session["customer_id"] = user.id
            flash("تم تسجيل الدخول بنجاح.", "success")
            return redirect(url_for("customer_home"))
        flash("بيانات الدخول غير صحيحة.", "err")
    return render_template("login_customer.html")





@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("customer_login"))

# ======================== واجهة العميل ========================

@app.route("/customer/home")
def customer_home():
    if not _require_customer():
        return redirect(url_for("customer_login"))

    user = _current_customer()
    # ممكن تحسب أي عدادات أو تنبيهات هنا
    return render_template(
        "customer_home.html",
        notifications=notifications_data(user.id if user else None),
        body_class="customer-home-page"
    )

# -------- إضافة طلب --------
@app.route("/customer/request/new", methods=["GET", "POST"])
def customer_request_new():
    if not _require_customer():
        return redirect(url_for("customer_login"))

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        district = (request.form.get("district") or "").strip()
        if district == "other":
            district = (request.form.get("district_other") or "").strip()
        req_type = (request.form.get("request_type") or "").strip()
        notes = (request.form.get("notes") or "").strip()

        if not title or not district or not req_type:
            flash("عذراً، فضلاً أكمل الحقول المطلوبة.", "err")
            return redirect(url_for("customer_request_new"))

        r = RequestModel(
            customer_id=session["customer_id"],
            title=title,
            district=district,
            request_type=req_type,
            notes=notes,
            status="pending",
            tracking_code=_next_tracking_code(),
            created_at=datetime.utcnow(),
        )
        db.session.add(r)
        db.session.commit()

        msg = f"تم حفظ طلبك بنجاح، رقم الطلب #{r.tracking_code}"
        # دعم AJAX
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or \
           "application/json" in (request.headers.get("Accept") or ""):
            return jsonify(success=True, message=msg)

        flash(msg, "success")
        return redirect(url_for("customer_home"))

    return render_template(
        "customer_request_new.html",
        notifications=notifications_data(session.get("customer_id")),
        body_class="customer-shell",
    )

# -------- حالة الطلب (بحث برقم الطلب) --------
@app.route("/customer/requests", methods=["GET", "POST"])
def customer_requests_status():
    if not _require_customer():
        return redirect(url_for("customer_login"))

    rows = []
    tracking = ""
    if request.method == "POST":
        tracking = (request.form.get("tracking_code") or "").strip()
        if tracking:
            rows = (
                db.session.query(RequestModel)
                .filter(
                    RequestModel.customer_id == session["customer_id"],
                    RequestModel.tracking_code.ilike(tracking)
                )
                .order_by(RequestModel.created_at.desc())
                .all()
            )
    return render_template(
        "customer_requests_status.html",
        rows=rows,
        tracking_code=tracking,
        notifications=notifications_data(session.get("customer_id")),
        body_class="customer-shell",
    )

# -------- أرشيف الطلبات --------
@app.route("/customer/archive")
def customer_archive():
    if not _require_customer():
        return redirect(url_for("customer_login"))
    rows = (
        db.session.query(RequestModel)
        .filter(RequestModel.customer_id == session["customer_id"])
        .order_by(RequestModel.created_at.desc())
        .all()
    )
    return render_template(
        "customer_archive.html",
        rows=rows,
        notifications=notifications_data(session.get("customer_id")),
        body_class="customer-shell",
    )

# -------- حسابي --------
@app.route("/customer/account", methods=["GET", "POST"])
def customer_account():
    if not _require_customer():
        return redirect(url_for("customer_login"))

    user = _current_customer()
    if not user:
        flash("تعذّر تحميل الحساب.", "err")
        return redirect(url_for("customer_home"))

    # ثلاثة نماذج صغيرة بنفس الصفحة:
    # 1) تحديث التفضيلات (داكن/إشعارات)
    if request.method == "POST" and request.form.get("action") == "prefs":
        user.dark_mode = True if request.form.get("dark_mode") == "on" else False
        user.notifications_enabled = True if request.form.get("notifications") == "on" else False
        db.session.commit()
        flash("تم تحديث تفضيلاتك بنجاح ✅", "success")
        return redirect(url_for("customer_account"))

    # 2) تغيير كلمة المرور
    if request.method == "POST" and request.form.get("action") == "password":
        current_pw = request.form.get("current_password") or ""
        new_pw = request.form.get("new_password") or ""
        confirm_pw = request.form.get("confirm_password") or ""
        if not check_password_hash(user.password_hash, current_pw):
            flash("كلمة المرور الحالية غير صحيحة.", "err")
            return redirect(url_for("customer_account"))
        if not new_pw or new_pw != confirm_pw or len(new_pw) < 8:
            flash("تحقق من كلمة المرور الجديدة (8 أحرف على الأقل) والتأكيد.", "err")
            return redirect(url_for("customer_account"))
        user.password_hash = generate_password_hash(new_pw)
        db.session.commit()
        flash("تم تحديث كلمة المرور ✅", "success")
        return redirect(url_for("customer_account"))

    # 3) حذف الحساب (زر أحمر تحت معلومات الحساب)
    if request.method == "POST" and request.form.get("action") == "delete":
        cid = user.id
        # احذف طلبات العميل إن رغبت:
        db.session.query(RequestModel).filter(RequestModel.customer_id == cid).delete()
        db.session.delete(user)
        db.session.commit()
        session.clear()
        flash("تم حذف حسابك ✅", "success")
        return redirect(url_for("customer_login"))

    # GET — عرض الصفحة
    return render_template(
        "customer_account.html",
        user=user,
        notifications=notifications_data(user.id),
        body_class="customer-account",
    )

# مسار صريح للحذف في حال القوالب تنادي اسم ثابت
@app.route("/customer/account/delete", methods=["POST"])
def customer_delete_account():
    if not _require_customer():
        return redirect(url_for("customer_login"))
    user = _current_customer()
    if not user:
        return redirect(url_for("customer_login"))
    db.session.query(RequestModel).filter(RequestModel.customer_id == user.id).delete()
    db.session.delete(user)
    db.session.commit()
    session.clear()
    flash("تم حذف حسابك ✅", "success")
    return redirect(url_for("customer_login"))

# alias حفاظًا على التوافق لو كان القالب ينادي customer_account_delete
app.add_url_rule(
    "/customer/account/delete-alias",
    endpoint="customer_account_delete",
    view_func=customer_delete_account,
    methods=["POST"]
)

# ======================== صفحات المسؤول (بسيطة كنماذج) ========================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    # ضع تحقق المسؤول الحقيقي لاحقًا
    if request.method == "POST":
        session["admin"] = True
        return redirect(url_for("admin_home"))
    return render_template("admin_login.html")

@app.route("/admin/home")
def admin_home():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    total_requests = db.session.query(RequestModel).count()
    total_customers = db.session.query(Customer).count()
    return render_template(
        "admin_home.html",
        total_requests=total_requests,
        total_customers=total_customers
    )

@app.route("/admin/archive")
def admin_archive():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    rows = db.session.query(RequestModel).order_by(RequestModel.created_at.desc()).all()
    return render_template("admin_archive.html", rows=rows)
#============================================================
@app.route("/terms", methods=["GET"])
def terms():
    return render_template("terms.html", body_class="policy-page")

@app.route("/privacy", methods=["GET"])
def privacy():
    return render_template("privacy.html", body_class="policy-page")

@app.route("/faq", methods=["GET"])
def faq():
    return render_template("faq.html", body_class="policy-page")

@app.route("/complaints", methods=["GET"])
def complaints():
    return render_template("complaints.html", body_class="policy-page")
# ======================== تشغيل التطبيق ========================

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)