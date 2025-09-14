from app import app, db, AppUser

def main():
    with app.app_context():
        db.create_all()

        email = "admin@example.com"
        password = "1234"
        name = "Mayara Alhamed"

        user = AppUser.query.filter_by(email=email).first()
        if not user:
            user = AppUser(name=name, email=email, password=password)
            db.session.add(user)
            db.session.commit()
            print("✓ تم إنشاء المستخدم:", email)
        else:
            user.password = password
            user.name = name
            db.session.commit()
            print("✓ تم تحديث المستخدم:", email)

if __name__ == "__main__":
    main()