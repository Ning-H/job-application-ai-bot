from flask import Flask, render_template_string, redirect, url_for, request
from src.models import Job, get_session, init_db
from datetime import datetime

app = Flask(__name__)

# ── helpers ──────────────────────────────────────────────────────────────────

def score_color(score):
    if score is None:
        return "secondary"
    if score >= 0.75:
        return "success"
    if score >= 0.55:
        return "warning"
    return "danger"

def job_type_icon(title):
    t = (title or "").lower()
    # Check manager/leadership first
    is_mgr = any(x in t for x in ["manager", "director", "head of", "vp of"])
    if is_mgr:
        return ("bi-people-fill", "text-warning", "Manager")
    if any(x in t for x in ["machine learning", " ml "]):
        return ("bi-cpu-fill", "text-info", "ML Engineer")
    if any(x in t for x in ["ai engineer", "ai deployment", "ai enablement", "applied ai", "forward deployed"]):
        return ("bi-stars", "text-primary", "AI Engineer")
    if "analytics engineer" in t:
        return ("bi-graph-up-arrow", "text-success", "Analytics Engineer")
    if "data engineer" in t:
        return ("bi-database-fill", "text-primary", "Data Engineer")
    if any(x in t for x in ["software engineer", "systems engineer", "platform engineer"]):
        return ("bi-code-slash", "text-secondary", "Software Engineer")
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
    # Returns safe HTML - no user input is interpolated
    if job.is_remote:
        return '<span class="badge bg-primary">Remote</span>'
    loc = (job.location or "").lower()
    if any(x in loc for x in ["san francisco", "bay area", "palo alto", "mountain view", "san jose"]):
        return '<span class="badge bg-info text-dark">Bay Area</span>'
    if any(x in loc for x in ["alexandria", "arlington", "washington", "virginia", "maryland", "dc"]):
        return '<span class="badge bg-success">DMV</span>'
    return '<span class="badge bg-secondary">Other</span>'

# ── base layout ──────────────────────────────────────────────────────────────

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
    body { background: #f8f9fa; }
    .job-card { transition: box-shadow .15s; cursor: pointer; }
    .job-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,.12); }
    .score-circle {
      width: 52px; height: 52px; border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      font-weight: 700; font-size: .9rem; flex-shrink: 0;
    }
    .navbar-brand { font-weight: 700; letter-spacing: -.5px; }
    .filter-bar { background: #fff; border-radius: 12px; padding: 1rem; margin-bottom: 1.5rem; }
    .stat-card { border-radius: 12px; text-align: center; padding: 1rem; }
  </style>
</head>
<body>
<nav class="navbar navbar-dark bg-dark mb-4">
  <div class="container">
    <a class="navbar-brand" href="/"><i class="bi bi-briefcase-fill me-2"></i>Job Dashboard</a>
    <span class="text-white-50 small">Ning Han · Job Search</span>
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
<!-- stats row -->
<div class="row g-3 mb-4">
  <div class="col-6 col-md-3">
    <div class="stat-card bg-white border">
      <div class="fs-2 fw-bold text-primary">{{ total }}</div>
      <div class="text-muted small">Total Jobs</div>
    </div>
  </div>
  <div class="col-6 col-md-3">
    <div class="stat-card bg-white border">
      <div class="fs-2 fw-bold text-success">{{ new_count }}</div>
      <div class="text-muted small">New</div>
    </div>
  </div>
  <div class="col-6 col-md-3">
    <div class="stat-card bg-white border">
      <div class="fs-2 fw-bold text-warning">{{ review_count }}</div>
      <div class="text-muted small">Need Review</div>
    </div>
  </div>
  <div class="col-6 col-md-3">
    <div class="stat-card bg-white border">
      <div class="fs-2 fw-bold text-info">{{ applied_count }}</div>
      <div class="text-muted small">Applied</div>
    </div>
  </div>
</div>

<!-- filters -->
<div class="filter-bar d-flex flex-wrap gap-2 align-items-center">
  <strong class="me-1">Filter:</strong>
  <a href="/?status=all" class="btn btn-sm {{ 'btn-dark' if status=='all' else 'btn-outline-secondary' }}">All</a>
  <a href="/?status=new" class="btn btn-sm {{ 'btn-dark' if status=='new' else 'btn-outline-secondary' }}">New</a>
  <a href="/?status=review" class="btn btn-sm {{ 'btn-dark' if status=='review' else 'btn-outline-secondary' }}">Review</a>
  <a href="/?status=applied" class="btn btn-sm {{ 'btn-dark' if status=='applied' else 'btn-outline-secondary' }}">Applied</a>
  <span class="text-muted ms-2">|</span>
  <a href="/?status={{ status }}&loc=all" class="btn btn-sm {{ 'btn-dark' if loc=='all' else 'btn-outline-secondary' }}">Any Location</a>
  <a href="/?status={{ status }}&loc=remote" class="btn btn-sm {{ 'btn-dark' if loc=='remote' else 'btn-outline-primary' }}">Remote</a>
  <a href="/?status={{ status }}&loc=dmv" class="btn btn-sm {{ 'btn-dark' if loc=='dmv' else 'btn-outline-success' }}">DMV</a>
  <a href="/?status={{ status }}&loc=bay" class="btn btn-sm {{ 'btn-dark' if loc=='bay' else 'btn-outline-info' }}">Bay Area</a>
</div>

<!-- job list -->
{% if not jobs %}
<div class="text-center py-5 text-muted">
  <i class="bi bi-inbox fs-1"></i>
  <p class="mt-2">No jobs found. Run <code>./run.sh once</code> to crawl.</p>
</div>
{% endif %}

{% for job in jobs %}
{% set icon, icon_color, job_type = job_type_icon(job.title) %}
<a href="/job/{{ job.job_id }}" class="text-decoration-none">
  <div class="card job-card mb-3 border-0 shadow-sm">
    <div class="card-body d-flex gap-3 align-items-start">
      <div class="d-flex flex-column align-items-center pt-1" style="width:42px;flex-shrink:0">
        <i class="bi {{ icon }} {{ icon_color }} fs-4"></i>
        <span class="text-muted" style="font-size:0.6rem;margin-top:2px">{{ job_type }}</span>
      </div>
      <div class="flex-grow-1 min-width-0">
        <div class="fw-semibold text-dark">{{ job.title }}</div>
        <div class="text-muted small mb-1">
          {{ job.company }}
          <span class="text-muted" style="font-size:0.7rem">· {{ format_source(job.source) }}</span>
        </div>
        <div class="d-flex flex-wrap gap-1 align-items-center">
          {{ location_badge(job) | safe }}
          {% if job.location %}<span class="text-muted small">{{ job.location }}</span>{% endif %}
          {% if job.salary_min or job.salary_max %}
          <span class="badge bg-success bg-opacity-75 text-white">
            ${{ "{:,}".format(job.salary_min or 0) }}{% if job.salary_max %} – ${{ "{:,}".format(job.salary_max) }}{% endif %}
          </span>
          {% endif %}
          {% if job.status == 'applied' %}
          <span class="badge bg-success">Applied</span>
          {% elif job.requires_human_review %}
          <span class="badge bg-warning text-dark">Review</span>
          {% elif job.auto_apply_eligible %}
          <span class="badge bg-info text-dark">Auto-apply</span>
          {% endif %}
          {% if job.posted_date %}
          {% set days_ago = (now - job.posted_date).days %}
          <span class="badge bg-light text-muted border small">
            {% if days_ago == 0 %}Today{% elif days_ago == 1 %}Yesterday{% else %}{{ days_ago }}d ago{% endif %}
          </span>
          {% endif %}
          {% if job.user_preference_score %}
          <span class="badge bg-dark small" title="Your rating">⭐ {{ job.user_preference_score|int }}/5</span>
          {% endif %}
        </div>
        {% if job.summary %}
        <div class="small mt-1" style="color:#444;">{{ job.summary[:180] }}{% if job.summary|length > 180 %}…{% endif %}</div>
        {% endif %}
      </div>
      <i class="bi bi-chevron-right text-muted mt-1"></i>
    </div>
  </div>
</a>
{% endfor %}
""")

DETAIL = BASE.replace("{% block content %}{% endblock %}", """
{% set icon, icon_color, job_type = job_type_icon(job.title) %}
<a href="/" class="btn btn-outline-secondary btn-sm mb-3"><i class="bi bi-arrow-left me-1"></i>Back</a>

<div class="card border-0 shadow-sm mb-3">
  <div class="card-body">
    <div class="d-flex justify-content-between align-items-start flex-wrap gap-2">
      <div>
        <div class="d-flex align-items-center gap-2 mb-1">
          <i class="bi {{ icon }} {{ icon_color }} fs-4"></i>
          <span class="badge bg-light text-dark border small">{{ job_type }}</span>
        </div>
        <h4 class="fw-bold mb-1">{{ job.title }}</h4>
        <div class="text-muted fs-5">{{ job.company }}</div>
      </div>
      <div class="text-end">
        <div class="fw-bold fs-4 text-{{ score_color(job.overall_score) }}">{{ "%.0f"|format((job.overall_score or 0)*100) }}<span class="fs-6 fw-normal text-muted">/100</span></div>
        <div class="text-muted small">LLM Score</div>
      </div>
    </div>

    <hr>

    <div class="row g-3 mb-3">
      <div class="col-6 col-md-3">
        <div class="text-muted small">Location</div>
        <div>{{ location_badge(job)|safe }} {{ job.location or '—' }}</div>
      </div>
      <div class="col-6 col-md-3">
        <div class="text-muted small">Salary</div>
        <div>{% if job.salary_min or job.salary_max %}${{ "{:,}".format(job.salary_min or 0) }}{% if job.salary_max %} – ${{ "{:,}".format(job.salary_max) }}{% endif %}{% else %}Not listed{% endif %}</div>
      </div>
      <div class="col-6 col-md-3">
        <div class="text-muted small">Source</div>
        <div>{{ format_source(job.source) }}</div>
      </div>
      <div class="col-6 col-md-3">
        <div class="text-muted small">Posted</div>
        <div>{{ job.posted_date.strftime('%b %d, %Y') if job.posted_date else '—' }}</div>
      </div>
    </div>

    <!-- score breakdown -->
    <div class="mb-3">
      <div class="text-muted small fw-semibold mb-2">Score Breakdown</div>
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

    <!-- action buttons -->
    <div class="d-flex flex-wrap gap-2 mb-3">
      {% if job.url %}
      <a href="{{ job.url }}" target="_blank" class="btn btn-primary"><i class="bi bi-box-arrow-up-right me-1"></i>View Job</a>
      {% endif %}
      {% if not job.applied %}
      <form method="post" action="/job/{{ job.job_id }}/apply" class="d-inline">
        <button class="btn btn-success"><i class="bi bi-check-lg me-1"></i>Mark Applied</button>
      </form>
      {% else %}
      <span class="btn btn-success disabled"><i class="bi bi-check-lg me-1"></i>Applied ✓</span>
      {% endif %}
      <form method="post" action="/job/{{ job.job_id }}/status" class="d-inline">
        <select name="status" class="form-select form-select-sm d-inline w-auto" onchange="this.form.submit()">
          <option value="">Set status…</option>
          <option value="interested" {{ 'selected' if job.status=='interested' }}>Interested</option>
          <option value="not_interested" {{ 'selected' if job.status=='not_interested' }}>Not Interested</option>
          <option value="new" {{ 'selected' if job.status=='new' }}>New</option>
        </select>
      </form>
    </div>

    {% if job.summary %}
    <div class="mb-3">
      <div class="text-muted small fw-semibold mb-1">Summary</div>
      <div class="bg-light rounded p-3">{{ job.summary }}</div>
    </div>
    {% endif %}

    <!-- User Feedback -->
    <div class="border rounded p-3 mb-3" style="background:#fafafa">
      <div class="fw-semibold mb-3"><i class="bi bi-star-fill text-warning me-1"></i>Your Ratings <span class="text-muted small fw-normal">(helps LLM improve future scores)</span></div>
      <form method="post" action="/job/{{ job.job_id }}/feedback">
        {% set dims = [
          ('user_skills_rating',   'skills_match_score',   'Skills Match',   '🔧'),
          ('user_company_rating',  'company_score',        'Company',         '🏢'),
          ('user_location_rating', 'location_score',       'Location',        '📍'),
          ('user_salary_rating',   'salary_score',         'Salary',          '💰'),
          ('user_preference_score', 'overall_score',       'Personal Fit',    '⭐'),
        ] %}
        {% for field, llm_field, label, emoji in dims %}
        <div class="mb-2">
          <div class="d-flex justify-content-between align-items-center mb-1">
            <label class="small fw-semibold">{{ emoji }} {{ label }}</label>
            <span class="text-muted small">LLM: {{ "%.0f"|format(((job[llm_field] or 0))*100) }}% &nbsp;|&nbsp; Yours: <span id="val_{{ field }}">{{ (job[field]|int) if job[field] else '—' }}</span>/5</span>
          </div>
          <input type="range" class="form-range" min="1" max="5" step="1"
            name="{{ field }}" value="{{ job[field]|int if job[field] else 3 }}"
            oninput="document.getElementById('val_{{ field }}').textContent=this.value">
        </div>
        {% endfor %}
        <div class="mb-2">
          <label class="small fw-semibold">📝 Notes (why you rated it this way)</label>
          <textarea name="user_notes" class="form-control form-control-sm mt-1" rows="2" placeholder="e.g. Great Spark stack but needs TS/SCI clearance...">{{ job.user_notes or '' }}</textarea>
        </div>
        <button type="submit" class="btn btn-dark btn-sm"><i class="bi bi-save me-1"></i>Save Feedback</button>
        {% if job.feedback_date %}<span class="text-muted small ms-2">Last saved {{ job.feedback_date.strftime('%b %d') }}</span>{% endif %}
      </form>
    </div>
    {% if job.description %}
    <div>
      <button class="btn btn-sm btn-outline-secondary mb-2" type="button" data-bs-toggle="collapse" data-bs-target="#fullDesc">
        <i class="bi bi-file-text me-1"></i>Full Description
      </button>
      <div class="collapse" id="fullDesc">
        <div class="bg-light rounded p-3 small" style="white-space:pre-wrap; max-height:500px; overflow-y:auto">{{ job.description }}</div>
      </div>
    </div>
    {% endif %}
  </div>
</div>
""")


# ── routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    session = get_session()
    try:
        status = request.args.get("status", "all")
        loc = request.args.get("loc", "all")

        q = session.query(Job)

        if status == "new":
            q = q.filter(Job.status == "new")
        elif status == "review":
            q = q.filter(Job.requires_human_review == True)
        elif status == "applied":
            q = q.filter(Job.applied == True)

        jobs = q.order_by(Job.overall_score.desc().nullslast(), Job.posted_date.desc().nullslast()).all()

        if loc == "remote":
            jobs = [j for j in jobs if j.is_remote]
        elif loc == "dmv":
            jobs = [j for j in jobs if j.location and any(
                x in j.location.lower() for x in ["alexandria", "arlington", "washington", "virginia", "maryland", "dc"]
            )]
        elif loc == "bay":
            jobs = [j for j in jobs if j.location and any(
                x in j.location.lower() for x in ["san francisco", "bay area", "palo alto", "mountain view", "san jose"]
            )]

        total = session.query(Job).count()
        new_count = session.query(Job).filter(Job.status == "new").count()
        review_count = session.query(Job).filter(Job.requires_human_review == True).count()
        applied_count = session.query(Job).filter(Job.applied == True).count()
        
        return render_template_string(
            INDEX,
            jobs=jobs,
            total=total,
            new_count=new_count,
            review_count=review_count,
            applied_count=applied_count,
            status=status,
            loc=loc,
            score_color=score_color,
            location_badge=location_badge,
            job_type_icon=job_type_icon,
            format_source=format_source,
            now=datetime.utcnow(),
        )
    finally:
        session.close()


@app.route("/job/<job_id>")
def job_detail(job_id):
    session = get_session()
    try:
        job = session.query(Job).filter_by(job_id=job_id).first()
        if not job:
            return "Job not found", 404
        return render_template_string(
            DETAIL,
            job=job,
            score_color=score_color,
            location_badge=location_badge,
            job_type_icon=job_type_icon,
            format_source=format_source,
        )
    finally:
        session.close()


@app.route("/job/<job_id>/apply", methods=["POST"])
def mark_applied(job_id):
    session = get_session()
    try:
        job = session.query(Job).filter_by(job_id=job_id).first()
        if job:
            job.applied = True
            job.applied_date = datetime.utcnow()
            job.status = "applied"
            session.commit()
        return redirect(url_for("job_detail", job_id=job_id))
    finally:
        session.close()


@app.route("/job/<job_id>/feedback", methods=["POST"])
def save_feedback(job_id):
    session = get_session()
    try:
        job = session.query(Job).filter_by(job_id=job_id).first()
        if job:
            for field in ["user_skills_rating", "user_company_rating",
                          "user_location_rating", "user_salary_rating", "user_preference_score"]:
                val = request.form.get(field)
                if val:
                    try:
                        setattr(job, field, float(val))
                    except (ValueError, TypeError):
                        pass
            job.user_notes = request.form.get("user_notes", "").strip() or None
            job.feedback_date = datetime.utcnow()
            session.commit()
        return redirect(url_for("job_detail", job_id=job_id))
    finally:
        session.close()


@app.route("/job/<job_id>/status", methods=["POST"])
def set_status(job_id):
    session = get_session()
    try:
        job = session.query(Job).filter_by(job_id=job_id).first()
        new_status = request.form.get("status")
        if job and new_status:
            job.status = new_status
            session.commit()
        return redirect(url_for("job_detail", job_id=job_id))
    finally:
        session.close()


if __name__ == "__main__":
    init_db()
    print("\n  Job Dashboard running at http://localhost:8080")
    print("  On your phone (anywhere):  http://100.108.214.18:8080\n")
    app.run(host="0.0.0.0", port=8080, debug=False)
