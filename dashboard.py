from datetime import datetime, timedelta

from flask import Flask, redirect, render_template_string, request, url_for
from sqlalchemy import or_

from src.config_loader import config
from src.job_board import board_rank_score, fit_score, is_new_job, relative_time
from src.models import Job, get_session, init_db

app = Flask(__name__)


def score_color(score):
    if score is None:
        return "secondary"
    if score >= 0.8:
        return "success"
    if score >= 0.65:
        return "warning"
    return "danger"


def job_type_icon(title):
    t = (title or "").lower()
    if any(x in t for x in ["manager", "director", "head of", "vp of"]):
        return ("bi-people-fill", "text-warning", "Leadership")
    if any(x in t for x in ["analytics engineer", "analytics platform"]):
        return ("bi-graph-up-arrow", "text-success", "Analytics")
    if any(x in t for x in ["data engineer", "data platform", "data infrastructure", "data infra"]):
        return ("bi-database-fill", "text-primary", "Data")
    if any(x in t for x in ["ai engineer", "applied ai", "ai platform", "ai enablement"]):
        return ("bi-stars", "text-primary", "AI")
    if any(x in t for x in ["machine learning", " ml ", "ml engineer", "ml platform"]):
        return ("bi-cpu-fill", "text-info", "ML")
    if any(x in t for x in ["software engineer", "systems engineer", "platform engineer"]):
        return ("bi-code-slash", "text-secondary", "Platform")
    return ("bi-briefcase-fill", "text-secondary", "Other")


def format_source(source):
    if not source:
        return "—"
    ats_map = {"greenhouse": "Greenhouse", "ashby": "Ashby", "lever": "Lever"}
    if ":" in source:
        ats, company = source.split(":", 1)
        return f"{company} · {ats_map.get(ats, ats.title())}"
    if source.startswith("job_board_"):
        return source.replace("job_board_", "").title()
    if source.startswith("company_"):
        return source.replace("company_", "")
    return source


def location_badge(job):
    if job.is_remote:
        return '<span class="badge bg-primary-subtle text-primary border border-primary-subtle">Remote</span>'
    loc = (job.location or "").lower()
    if any(x in loc for x in ["san francisco", "bay area", "palo alto", "mountain view", "san jose"]):
        return '<span class="badge bg-info-subtle text-info-emphasis border border-info-subtle">Bay Area</span>'
    if any(x in loc for x in ["alexandria", "arlington", "washington", "virginia", "maryland", "dc"]):
        return '<span class="badge bg-success-subtle text-success border border-success-subtle">DMV</span>'
    return '<span class="badge bg-secondary-subtle text-secondary border border-secondary-subtle">Other US</span>'


def false_or_null(column):
    return or_(column == False, column == None)


def location_matches(job, loc_filter):
    if loc_filter == "all":
        return True
    loc = (job.location or "").lower()
    if loc_filter == "remote":
        return bool(job.is_remote)
    if loc_filter == "dmv":
        return any(x in loc for x in ["alexandria", "arlington", "washington", "virginia", "maryland", "dc"])
    if loc_filter == "bay":
        return any(x in loc for x in ["san francisco", "bay area", "palo alto", "mountain view", "san jose"])
    return True


def mark_reviewed(job, now=None, external_view=False):
    now = now or datetime.utcnow()
    job.reviewed_at = job.reviewed_at or now
    if external_view:
        job.last_viewed_at = now
        job.view_count = (job.view_count or 0) + 1
    if job.status in (None, "", "new"):
        job.status = "reviewed"


BASE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Job Search Dashboard</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
  <style>
    :root {
      --bg: #f4f6fb;
      --panel: #ffffff;
      --ink: #13233a;
      --muted: #627086;
      --accent: #0b6bcb;
      --accent-soft: #e7f1ff;
      --warm: #fff4d6;
      --warm-text: #8c5d00;
      --new: #d63384;
      --new-soft: #fde7f3;
    }
    body {
      background:
        radial-gradient(circle at top left, rgba(11, 107, 203, 0.10), transparent 28%),
        radial-gradient(circle at top right, rgba(214, 51, 132, 0.10), transparent 24%),
        var(--bg);
      color: var(--ink);
    }
    .navbar-brand { font-weight: 700; letter-spacing: -0.02em; }
    .surface {
      background: var(--panel);
      border: 1px solid rgba(19, 35, 58, 0.08);
      border-radius: 18px;
      box-shadow: 0 18px 50px rgba(19, 35, 58, 0.08);
    }
    .hero {
      padding: 1.4rem;
      margin-bottom: 1rem;
      background:
        linear-gradient(135deg, rgba(11, 107, 203, 0.10), rgba(214, 51, 132, 0.08)),
        var(--panel);
    }
    .stat-card {
      padding: 1rem;
      border-radius: 16px;
      background: var(--panel);
      border: 1px solid rgba(19, 35, 58, 0.08);
      text-align: center;
      height: 100%;
    }
    .filter-bar {
      padding: 1rem;
      margin-bottom: 1rem;
    }
    .job-card {
      border: 0;
      border-radius: 18px;
      transition: transform .14s ease, box-shadow .14s ease;
      background: var(--panel);
    }
    .job-card:hover {
      transform: translateY(-2px);
      box-shadow: 0 18px 40px rgba(19, 35, 58, 0.12);
    }
    .score-pill {
      min-width: 74px;
      border-radius: 999px;
      padding: .45rem .7rem;
      text-align: center;
      font-weight: 700;
      background: var(--accent-soft);
      color: var(--accent);
    }
    .summary-copy { color: #3b485b; line-height: 1.45; }
    .meta-line { color: var(--muted); font-size: 0.9rem; }
    .new-badge {
      background: var(--new-soft);
      color: var(--new);
      border: 1px solid rgba(214, 51, 132, 0.18);
    }
    .top-fit {
      background: var(--warm);
      color: var(--warm-text);
      border: 1px solid rgba(140, 93, 0, 0.14);
    }
    .detail-label {
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--muted);
    }
  </style>
</head>
<body>
<nav class="navbar navbar-dark bg-dark mb-4">
  <div class="container">
    <a class="navbar-brand" href="/"><i class="bi bi-briefcase-fill me-2"></i>Job Dashboard</a>
    <span class="text-white-50 small">Direct career sites · ranked for Ning</span>
  </div>
</nav>
<div class="container pb-5">
  {% block content %}{% endblock %}
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

INDEX = BASE.replace("{% block content %}{% endblock %}", """
<div class="surface hero">
  <div class="d-flex flex-wrap justify-content-between gap-3 align-items-start">
    <div>
      <div class="text-uppercase small text-muted fw-semibold mb-1">Priority Board</div>
      <h2 class="mb-1">Best-fit jobs first</h2>
      <div class="meta-line">Fresh direct-career jobs from the last two weeks, ranked for your data engineering profile.</div>
    </div>
    <div class="meta-line text-end">
      <div>Pull cadence: every {{ crawl_hours }}h</div>
      <div>Last board refresh: {{ now.strftime('%b %d, %Y %I:%M %p') }}</div>
    </div>
  </div>
</div>

<div class="row g-3 mb-4">
  <div class="col-6 col-md">
    <div class="stat-card">
      <div class="fs-3 fw-bold text-primary">{{ active_count }}</div>
      <div class="text-muted small">Active Jobs</div>
    </div>
  </div>
  <div class="col-6 col-md">
    <div class="stat-card">
      <div class="fs-3 fw-bold" style="color:var(--new)">{{ new_count }}</div>
      <div class="text-muted small">New Pulls</div>
    </div>
  </div>
  <div class="col-6 col-md">
    <div class="stat-card">
      <div class="fs-3 fw-bold text-success">{{ reviewed_count }}</div>
      <div class="text-muted small">Reviewed</div>
    </div>
  </div>
  <div class="col-6 col-md">
    <div class="stat-card">
      <div class="fs-3 fw-bold text-warning">{{ review_count }}</div>
      <div class="text-muted small">Strong Matches</div>
    </div>
  </div>
  <div class="col-6 col-md">
    <div class="stat-card">
      <div class="fs-3 fw-bold text-info">{{ applied_count }}</div>
      <div class="text-muted small">Applied</div>
    </div>
  </div>
</div>

<div class="surface filter-bar">
  <div class="d-flex flex-wrap gap-2 align-items-center mb-2">
    <strong class="me-1">Board:</strong>
    <a href="/?status=all&loc={{ loc }}" class="btn btn-sm {{ 'btn-dark' if status=='all' else 'btn-outline-secondary' }}">All Active</a>
    <a href="/?status=new&loc={{ loc }}" class="btn btn-sm {{ 'btn-dark' if status=='new' else 'btn-outline-secondary' }}">Unreviewed</a>
    <a href="/?status=reviewed&loc={{ loc }}" class="btn btn-sm {{ 'btn-dark' if status=='reviewed' else 'btn-outline-secondary' }}">Reviewed</a>
    <a href="/?status=review&loc={{ loc }}" class="btn btn-sm {{ 'btn-dark' if status=='review' else 'btn-outline-secondary' }}">Top Matches</a>
    <a href="/?status=applied&loc={{ loc }}" class="btn btn-sm {{ 'btn-dark' if status=='applied' else 'btn-outline-secondary' }}">Applied</a>
    <a href="/?status=not_fit&loc={{ loc }}" class="btn btn-sm {{ 'btn-dark' if status=='not_fit' else 'btn-outline-secondary' }}">Not Fit</a>
  </div>
  <div class="d-flex flex-wrap gap-2 align-items-center">
    <strong class="me-1">Location:</strong>
    <a href="/?status={{ status }}&loc=all" class="btn btn-sm {{ 'btn-dark' if loc=='all' else 'btn-outline-secondary' }}">Any US</a>
    <a href="/?status={{ status }}&loc=remote" class="btn btn-sm {{ 'btn-dark' if loc=='remote' else 'btn-outline-primary' }}">Remote</a>
    <a href="/?status={{ status }}&loc=dmv" class="btn btn-sm {{ 'btn-dark' if loc=='dmv' else 'btn-outline-success' }}">DMV</a>
    <a href="/?status={{ status }}&loc=bay" class="btn btn-sm {{ 'btn-dark' if loc=='bay' else 'btn-outline-info' }}">Bay Area</a>
  </div>
</div>

{% if not jobs %}
<div class="surface p-5 text-center text-muted">
  <i class="bi bi-inbox fs-1"></i>
  <p class="mt-3 mb-0">No jobs match this view right now. Run <code>./run.sh once</code> to pull a fresh batch.</p>
</div>
{% endif %}

{% for job in jobs %}
{% set icon, icon_color, job_type = job_type_icon(job.title) %}
{% set board_score = board_rank_score(job, now) %}
{% set board_fit = fit_score(job, now) %}
<a href="/job/{{ job.job_id }}" class="text-decoration-none">
  <div class="card job-card mb-3 surface">
    <div class="card-body p-4">
      <div class="d-flex flex-wrap gap-3 align-items-start">
        <div class="d-flex flex-column align-items-center pt-1" style="width:48px;flex-shrink:0">
          <i class="bi {{ icon }} {{ icon_color }} fs-3"></i>
          <span class="text-muted text-center" style="font-size:0.68rem;margin-top:4px">{{ job_type }}</span>
        </div>
        <div class="flex-grow-1">
          <div class="d-flex flex-wrap justify-content-between gap-3">
            <div>
              <div class="fw-semibold fs-5 text-dark">{{ job.title }}</div>
              <div class="meta-line mb-2">{{ job.company }} · {{ format_source(job.source) }}</div>
            </div>
            <div class="score-pill">
              {{ "%.0f"|format(board_fit * 100) }}
              <div class="small fw-normal">fit</div>
            </div>
          </div>

          <div class="d-flex flex-wrap gap-2 align-items-center mb-2">
            {{ location_badge(job) | safe }}
            {% if job.location %}<span class="meta-line">{{ job.location }}</span>{% endif %}
            {% if is_new_job(job, now) %}
            <span class="badge new-badge">NEW</span>
            {% endif %}
            {% if board_score >= 0.8 and not job.applied %}
            <span class="badge top-fit">Top Match</span>
            {% endif %}
            {% if job.reviewed_at and not job.applied %}
            <span class="badge bg-light text-dark border">Reviewed</span>
            {% endif %}
            {% if job.applied %}
            <span class="badge bg-success">Applied</span>
            {% endif %}
            {% if job.salary_min or job.salary_max %}
            <span class="badge bg-success-subtle text-success border border-success-subtle">
              ${{ "{:,}".format(job.salary_min or 0) }}{% if job.salary_max %} - ${{ "{:,}".format(job.salary_max) }}{% endif %}
            </span>
            {% endif %}
            {% if job.posted_date %}
            <span class="badge bg-light text-muted border">Posted {{ relative_time(job.posted_date, now) }}</span>
            {% endif %}
            <span class="badge bg-light text-muted border">Pulled {{ relative_time(job.last_seen_at or job.discovered_date, now) }}</span>
            {% if job.view_count %}
            <span class="badge bg-light text-muted border">{{ job.view_count }} job views</span>
            {% endif %}
            {% if job.user_preference_score %}
            <span class="badge bg-dark">Your rating {{ job.user_preference_score|int }}/5</span>
            {% endif %}
          </div>

          {% if job.summary %}
          <div class="summary-copy">{{ job.summary[:220] }}{% if job.summary|length > 220 %}…{% endif %}</div>
          {% elif job.description %}
          <div class="summary-copy">{{ job.description[:220] }}{% if job.description|length > 220 %}…{% endif %}</div>
          {% endif %}
        </div>
      </div>
    </div>
  </div>
</a>
{% endfor %}
""")

DETAIL = BASE.replace("{% block content %}{% endblock %}", """
{% set icon, icon_color, job_type = job_type_icon(job.title) %}
{% set board_score = board_rank_score(job, now) %}
{% set board_fit = fit_score(job, now) %}

<a href="/?status={{ status }}&loc={{ loc }}" class="btn btn-outline-secondary btn-sm mb-3"><i class="bi bi-arrow-left me-1"></i>Back to board</a>

<div class="surface p-4 mb-3">
  <div class="d-flex flex-wrap justify-content-between gap-3 align-items-start">
    <div>
      <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
        <i class="bi {{ icon }} {{ icon_color }} fs-3"></i>
        <span class="badge bg-light text-dark border">{{ job_type }}</span>
        {% if is_new_job(job, now) %}<span class="badge new-badge">NEW</span>{% endif %}
        {% if job.reviewed_at %}<span class="badge bg-light text-dark border">Reviewed</span>{% endif %}
        {% if job.applied %}<span class="badge bg-success">Applied</span>{% endif %}
        {% if job.not_fit %}<span class="badge bg-danger">Not Fit</span>{% endif %}
      </div>
      <h2 class="fw-bold mb-1">{{ job.title }}</h2>
      <div class="fs-5 text-muted">{{ job.company }}</div>
    </div>
    <div class="text-end">
      <div class="detail-label mb-1">Board Score</div>
      <div class="fw-bold fs-2 text-{{ score_color(board_fit) }}">{{ "%.0f"|format(board_fit * 100) }}</div>
      <div class="text-muted small">ranked for you</div>
    </div>
  </div>
</div>

<div class="surface p-4 mb-3">
  <div class="row g-3">
    <div class="col-6 col-md-3">
      <div class="detail-label">Location</div>
      <div>{{ location_badge(job) | safe }} {% if job.location %}<span class="ms-1">{{ job.location }}</span>{% else %}—{% endif %}</div>
    </div>
    <div class="col-6 col-md-3">
      <div class="detail-label">Salary</div>
      <div>{% if job.salary_min or job.salary_max %}${{ "{:,}".format(job.salary_min or 0) }}{% if job.salary_max %} - ${{ "{:,}".format(job.salary_max) }}{% endif %}{% else %}Not listed{% endif %}</div>
    </div>
    <div class="col-6 col-md-3">
      <div class="detail-label">Posted</div>
      <div>{{ job.posted_date.strftime('%b %d, %Y') if job.posted_date else '—' }}</div>
    </div>
    <div class="col-6 col-md-3">
      <div class="detail-label">Source</div>
      <div>{{ format_source(job.source) }}</div>
    </div>
    <div class="col-6 col-md-3">
      <div class="detail-label">First Pulled</div>
      <div>{{ job.first_seen_at.strftime('%b %d, %Y %I:%M %p') if job.first_seen_at else '—' }}</div>
    </div>
    <div class="col-6 col-md-3">
      <div class="detail-label">Last Pulled</div>
      <div>{{ job.last_seen_at.strftime('%b %d, %Y %I:%M %p') if job.last_seen_at else '—' }}</div>
    </div>
    <div class="col-6 col-md-3">
      <div class="detail-label">Reviewed</div>
      <div>{{ job.reviewed_at.strftime('%b %d, %Y %I:%M %p') if job.reviewed_at else 'No' }}</div>
    </div>
    <div class="col-6 col-md-3">
      <div class="detail-label">External Views</div>
      <div>{{ job.view_count or 0 }}</div>
    </div>
  </div>
</div>

<div class="surface p-4 mb-3">
  <div class="d-flex flex-wrap gap-2 mb-3">
    {% if job.url %}
    <a href="/job/{{ job.job_id }}/open?status={{ status }}&loc={{ loc }}" target="_blank" class="btn btn-primary"><i class="bi bi-box-arrow-up-right me-1"></i>View Job</a>
    {% endif %}
    {% if not job.applied %}
    <form method="post" action="/job/{{ job.job_id }}/apply?status={{ status }}&loc={{ loc }}" class="d-inline">
      <button class="btn btn-success"><i class="bi bi-check-lg me-1"></i>Mark Applied</button>
    </form>
    {% else %}
    <span class="btn btn-success disabled"><i class="bi bi-check-lg me-1"></i>Applied</span>
    {% endif %}
    <form method="post" action="/job/{{ job.job_id }}/status?status={{ status }}&loc={{ loc }}" class="d-inline">
      <select name="status" class="form-select d-inline w-auto" onchange="this.form.submit()">
        <option value="">Set status…</option>
        <option value="new" {{ 'selected' if job.status == 'new' }}>New</option>
        <option value="reviewed" {{ 'selected' if job.status == 'reviewed' }}>Reviewed</option>
        <option value="interested" {{ 'selected' if job.status == 'interested' }}>Interested</option>
      </select>
    </form>
  </div>

  <div class="row g-3">
    <div class="col-12 col-lg-7">
      {% if job.summary %}
      <div class="mb-3">
        <div class="detail-label mb-1">Why This Could Fit</div>
        <div class="bg-light rounded-4 p-3 summary-copy">{{ job.summary }}</div>
      </div>
      {% endif %}

      <div class="mb-3">
        <div class="detail-label mb-2">Score Breakdown</div>
        <div class="row g-2">
          {% for label, val in [('Skills Match', job.skills_match_score), ('Salary Fit', job.salary_score), ('Company', job.company_score), ('Location', job.location_score)] %}
          <div class="col-6 col-md-3">
            <div class="small text-muted">{{ label }}</div>
            <div class="progress" style="height:8px">
              <div class="progress-bar bg-{{ score_color(val) }}" style="width:{{ ((val or 0)*100)|int }}%"></div>
            </div>
            <div class="small fw-semibold">{{ "%.0f"|format((val or 0)*100) }}%</div>
          </div>
          {% endfor %}
        </div>
      </div>

      {% if job.description %}
      <div>
        <button class="btn btn-sm btn-outline-secondary mb-2" type="button" data-bs-toggle="collapse" data-bs-target="#fullDesc">
          <i class="bi bi-file-text me-1"></i>Full Description
        </button>
        <div class="collapse show" id="fullDesc">
          <div class="bg-light rounded-4 p-3 small" style="white-space:pre-wrap; max-height:500px; overflow-y:auto">{{ job.description }}</div>
        </div>
      </div>
      {% endif %}
    </div>

    <div class="col-12 col-lg-5">
      <div class="border rounded-4 p-3 mb-3" style="background:#fafafa">
        <div class="fw-semibold mb-3"><i class="bi bi-star-fill text-warning me-1"></i>Your Ratings <span class="text-muted small fw-normal">(used to improve future ranking)</span></div>
        <form method="post" action="/job/{{ job.job_id }}/feedback?status={{ status }}&loc={{ loc }}">
          {% set dims = [
            ('user_skills_rating', 'skills_match_score', 'Skills Match'),
            ('user_company_rating', 'company_score', 'Company'),
            ('user_location_rating', 'location_score', 'Location'),
            ('user_salary_rating', 'salary_score', 'Salary'),
            ('user_preference_score', 'overall_score', 'Personal Fit'),
          ] %}
          {% for field, llm_field, label in dims %}
          <div class="mb-2">
            <div class="d-flex justify-content-between align-items-center mb-1">
              <label class="small fw-semibold">{{ label }}</label>
              <span class="text-muted small">LLM {{ "%.0f"|format(((job[llm_field] or 0))*100) }}% · Yours <span id="val_{{ field }}">{{ (job[field]|int) if job[field] else '—' }}</span>/5</span>
            </div>
            <input type="range" class="form-range" min="1" max="5" step="1"
              name="{{ field }}" value="{{ job[field]|int if job[field] else 3 }}"
              oninput="document.getElementById('val_{{ field }}').textContent=this.value">
          </div>
          {% endfor %}
          <div class="mb-2">
            <label class="small fw-semibold">Notes</label>
            <textarea name="user_notes" class="form-control form-control-sm mt-1" rows="3" placeholder="What makes this a strong fit, or what is missing?">{{ job.user_notes or '' }}</textarea>
          </div>
          <button type="submit" class="btn btn-dark btn-sm"><i class="bi bi-save me-1"></i>Save Feedback</button>
          {% if job.feedback_date %}<span class="text-muted small ms-2">Saved {{ job.feedback_date.strftime('%b %d, %I:%M %p') }}</span>{% endif %}
        </form>
      </div>

      <div class="border rounded-4 p-3" style="background:#fff9f9">
        <div class="fw-semibold mb-2 text-danger"><i class="bi bi-x-circle me-1"></i>Not Fit</div>
        <div class="text-muted small mb-2">Remove this job from the main board and teach the ranking system what to avoid next time.</div>
        <form method="post" action="/job/{{ job.job_id }}/not-fit?status={{ status }}&loc={{ loc }}">
          <textarea name="reason" class="form-control form-control-sm mb-2" rows="3" placeholder="Example: too ML-modeling heavy, not enough data engineering, wrong domain, salary too low">{{ job.not_fit_reason or '' }}</textarea>
          <button class="btn btn-outline-danger btn-sm">Mark Not Fit</button>
        </form>
        {% if job.not_fit_reason %}
        <div class="small text-muted mt-2">Current reason: {{ job.not_fit_reason }}</div>
        {% endif %}
      </div>
    </div>
  </div>
</div>
""")


def base_board_query(session):
    recent_cutoff = datetime.utcnow() - timedelta(days=14)
    return session.query(Job).filter(
        false_or_null(Job.hidden),
        false_or_null(Job.not_fit),
        or_(Job.posted_date == None, Job.posted_date >= recent_cutoff),
    )


@app.route("/")
def index():
    session = get_session()
    now = datetime.utcnow()
    try:
        status = request.args.get("status", "all")
        loc = request.args.get("loc", "all")

        if status == "not_fit":
            jobs = session.query(Job).filter(or_(Job.not_fit == True, Job.hidden == True)).all()
        elif status == "applied":
            jobs = base_board_query(session).filter(Job.applied == True).all()
        else:
            q = base_board_query(session).filter(false_or_null(Job.applied))
            if status == "new":
                q = q.filter(or_(Job.reviewed_at == None, Job.status == "new"))
            elif status == "reviewed":
                q = q.filter(Job.reviewed_at != None)
            elif status == "review":
                q = q.filter(Job.requires_human_review == True)
            jobs = q.all()

        jobs = [job for job in jobs if location_matches(job, loc)]
        jobs = sorted(
            jobs,
            key=lambda job: (board_rank_score(job, now), job.last_seen_at or job.discovered_date or datetime.min),
            reverse=True,
        )

        board_jobs = base_board_query(session).all()
        active_jobs = [job for job in board_jobs if not job.applied]
        active_count = len(active_jobs)
        new_count = sum(1 for job in active_jobs if is_new_job(job, now))
        reviewed_count = sum(1 for job in active_jobs if job.reviewed_at is not None)
        review_count = sum(1 for job in active_jobs if job.requires_human_review)
        applied_count = session.query(Job).filter(Job.applied == True).count()

        return render_template_string(
            INDEX,
            jobs=jobs,
            active_count=active_count,
            new_count=new_count,
            reviewed_count=reviewed_count,
            review_count=review_count,
            applied_count=applied_count,
            status=status,
            loc=loc,
            now=now,
            crawl_hours=config.get_crawl_frequency_hours(),
            score_color=score_color,
            location_badge=location_badge,
            job_type_icon=job_type_icon,
            format_source=format_source,
            board_rank_score=board_rank_score,
            fit_score=fit_score,
            is_new_job=is_new_job,
            relative_time=relative_time,
        )
    finally:
        session.close()


@app.route("/job/<job_id>")
def job_detail(job_id):
    session = get_session()
    try:
        status = request.args.get("status", "all")
        loc = request.args.get("loc", "all")
        job = session.query(Job).filter_by(job_id=job_id).first()
        if not job:
            return "Job not found", 404

        mark_reviewed(job)
        session.commit()

        return render_template_string(
            DETAIL,
            job=job,
            status=status,
            loc=loc,
            now=datetime.utcnow(),
            score_color=score_color,
            location_badge=location_badge,
            job_type_icon=job_type_icon,
            format_source=format_source,
            board_rank_score=board_rank_score,
            fit_score=fit_score,
            is_new_job=is_new_job,
        )
    finally:
        session.close()


@app.route("/job/<job_id>/open")
def open_job(job_id):
    session = get_session()
    try:
        job = session.query(Job).filter_by(job_id=job_id).first()
        if not job or not job.url:
            return redirect(url_for("job_detail", job_id=job_id))

        mark_reviewed(job, external_view=True)
        session.commit()
        return redirect(job.url)
    finally:
        session.close()


@app.route("/job/<job_id>/apply", methods=["POST"])
def mark_applied(job_id):
    session = get_session()
    try:
        job = session.query(Job).filter_by(job_id=job_id).first()
        if job:
            now = datetime.utcnow()
            mark_reviewed(job, now=now, external_view=True)
            job.applied = True
            job.applied_date = now
            job.status = "applied"
            session.commit()
        return redirect(url_for("job_detail", job_id=job_id, status=request.args.get("status", "all"), loc=request.args.get("loc", "all")))
    finally:
        session.close()


@app.route("/job/<job_id>/feedback", methods=["POST"])
def save_feedback(job_id):
    session = get_session()
    try:
        job = session.query(Job).filter_by(job_id=job_id).first()
        if job:
            mark_reviewed(job)
            for field in [
                "user_skills_rating",
                "user_company_rating",
                "user_location_rating",
                "user_salary_rating",
                "user_preference_score",
            ]:
                val = request.form.get(field)
                if val:
                    try:
                        setattr(job, field, float(val))
                    except (ValueError, TypeError):
                        pass
            job.user_notes = request.form.get("user_notes", "").strip() or None
            job.feedback_date = datetime.utcnow()
            session.commit()
        return redirect(url_for("job_detail", job_id=job_id, status=request.args.get("status", "all"), loc=request.args.get("loc", "all")))
    finally:
        session.close()


@app.route("/job/<job_id>/status", methods=["POST"])
def set_status(job_id):
    session = get_session()
    try:
        job = session.query(Job).filter_by(job_id=job_id).first()
        new_status = request.form.get("status")
        if job and new_status:
            if new_status == "new":
                job.reviewed_at = None
                job.status = "new"
            else:
                mark_reviewed(job)
                job.status = new_status
            if new_status != "not_fit":
                job.hidden = False
                job.not_fit = False
            session.commit()
        return redirect(url_for("job_detail", job_id=job_id, status=request.args.get("status", "all"), loc=request.args.get("loc", "all")))
    finally:
        session.close()


@app.route("/job/<job_id>/not-fit", methods=["POST"])
def mark_not_fit(job_id):
    session = get_session()
    try:
        job = session.query(Job).filter_by(job_id=job_id).first()
        if job:
            now = datetime.utcnow()
            reason = request.form.get("reason", "").strip()
            mark_reviewed(job, now=now)
            job.not_fit = True
            job.hidden = True
            job.status = "not_fit"
            job.not_fit_reason = reason or None
            job.hidden_reason = reason or job.hidden_reason
            job.not_fit_feedback_at = now
            if job.user_preference_score is None:
                job.user_preference_score = 1
            if reason and not job.user_notes:
                job.user_notes = reason
            if job.feedback_date is None:
                job.feedback_date = now
            session.commit()
        return redirect(url_for("index"))
    finally:
        session.close()


if __name__ == "__main__":
    init_db()
    print("\n  Job Dashboard running at http://localhost:8080")
    app.run(host="0.0.0.0", port=8080, debug=False)
