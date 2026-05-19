#!/usr/bin/env python3
"""job_matcher.py — score Adzuna + JSearch job listings against your resume using Claude."""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic
import requests

try:
    import PyPDF2
except ImportError:
    print("Missing dependency. Run: pip install PyPDF2")
    sys.exit(1)

try:
    import docx
except ImportError:
    print("Missing dependency. Run: pip install python-docx")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional; set env vars manually if not installed


# ---------------------------------------------------------------------------
# Resume reading
# ---------------------------------------------------------------------------

def read_resume(path: str) -> str:
    p = Path(path)
    if not p.exists():
        print(f"Error: file not found: {path}")
        sys.exit(1)
    if p.suffix.lower() == ".pdf":
        with open(p, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            if reader.is_encrypted:
                print("Error: PDF is encrypted. Please provide an unencrypted file.")
                sys.exit(1)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
    elif p.suffix.lower() in (".docx", ".doc"):
        doc = docx.Document(str(p))
        text = "\n".join(para.text for para in doc.paragraphs)
    else:
        text = p.read_text(encoding="utf-8")
    return text.strip()


# ---------------------------------------------------------------------------
# Job normalization — common flat schema for all sources
# ---------------------------------------------------------------------------

def _normalize_adzuna(job: dict) -> dict:
    desc = job.get("description") or ""
    location = (job.get("location") or {}).get("display_name", "N/A")
    is_remote = "remote" in location.lower() or "remote" in desc.lower()
    return {
        "title":       job.get("title", "N/A"),
        "company":     (job.get("company") or {}).get("display_name", "N/A"),
        "location":    location,
        "salary_min":  job.get("salary_min"),
        "salary_max":  job.get("salary_max"),
        "description": desc,
        "url":         job.get("redirect_url", "N/A"),
        "created":     job.get("created", ""),
        "source":      "Adzuna",
        "is_remote":   is_remote,
    }


def _normalize_jsearch(job: dict) -> dict:
    city  = job.get("job_city") or ""
    state = job.get("job_state") or ""
    location = ", ".join(filter(None, [city, state])) or job.get("job_country", "N/A")
    return {
        "title":       job.get("job_title", "N/A"),
        "company":     job.get("employer_name", "N/A"),
        "location":    location,
        "salary_min":  job.get("job_min_salary"),
        "salary_max":  job.get("job_max_salary"),
        "description": job.get("job_description") or "",
        "url":         job.get("job_apply_link", "N/A"),
        "created":     job.get("job_posted_at_datetime_utc", ""),
        "source":      "JSearch",
        "is_remote":   bool(job.get("job_is_remote")),
    }


# ---------------------------------------------------------------------------
# Job search — Adzuna
# ---------------------------------------------------------------------------

def search_jobs_adzuna(
    app_id: str,
    app_key: str,
    country: str,
    keywords: str,
    max_results: int,
) -> list:
    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": min(max_results, 50),
        "content-type": "application/json",
    }
    if keywords:
        params["what"] = keywords

    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
    except requests.HTTPError as e:
        print(f"  Adzuna API error: {e}")
        return []
    except requests.ConnectionError:
        print("  Network error: could not reach Adzuna API.")
        return []

    return [_normalize_adzuna(j) for j in resp.json().get("results", [])]


# ---------------------------------------------------------------------------
# Job search — JSearch (RapidAPI — aggregates LinkedIn, Indeed, Glassdoor)
# ---------------------------------------------------------------------------

def search_jobs_jsearch(
    api_key: str,
    keywords: str,
    max_results: int,
) -> list:
    url = "https://api.openwebninja.com/jsearch/search"
    params = {
        "query": keywords or "jobs",
        "page":  "1",
    }
    headers = {
        "x-api-key": api_key,
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
    except requests.HTTPError as e:
        print(f"  JSearch API error: {e}")
        return []
    except requests.ConnectionError:
        print("  Network error: could not reach JSearch API.")
        return []

    data = resp.json().get("data") or []
    return [_normalize_jsearch(j) for j in data[:max_results]]


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def deduplicate_jobs(jobs: list) -> list:
    seen = set()
    unique = []
    for job in jobs:
        key = (job["title"].lower().strip(), job["company"].lower().strip())
        if key not in seen:
            seen.add(key)
            unique.append(job)
    return unique


# ---------------------------------------------------------------------------
# Claude scoring
#
# The system prompt embeds the resume and preferences with cache_control so
# both are reused across all scoring calls after the first API roundtrip.
# ---------------------------------------------------------------------------

def _build_preferences_text(preferences: dict) -> str:
    lines = []
    if preferences.get("location"):
        lines.append(f"- Preferred location: {preferences['location']}")
    if preferences.get("min_salary"):
        lines.append(f"- Minimum acceptable salary: ${preferences['min_salary']:,}")
    if preferences.get("work_type"):
        lines.append(f"- Preferred work arrangement: {preferences['work_type']}")
    if preferences.get("days_ago"):
        lines.append(f"- Prefer jobs posted within the last {preferences['days_ago']} days")
    return "\n".join(lines)


def score_job(
    client: anthropic.Anthropic,
    resume: str,
    job: dict,
    preferences: dict,
) -> tuple:
    job_text = (
        f"Title: {job['title']}\n"
        f"Company: {job['company']}\n"
        f"Location: {job['location']}\n"
        f"Salary range: {job.get('salary_min', '')} - {job.get('salary_max', '')}\n"
        f"Description:\n{job['description'][:2000]}"
    )

    prefs_text = _build_preferences_text(preferences)
    prefs_block = (
        f"\n\n<preferences>\n{prefs_text}\n</preferences>\n"
        "These are soft preferences. Factor them into the score — a job that "
        "matches them well should score higher — but never score a job at 1 "
        "solely because it doesn't match a preference."
    ) if prefs_text else ""

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=300,
        system=[
            {
                "type": "text",
                "text": (
                    "You are a career advisor evaluating job-resume fit.\n"
                    "Given the resume and candidate preferences below, respond with ONLY "
                    'a JSON object: {"score": <integer 1-10>, "explanation": "<one sentence>"}.\n'
                    "Score 10 = perfect match for both skills and preferences, "
                    "1 = completely unrelated to the candidate's background. No other text.\n\n"
                    f"<resume>\n{resume}\n</resume>"
                    f"{prefs_block}"
                ),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": f"Score this job posting:\n\n{job_text}"}],
    )

    raw = response.content[0].text.strip()
    start = raw.find("{")
    end = raw.rfind("}") + 1
    data = json.loads(raw[start:end])
    return int(data["score"]), str(data["explanation"])


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt_salary(job: dict) -> str:
    lo = job.get("salary_min")
    hi = job.get("salary_max")
    try:
        if lo and hi:
            return f"${float(lo):,.0f} - ${float(hi):,.0f}"
        if lo:
            return f"${float(lo):,.0f}+"
        if hi:
            return f"up to ${float(hi):,.0f}"
    except (TypeError, ValueError):
        pass
    return "Not listed"


def fmt_date(job: dict) -> str:
    raw = job.get("created", "")
    if not raw:
        return "N/A"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return raw[:10] if len(raw) >= 10 else raw


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_results(jobs: list) -> None:
    w = 80
    print("\n" + "=" * w)
    print(f"  TOP JOB MATCHES  ({len(jobs)} results)".center(w))
    print("=" * w)
    for i, j in enumerate(jobs, 1):
        score = j["match_score"]
        bar = "#" * score + "-" * (10 - score)
        remote_tag = "Remote" if j.get("is_remote") else "On-site"
        print(f"\n  #{i}  [{bar}]  {score}/10  [{j['source']}]")
        print(f"  {j['title']}  |  {j['company']}")
        print(f"  Location : {j['location']}  ({remote_tag})")
        print(f"  Salary   : {j['salary']}")
        print(f"  Match    : {j['explanation']}")
        print(f"  Link     : {j['url']}")
        if j.get("description"):
            snippet = j["description"][:200].replace("\n", " ")
            print(f"  Desc     : {snippet}...")
    print("\n" + "=" * w)


def save_csv(jobs: list, path: str) -> None:
    fields = ["rank", "match_score", "title", "company", "location",
              "is_remote", "salary", "date_posted", "explanation",
              "description", "source", "url"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for i, job in enumerate(jobs, 1):
            writer.writerow({"rank": i, **job})
    print(f"\nResults saved to: {path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Match your resume to jobs using Adzuna, JSearch, and Claude AI."
    )
    parser.add_argument("resume", help="Path to your resume (.pdf or .txt)")
    parser.add_argument(
        "--keywords", default="",
        help="Job search keywords, e.g. 'software engineer python' (used by both sources)",
    )
    parser.add_argument(
        "--location", default="",
        help="Preferred location, e.g. 'New York' (soft preference, influences score)",
    )
    parser.add_argument(
        "--min-salary", type=int, metavar="AMOUNT",
        help="Preferred minimum annual salary (soft preference, influences score)",
    )
    parser.add_argument(
        "--work-type", choices=["remote", "hybrid", "in-person"],
        help="Preferred work arrangement (soft preference, influences score)",
    )
    parser.add_argument(
        "--days-ago", type=int, default=30, metavar="N",
        help="Prefer jobs posted within the last N days (soft preference, default: 30)",
    )
    parser.add_argument(
        "--country", default="us",
        help="Adzuna country code, e.g. us, gb, au, ca (default: us)",
    )
    parser.add_argument(
        "--fetch", type=int, default=20, metavar="N",
        help="Number of jobs to fetch from each source, max 50 (default: 20)",
    )
    parser.add_argument(
        "--top", type=int, default=10, metavar="N",
        help="Number of top matches to display (default: 10)",
    )
    parser.add_argument(
        "--output", default="job_matches.csv",
        help="CSV output filename (default: job_matches.csv)",
    )
    args = parser.parse_args()

    # --- API key validation ---
    adzuna_id     = os.environ.get("ADZUNA_APP_ID")
    adzuna_key    = os.environ.get("ADZUNA_APP_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    rapidapi_key  = os.environ.get("RAPIDAPI_KEY")

    missing = [name for name, val in [
        ("ADZUNA_APP_ID",     adzuna_id),
        ("ADZUNA_APP_KEY",    adzuna_key),
        ("ANTHROPIC_API_KEY", anthropic_key),
    ] if not val]
    if missing:
        print(f"Error: missing environment variable(s): {', '.join(missing)}")
        sys.exit(1)

    # --- Read resume ---
    print(f"Reading resume: {args.resume}")
    resume = read_resume(args.resume)
    if not resume:
        print("Error: could not extract any text from the resume file.")
        sys.exit(1)
    print(f"  Extracted {len(resume):,} characters.")

    # --- Build soft preferences for Claude scoring ---
    preferences = {
        "location":   args.location or None,
        "min_salary": args.min_salary,
        "work_type":  args.work_type,
        "days_ago":   args.days_ago,
    }

    # --- Search jobs from all sources ---
    all_jobs: list = []

    print(f"\nSearching Adzuna [{args.country.upper()}]...")
    adzuna_jobs = search_jobs_adzuna(
        adzuna_id, adzuna_key, args.country, args.keywords, args.fetch
    )
    print(f"  Found {len(adzuna_jobs)} job(s).")
    all_jobs.extend(adzuna_jobs)

    if rapidapi_key:
        query = args.keywords or "jobs"
        print(f"\nSearching JSearch (LinkedIn/Indeed/Glassdoor) — query: '{query}'...")
        jsearch_jobs = search_jobs_jsearch(rapidapi_key, query, args.fetch)
        print(f"  Found {len(jsearch_jobs)} job(s).")
        all_jobs.extend(jsearch_jobs)
    else:
        print("\nSkipping JSearch (RAPIDAPI_KEY not set — add it to .env to enable).")

    all_jobs = deduplicate_jobs(all_jobs)
    print(f"\nTotal unique jobs to score: {len(all_jobs)}")

    if not all_jobs:
        print("No jobs found. Try adding --keywords or checking your API credentials.")
        sys.exit(0)

    # --- Score with Claude ---
    client = anthropic.Anthropic(api_key=anthropic_key)
    print(f"\nScoring {len(all_jobs)} job(s) with Claude...")
    print("  (Resume is cached server-side after the first call.)\n")

    scored = []
    for i, job in enumerate(all_jobs, 1):
        title = job["title"][:55]
        print(f"  [{i:2}/{len(all_jobs)}] {title:<55}", end="", flush=True)
        try:
            score, explanation = score_job(client, resume, job, preferences)
            print(f"  {score}/10")
            scored.append({
                "title":       job["title"],
                "company":     job["company"],
                "location":    job["location"],
                "is_remote":   job.get("is_remote", False),
                "salary":      fmt_salary(job),
                "date_posted": fmt_date(job),
                "match_score": score,
                "explanation": explanation,
                "description": job.get("description", ""),
                "source":      job["source"],
                "url":         job["url"],
            })
        except json.JSONDecodeError:
            print("  [parse error — skipped]")
        except anthropic.APIError as e:
            print(f"  [Claude API error: {e}]")
        except Exception as e:
            print(f"  [error: {e}]")

    if not scored:
        print("\nNo jobs could be scored.")
        sys.exit(1)

    # --- Sort, display, save ---
    scored.sort(key=lambda x: x["match_score"], reverse=True)
    top = scored[: args.top]
    print_results(top)
    save_csv(top, args.output)


if __name__ == "__main__":
    main()
