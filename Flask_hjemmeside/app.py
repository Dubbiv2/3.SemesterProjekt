from flask import Flask, request, render_template, jsonify, redirect, url_for, session, Response
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
import yaml

app = Flask(__name__)
app.secret_key = "1234"  


def forbind_database():
    return psycopg2.connect(
        host="192.168.220.131",
        database="postgres",
        user="postgres",
        password="1234"
    )

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        users = {
            "admin": {"password": "smoshy", "role": "admin"},
            "anemette": {"password": "olfoolfo", "role": "limited"}
        }

        if username in users and users[username]["password"] == password:
            session["logged_in"] = True
            session["username"] = username
            session["role"] = users[username]["role"]
            return redirect(url_for("index"))
        else:
            error = "Forkert brugernavn eller adgangskode"

    return render_template("login.html", error=error)

@app.route("/logud")
def logud():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
def index():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template("index.html")

@app.route("/patient/ny", methods=["GET", "POST"])
def ny_patient():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        return "Adgang nægtet", 403

    if request.method == "POST":
        navn = request.form.get("navn")
        alder = request.form.get("alder")
        cpr = request.form.get("cpr")
        diagnose = request.form.get("diagnose")

        if not navn:
            return "Navn er påkrævet", 400

        try:
            conn = forbind_database()
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO patient (navn, alder, cpr, diagnose)
                    VALUES (%s, %s, %s, %s)
                """, (navn, alder, cpr, diagnose))
                conn.commit()
            conn.close()
        except Exception as e:
            print("Databasefejl:", e)
            return "Databasefejl", 500

        return redirect(url_for("patientdatabase"))

    return render_template("ny_patient.html")

@app.route("/patient/slet/<int:patient_id>", methods=["POST"])
def slet_patient(patient_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        return "Adgang nægtet", 403

    try:
        conn = forbind_database()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM patient_data WHERE patient_id = %s", (patient_id,))
            cur.execute("DELETE FROM patient WHERE id = %s", (patient_id,))
            conn.commit()
        conn.close()
    except Exception as e:
        print("Databasefejl:", e)
        return "Databasefejl", 500

    return redirect(url_for("patientdatabase"))

@app.route("/patientdatabase")
def patientdatabase():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    patients = []
    try:
        conn = forbind_database()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, navn, alder, cpr, diagnose FROM patient ORDER BY navn")
            patients = cur.fetchall()
        conn.close()
    except Exception as e:
        print("Databasefejl:", e)

    return render_template("patientdatabase.html", patients=patients)

@app.route("/patientdatabase/download")
def download_patient_yaml():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        return "Adgang nægtet", 403

    try:
        conn = forbind_database()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, navn, alder, cpr, diagnose FROM patient ORDER BY navn")
            patients = cur.fetchall()
        conn.close()
    except Exception as e:
        print("Databasefejl:", e)
        return "Databasefejl", 500

    yaml_data = yaml.dump(patients, allow_unicode=True)

    return Response(
        yaml_data,
        mimetype="application/x-yaml",
        headers={"Content-Disposition": "attachment; filename=patients.yaml"}
    )

@app.route("/patient/<int:patient_id>")
def patient_detail(patient_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    patient = None
    sensor_data = []

    try:
        conn = forbind_database()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, navn, alder, cpr, diagnose FROM patient WHERE id = %s",
                (patient_id,)
            )
            patient = cur.fetchone()

            cur.execute("""
                SELECT gps_lat, gps_lon, årsag, solenoid, door_state, created_at
                FROM patient_data
                WHERE patient_id = %s
                ORDER BY created_at DESC
                LIMIT 20
            """, (patient_id,))
            sensor_data = cur.fetchall()

        conn.close()
    except Exception as e:
        print("Databasefejl:", e)

    return render_template("patient.html", patient=patient, sensor_data=sensor_data)

def _to_bool(x):
    if isinstance(x, bool):
        return x
    if x is None:
        return False
    if isinstance(x, (int, float)):
        return x != 0
    if isinstance(x, str):
        return x.strip().lower() in ("1", "true", "yes", "y", "on")
    return False

@app.route("/api/update", methods=["POST"])
def api_update():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "msg": "no json"}), 400

    patient_id = data.get("patient_id")
    if not patient_id:
        return jsonify({"status": "error", "msg": "missing patient_id"}), 400

    gps_lat = data.get("latitude", data.get("lat"))
    gps_lon = data.get("longitude", data.get("lon"))

    gps_ok = data.get("gps_ok", None)
    if gps_ok is not None and not _to_bool(gps_ok):
        gps_lat = None
        gps_lon = None

    reason = data.get("årsag", data.get("reason"))

    alarm_val = data.get("alarm", None)
    if alarm_val is not None:
        if _to_bool(alarm_val):
            if not reason:
                reason = "ALARM"
            else:
                reason = "ALARM: " + str(reason)
        else:
            reason = "STOP"


    if not reason:
        reason = "UKENDT"

    solenoid = data.get("solenoid", data.get("solenoid_ok"))
    solenoid = _to_bool(solenoid)

    door_state = data.get("door_state", None)
    if door_state is not None:
        door_state = str(door_state).strip().upper()
        if door_state not in ("OPEN", "LOCKED"):
            door_state = None


    created_at = datetime.now()

    try:
        conn = forbind_database()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO patient_data
                (patient_id, gps_lat, gps_lon, årsag, solenoid, door_state, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (patient_id, gps_lat, gps_lon, reason, solenoid, door_state, created_at))
            conn.commit()
        conn.close()
    except Exception as e:
        print("Databasefejl:", e)
        return jsonify({"status": "error"}), 500

    return jsonify({"status": "success"})

if __name__ == "__main__":
    app.run(debug=True, host="192.168.220.131", port=5000)