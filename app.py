"""app.py — Flask web interface for job_matcher.py"""

import os
import sys
import subprocess
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

try:
    from werkzeug.utils import secure_filename
except ImportError:
    print("Missing dependency. Run: pip install flask")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB upload limit

BASE_DIR   = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_SUFFIXES = {".pdf", ".docx", ".doc", ".txt"}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/run", methods=["POST"])
def run():
    if "resume" not in request.files or not request.files["resume"].filename:
        return jsonify({"error": "No resume file provided."}), 400

    f = request.files["resume"]
    suffix = Path(f.filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        return jsonify({"error": f"Unsupported file type '{suffix}'. Use .pdf, .docx, or .txt."}), 400

    resume_path = UPLOAD_DIR / secure_filename(f.filename)
    f.save(resume_path)

    form = request.form
    csv_path = BASE_DIR / "job_matches.csv"

    cmd = [sys.executable, str(BASE_DIR / "job_matcher.py"), str(resume_path)]

    if form.get("keywords"):
        cmd += ["--keywords", form["keywords"]]
    if form.get("location"):
        cmd += ["--location", form["location"]]
    if form.get("min_salary"):
        cmd += ["--min-salary", form["min_salary"]]
    if form.get("work_type"):
        cmd += ["--work-type", form["work_type"]]
    if form.get("days_ago"):
        cmd += ["--days-ago", form["days_ago"]]
    if form.get("country"):
        cmd += ["--country", form["country"]]
    if form.get("fetch"):
        cmd += ["--fetch", form["fetch"]]
    if form.get("top"):
        cmd += ["--top", form["top"]]

    cmd += ["--output", str(csv_path)]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(BASE_DIR),
        timeout=600,
    )

    output = result.stdout
    if result.stderr:
        output += "\n" + result.stderr

    return jsonify({
        "output":        output,
        "exit_code":     result.returncode,
        "csv_available": csv_path.exists(),
    })


@app.route("/download-csv")
def download_csv():
    csv_path = BASE_DIR / "job_matches.csv"
    if not csv_path.exists():
        return "No results file found. Run the matcher first.", 404
    return send_file(str(csv_path), as_attachment=True, download_name="job_matches.csv")


if __name__ == "__main__":
    print("Job Matcher running at http://localhost:5000")
    app.run(debug=False, port=5000)
