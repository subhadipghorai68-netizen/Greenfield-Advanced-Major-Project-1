import os, sqlite3, csv, io
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, make_response
import requests

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-before-production")
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "greenfield.db"))

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS crops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, field_name TEXT NOT NULL,
            stage TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
            planted_on TEXT, notes TEXT DEFAULT ''
        )""")
        count = con.execute("SELECT COUNT(*) FROM crops").fetchone()[0]
        if count == 0:
            con.executemany(
                "INSERT INTO crops(name,field_name,stage,progress,planted_on,notes) VALUES(?,?,?,?,?,?)",
                [
                    ("Rice", "Field A", "Vegetative", 68, "2026-08-15", "Monitor water level and leaf health."),
                    ("Wheat", "Field B", "Early growth", 34, "2026-10-02", "Check soil moisture weekly."),
                    ("Vegetables", "Field C", "Flowering", 82, "2026-07-20", "Inspect leaves for pests."),
                ]
            )

@app.route("/")
def dashboard():
    with db() as con:
        crops = con.execute("SELECT * FROM crops ORDER BY id DESC").fetchall()
    return render_template("dashboard.html", crops=crops, active="dashboard", now=datetime.now())

@app.route("/crops", methods=["GET", "POST"])
def crops_page():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        field_name = request.form.get("field_name","").strip()
        stage = request.form.get("stage","Seedling").strip()
        try:
            progress = max(0, min(100, int(request.form.get("progress", 0))))
        except ValueError:
            progress = 0
        planted_on = request.form.get("planted_on","")
        notes = request.form.get("notes","").strip()
        if name and field_name:
            with db() as con:
                con.execute("INSERT INTO crops(name,field_name,stage,progress,planted_on,notes) VALUES(?,?,?,?,?,?)",
                            (name,field_name,stage,progress,planted_on,notes))
            flash("Crop record added successfully.", "success")
        else:
            flash("Please enter a crop name and field name.", "warning")
        return redirect(url_for("crops_page"))
    with db() as con:
        crops = con.execute("SELECT * FROM crops ORDER BY id DESC").fetchall()
    return render_template("crops.html", crops=crops, active="crops")

@app.post("/crops/<int:crop_id>/delete")
def delete_crop(crop_id):
    with db() as con:
        con.execute("DELETE FROM crops WHERE id=?", (crop_id,))
    flash("Crop record deleted.", "success")
    return redirect(url_for("crops_page"))

@app.route("/insights")
def insights():
    with db() as con:
        rows = con.execute("SELECT name, progress FROM crops ORDER BY id").fetchall()
    return render_template("insights.html", crops=rows, active="insights")

@app.route("/irrigation", methods=["GET", "POST"])
def irrigation():
    if request.method == "POST":
        # Safe project simulation only. This never controls physical equipment.
        state = request.form.get("state", "off")
        flash("Demo pump state changed to " + ("ON" if state == "on" else "OFF") +
              ". This is a software simulation, not a real pump connection.", "success")
        return redirect(url_for("irrigation"))
    return render_template("irrigation.html", active="irrigation")

@app.get("/api/weather")
def weather():
    city = request.args.get("city", "Kolkata").strip()[:80] or "Kolkata"
    try:
        geo = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                           params={"name": city, "count": 1, "language": "en", "format": "json"},
                           timeout=12)
        geo.raise_for_status()
        places = geo.json().get("results", [])
        if not places:
            return jsonify({"error": "Location not found. Try another city name."}), 404
        place = places[0]
        params = {
            "latitude": place["latitude"], "longitude": place["longitude"],
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,rain,showers,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "auto", "forecast_days": 7
        }
        r = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=12)
        r.raise_for_status()
        data = r.json()
        return jsonify({"location": f'{place["name"]}, {place.get("admin1", "")}, {place["country"]}',
                        "timezone": data.get("timezone"), "current": data.get("current"),
                        "daily": data.get("daily"), "source": "Open-Meteo"})
    except requests.RequestException:
        return jsonify({"error": "Weather service is temporarily unavailable. Please try again."}), 503

@app.get("/export/crops.csv")
def export_crops():
    with db() as con:
        rows = con.execute("SELECT name,field_name,stage,progress,planted_on,notes FROM crops ORDER BY id").fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Crop", "Field", "Growth stage", "Progress %", "Planted on", "Notes"])
    writer.writerows([tuple(row) for row in rows])
    response = make_response("\ufeff" + output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=greenfield-crop-report.csv"
    return response

@app.get("/health")
def health():
    return jsonify({"status": "ok", "app": "GreenField Advanced"})

init_db()
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG") == "1")
