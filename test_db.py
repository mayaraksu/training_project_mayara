import oracledb

try:
    conn = oracledb.connect(
        user="اسم_المستخدم",
        password="كلمة_المرور",
        dsn="localhost:1521/XEPDB1"   # عدّليها حسب بيئتك
    )
    print("✅ تم الاتصال بقاعدة البيانات")
    print("نسخة أوراكل:", conn.version)

    # اختبار استعلام بسيط
    with conn.cursor() as cur:
        cur.execute("SELECT 'OK' FROM dual")
        print("نتيجة الاختبار:", cur.fetchone()[0])

    conn.close()
except Exception as e:
    print("❌ خطأ في الاتصال:", e)