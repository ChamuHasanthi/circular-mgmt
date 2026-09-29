"""Compliance analytics dashboard (FR-31 to FR-35). Manager/Administrator only."""
import csv
import io
from datetime import datetime

from flask import Blueprint, jsonify, request, send_file, current_app
from flask_jwt_extended import jwt_required
from sqlalchemy import func, case

from ..extensions import db
from ..models.circular import Circular, Summary, Classification
from ..models.identity import User, Department
from ..models.engagement import Acknowledgement
from ..services.security import roles_required
from ..services.compliance_report import build_compliance_pdf

dashboard_bp = Blueprint("dashboard", __name__)

_PENDING = ("Unread", "Read")
# case() expressions reused across the per-group aggregations.
_ACK_SUM = func.sum(case((Acknowledgement.status == "Acknowledged", 1), else_=0))
_LATE_SUM = func.sum(case((Acknowledgement.is_late.is_(True), 1), else_=0))
_PENDING_SUM = func.sum(case((Acknowledgement.status.in_(_PENDING), 1), else_=0))


@dashboard_bp.get("/overview")
@jwt_required()
@roles_required("Manager", "Administrator")
def overview():
    """FR-31: real-time totals + per-department compliance breakdown."""
    total = Acknowledgement.query.count()
    acknowledged = Acknowledgement.query.filter_by(status="Acknowledged").count()
    read = Acknowledgement.query.filter_by(status="Read").count()
    unread = Acknowledgement.query.filter_by(status="Unread").count()
    overdue = Acknowledgement.query.filter_by(is_late=True).count()
    published = Circular.query.filter_by(status="published").count()

    # Per-department breakdown (acks belong to a user, who belongs to a department).
    rows = (db.session.query(
                Department.name,
                func.count(Acknowledgement.id),
                _ACK_SUM, _PENDING_SUM, _LATE_SUM)
            .join(User, User.department_id == Department.id)
            .join(Acknowledgement, Acknowledgement.user_id == User.id)
            .group_by(Department.id)
            .all())
    by_department = [
        {"department": name, "total": int(t or 0), "acknowledged": int(a or 0),
         "pending": int(p or 0), "overdue": int(l or 0),
         "rate": round(100 * (a or 0) / t) if t else 0}
        for name, t, a, p, l in rows
    ]

    ack_rate = round(100 * acknowledged / total) if total else 0
    return jsonify({
        "published": published,
        "acknowledged": acknowledged,
        "read": read,
        "pending": unread + read,
        "overdue": overdue,
        "ack_rate": ack_rate,
        "by_department": by_department,
    })


@dashboard_bp.get("/users")
@jwt_required()
@roles_required("Manager", "Administrator")
def user_overview():
    """User statistics: totals, active/inactive, by role and by department."""
    total = User.query.count()
    active = User.query.filter_by(is_active=True).count()

    role_rows = (db.session.query(User.role, func.count(User.id))
                 .group_by(User.role).all())
    by_role = [{"role": r, "count": int(n)} for r, n in role_rows]

    dept_rows = (db.session.query(Department.name, func.count(User.id))
                 .outerjoin(User, User.department_id == Department.id)
                 .group_by(Department.id)
                 .order_by(Department.name).all())
    by_department = [{"department": name, "count": int(n)} for name, n in dept_rows]

    return jsonify({
        "total": total,
        "active": active,
        "inactive": total - active,
        "by_role": by_role,
        "by_department": by_department,
    })


@dashboard_bp.get("/trends")
@jwt_required()
@roles_required("Manager", "Administrator")
def trends():
    """FR-33: category distribution, ack-status split, monthly circular volume."""
    categories = [
        {"category": c, "count": int(n)}
        for c, n in db.session.query(Classification.category, func.count(Classification.id))
        .group_by(Classification.category).all()
    ]

    status_rows = (db.session.query(Acknowledgement.status, func.count(Acknowledgement.id))
                   .group_by(Acknowledgement.status).all())
    statuses = [{"status": s, "count": int(n)} for s, n in status_rows]

    # Monthly published volume (DATE_FORMAT works on MySQL/MariaDB).
    month_rows = (db.session.query(
                    func.date_format(Circular.published_at, "%Y-%m"),
                    func.count(Circular.id))
                  .filter(Circular.published_at.isnot(None))
                  .group_by(func.date_format(Circular.published_at, "%Y-%m"))
                  .order_by(func.date_format(Circular.published_at, "%Y-%m"))
                  .all())
    volume = [{"month": m, "count": int(n)} for m, n in month_rows]

    return jsonify({"categories": categories, "statuses": statuses, "volume": volume})


@dashboard_bp.get("/circulars")
@jwt_required()
@roles_required("Manager", "Administrator")
def circular_compliance():
    """FR-32: per published circular — acknowledged / total / overdue counts."""
    rows = (db.session.query(
                Circular,
                func.count(Acknowledgement.id),
                _ACK_SUM, _LATE_SUM)
            .outerjoin(Acknowledgement, Acknowledgement.circular_id == Circular.id)
            .filter(Circular.status == "published")
            .group_by(Circular.id)
            .order_by(Circular.published_at.desc())
            .all())
    return jsonify([
        {"id": c.id, "circular_number": c.circular_number, "title": c.title,
         "priority": c.priority,
         "ack_deadline": c.ack_deadline.isoformat() if c.ack_deadline else None,
         "total": int(t or 0), "acknowledged": int(a or 0), "overdue": int(l or 0),
         "rate": round(100 * (a or 0) / t) if t else 0}
        for c, t, a, l in rows
    ])


@dashboard_bp.get("/circulars/<int:circular_id>/acknowledgements")
@jwt_required()
@roles_required("Manager", "Administrator")
def circular_acknowledgements(circular_id):
    """FR-32: per-employee reading/acknowledgement status for one circular."""
    rows = (db.session.query(Acknowledgement, User, Department)
            .join(User, User.id == Acknowledgement.user_id)
            .outerjoin(Department, Department.id == User.department_id)
            .filter(Acknowledgement.circular_id == circular_id)
            .all())
    return jsonify([
        {"user": u.full_name, "department": d.name if d else None,
         "status": ack.status, "is_late": ack.is_late,
         "acknowledged_at": ack.acknowledged_at.isoformat() if ack.acknowledged_at else None}
        for ack, u, d in rows
    ])


@dashboard_bp.get("/ai-performance")
@jwt_required()
@roles_required("Manager", "Administrator")
def ai_performance():
    """FR-35: summarization performance metrics for research evaluation."""
    real = Summary.query.filter(Summary.bart_model != "stub")
    count = real.count()
    avg_time = db.session.query(func.avg(Summary.processing_seconds)).filter(
        Summary.bart_model != "stub").scalar()
    avg_rouge = db.session.query(func.avg(Summary.rouge_score)).scalar()
    models = [m[0] for m in db.session.query(Summary.bart_model).distinct().all()]
    return jsonify({
        "summaries": count,
        "avg_processing_seconds": round(float(avg_time), 2) if avg_time else None,
        "avg_rouge": round(float(avg_rouge), 3) if avg_rouge else None,
        "models_used": [m for m in models if m and m != "stub"],
    })


# ---------------------------------------------------------------- exports (FR-34)
def _compliance_report_rows():
    """Per-circular compliance rows shared by the CSV and PDF exports."""
    rows = (db.session.query(Circular, func.count(Acknowledgement.id), _ACK_SUM, _LATE_SUM)
            .outerjoin(Acknowledgement, Acknowledgement.circular_id == Circular.id)
            .filter(Circular.status == "published")
            .group_by(Circular.id).order_by(Circular.published_at.desc()).all())
    return [
        (c.circular_number, c.title, c.priority, int(t or 0), int(a or 0), int(l or 0),
         f"{round(100 * (a or 0) / t) if t else 0}%")
        for c, t, a, l in rows
    ]


@dashboard_bp.get("/export.csv")
@jwt_required()
@roles_required("Manager", "Administrator")
def export_csv():
    """FR-34: export the compliance report as CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Circular", "Title", "Priority", "Recipients",
                     "Acknowledged", "Overdue", "Ack rate"])
    writer.writerows(_compliance_report_rows())
    data = io.BytesIO(buf.getvalue().encode("utf-8"))
    return send_file(data, mimetype="text/csv", as_attachment=True,
                     download_name="compliance_report.csv")


@dashboard_bp.get("/export.pdf")
@jwt_required()
@roles_required("Manager", "Administrator")
def export_pdf():
    """FR-34: export a structured snapshot of dashboard compliance metrics."""
    total = Acknowledgement.query.count()
    acknowledged = Acknowledgement.query.filter_by(status="Acknowledged").count()
    read = Acknowledgement.query.filter_by(status="Read").count()
    unread = Acknowledgement.query.filter_by(status="Unread").count()
    late = Acknowledgement.query.filter_by(is_late=True).count()

    dept_rows = (db.session.query(Department.name, func.count(Acknowledgement.id),
                                  _ACK_SUM, _PENDING_SUM, _LATE_SUM)
                 .join(User, User.department_id == Department.id)
                 .join(Acknowledgement, Acknowledgement.user_id == User.id)
                 .group_by(Department.id).order_by(Department.name).all())
    circular_rows = (db.session.query(Circular, func.count(Acknowledgement.id),
                                      _ACK_SUM, _PENDING_SUM, _LATE_SUM)
                     .outerjoin(Acknowledgement, Acknowledgement.circular_id == Circular.id)
                     .filter(Circular.status == "published")
                     .group_by(Circular.id).order_by(Circular.published_at.desc()).all())
    category_rows = (db.session.query(Classification.category,
                                      func.count(func.distinct(Classification.circular_id)))
                     .join(Circular, Circular.id == Classification.circular_id)
                     .filter(Circular.status == "published")
                     .group_by(Classification.category)
                     .order_by(func.count(func.distinct(Classification.circular_id)).desc()).all())

    user_total = User.query.count()
    user_active = User.query.filter_by(is_active=True).count()
    real_summaries = Summary.query.filter(Summary.bart_model != "stub")
    avg_time = db.session.query(func.avg(Summary.processing_seconds)).filter(
        Summary.bart_model != "stub").scalar()
    avg_rouge = db.session.query(func.avg(Summary.rouge_score)).scalar()
    models = [m for (m,) in db.session.query(Summary.bart_model).distinct().all()
              if m and m != "stub"]

    report_data = {
        "summary": {
            "published": len(circular_rows), "recipients": total,
            "acknowledged": acknowledged, "read": read, "unread": unread,
            "pending": read + unread, "overdue": late,
            "rate": round(100 * acknowledged / total) if total else 0,
        },
        "departments": [
            {"name": name, "total": int(t or 0), "acknowledged": int(a or 0),
             "pending": int(p or 0), "overdue": int(l or 0),
             "rate": round(100 * (a or 0) / t) if t else 0}
            for name, t, a, p, l in dept_rows
        ],
        "circulars": [
            {"number": c.circular_number, "title": c.title, "priority": c.priority,
             "deadline": c.ack_deadline.strftime("%Y-%m-%d") if c.ack_deadline else "Not set",
             "total": int(t or 0), "acknowledged": int(a or 0),
             "pending": int(p or 0), "overdue": int(l or 0),
             "rate": round(100 * (a or 0) / t) if t else 0}
            for c, t, a, p, l in circular_rows
        ],
        "categories": [(name, int(count)) for name, count in category_rows],
        "users": {"total": user_total, "active": user_active,
                  "inactive": user_total - user_active},
        "roles": [(role, int(count)) for role, count in
                  db.session.query(User.role, func.count(User.id)).group_by(User.role).all()],
        "user_departments": [(name, int(count)) for name, count in
                             db.session.query(Department.name, func.count(User.id))
                             .outerjoin(User, User.department_id == Department.id)
                             .group_by(Department.id).order_by(Department.name).all()],
        "ai": {"summaries": real_summaries.count(),
               "avg_seconds": round(float(avg_time), 2) if avg_time is not None else None,
               "avg_rouge": round(float(avg_rouge), 3) if avg_rouge is not None else None,
               "models": models},
    }
    data = io.BytesIO(build_compliance_pdf(
        report_data, bank_name=current_app.config["REPORT_BANK_NAME"],
        generated_at=datetime.utcnow(),
    ))
    return send_file(data, mimetype="application/pdf", as_attachment=True,
                     download_name="compliance_report.pdf")
