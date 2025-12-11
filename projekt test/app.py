from flask import Flask, render_template, request, redirect, session, send_file
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import yaml

app = Flask(__name__)
app.secret_key = "super_secret_key"


# -------------------- DATABASE CONNECTION --------------------
#main_db = psycopg2.connect(
 #   host="192.168.220.131",
  #  user="postgres",
   # password="1234",
    #dbname="postgres"
#)

def get_cur():
    return main_db.cursor(cursor_factory=RealDictCursor)


# -------------------- LOGIN SYSTEM --------------------
USERNAME = "admin"
PASSWORD = "1234"

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["username"] == USERNAME and request.form["password"] == PASSWORD:
            session["logged_in"] = True
            return redirect("/dashboard")
        else:
            return render_template("login.html", error="Forkert login")

    return render_template("login.html")


# -------------------- DASHBOARD --------------------
@app.route("/dashboard")
def dashboard():
    if "logged_in" not in session:
        return redirect("/")

    return render_template("dashboard.html")


# -------------------- PATIENT LIST --------------------
@app.route("/patients")
def patients():
    if "logged_in" not in session:
        return redirect("/")

    cur = get_cur()
    cur.execute("SELECT * FROM patient ORDER BY id DESC")
    data = cur.fetchall()

    return render_template("patients.html", patients=data)

# -------------------- SENSOR DATA ENDPOINT --------------------
@app.route("/sensor", methods=["POST"])
def sensor():
    data = request.get_json()

    if not data or "value" not in data:
        return {"error": "Invalid payload"}, 400

    value = data["value"]

    cur = get_cur()
    cur.execute("INSERT INTO readings (value) VALUES (%s)", (value,))
    main_db.commit()

    return {"status": "Sensor data stored", "value": value}


# -------------------- ADD PATIENT --------------------
@app.route("/add_patient", methods=["GET", "POST"])
def add_patient():
    if "logged_in" not in session:
        return redirect("/")

    if request.method == "POST":
        navn = request.form["navn"]
        alder = request.form["alder"]
        cpr = request.form["cpr"]
        diagnose = request.form["diagnose"]

        cur = get_cur()
        cur.execute("""
        INSERT INTO patient (navn, alder, cpr, diagnose)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (cpr) DO NOTHING;
        """, (navn, alder, cpr, diagnose))

        main_db.commit()
        return redirect("/patients")

    return render_template("add_patient.html")


# -------------------- EXPORT YAML --------------------
@app.route("/export_yaml")
def export_yaml():
    cur = get_cur()
    cur.execute("SELECT * FROM patient")
    patients = cur.fetchall()

    with open("patient.yaml", "w") as f:
        yaml.dump(patients, f, sort_keys=False)

    return send_file("patient.yaml", as_attachment=True)


# -------------------- LOGOUT --------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# -------------------- RUN --------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)