from flask import Flask
app = Flask(__name__)

@app.route("/ping")
def ping():
    return "OK"  # ما فيه قوالب ولا جلسات

@app.route("/")
def index():
    return "Alive"

if __name__ == "__main__":
    app.run(debug=True)