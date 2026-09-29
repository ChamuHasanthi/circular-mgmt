"""Circular upload, listing, search (FR-06 to FR-10, FR-27 to FR-30)."""
import os
import uuid
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, current_app, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from werkzeug.utils import secure_filename
from sqlalchemy import or_

from ..extensions import db
from ..models.circular import Circular, Summary, Classification, Category
from ..models.engagement import Acknowledgement, Notification
from ..models.identity import User, CircularDepartment, Department
from ..models.system import ChangeRequest, AuditLog
from ..services.security import roles_required
from ..services import audit, pdf_extract, distribution
from ..ai import get_engine, get_index

circulars_bp = Blueprint("circulars", __name__)

ALLOWED_EXTENSIONS = {".pdf"}


@circulars_bp.get("/categories")
@jwt_required()
def list_categories():
    """Managed compliance categories (for the manual classification picker)."""
    return jsonify([c.to_dict() for c in Category.query.order_by(Category.name).all()])


@circulars_bp.post("/categories")
@jwt_required()
@roles_required("Administrator")
def add_category():
    """Administrators extend the taxonomy with a new category."""
    name = ((request.get_json(silent=True) or {}).get("name") or "").strip()
    if not name:
        return jsonify({"error": "Category name is required."}), 400
    if Category.query.filter(Category.name.ilike(name)).first():
        return jsonify({"error": f"Category '{name}' already exists."}), 409
    cat = Category(name=name)
    db.session.add(cat)
    db.session.commit()
    audit.record("CATEGORY_ADDED", user_id=int(get_jwt_identity()),
                 entity_type="Category", entity_id=cat.id, detail=name)
    return jsonify(cat.to_dict()), 201


@circulars_bp.delete("/categories/<int:cat_id>")
@jwt_required()
@roles_required("Administrator")
def delete_category(cat_id):
    """Administrators remove a category from the taxonomy."""
    cat = Category.query.get(cat_id)
    if not cat:
        return jsonify({"error": "Category not found."}), 404
    db.session.delete(cat)
    db.session.commit()
    audit.record("CATEGORY_DELETED", user_id=int(get_jwt_identity()),
                 entity_type="Category", entity_id=cat_id, detail=cat.name)
    return jsonify({"message": f"Category '{cat.name}' deleted."})


def _circular_list_item(circular, my_status):
    """Shape a circular for the list view (WF-02), with the viewer's ack status."""
    data = circular.to_dict()
    data["my_status"] = my_status                       # Unread/Read/Acknowledged/None
    data["categories"] = [c.category for c in circular.classifications]
    data["has_summary"] = circular.summary is not None
    return data


@circulars_bp.get("")
@jwt_required()
def list_circulars():
    """FR-28/29: search + filter circulars, scoped by role.

    Employees see only circulars routed to them (i.e. they have an acknowledgement
    record); Managers/Administrators see all. Supports keyword search across title,
    summary and category, plus category / ack-status / department / date filters.
    """
    uid = int(get_jwt_identity())
    role = get_jwt().get("role")
    args = request.args
    q = (args.get("q") or "").strip()

    # ---- base query + role scoping, paired with the viewer's ack ----
    ack_join = (Acknowledgement.circular_id == Circular.id) & (Acknowledgement.user_id == uid)
    if role == "Employee":
        query = (db.session.query(Circular, Acknowledgement)
                 .join(Acknowledgement, ack_join)
                 .filter(Circular.status == "published"))
    else:  # Manager / Administrator see everything, with their own ack if any
        query = db.session.query(Circular, Acknowledgement).outerjoin(Acknowledgement, ack_join)

    # ---- keyword search (FR-28): title, summary text, or category ----
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Circular.title.ilike(like),
            Circular.circular_number.ilike(like),
            Circular.summary.has(Summary.summary_text.ilike(like)),
            Circular.classifications.any(Classification.category.ilike(like)),
        ))

    # ---- filters (FR-29) ----
    category = args.get("category")
    if category:
        query = query.filter(Circular.classifications.any(Classification.category == category))
    status = args.get("status")
    if status:
        query = query.filter(Acknowledgement.status == status)
    department_id = args.get("department_id")
    if department_id:
        query = query.filter(Circular.departments.any(department_id=int(department_id)))
    date_from = args.get("date_from")
    if date_from:
        query = query.filter(Circular.issue_date >= date_from)
    date_to = args.get("date_to")
    if date_to:
        query = query.filter(Circular.issue_date <= date_to)

    # MySQL/MariaDB sorts NULLs last on DESC, which is what we want (drafts last).
    rows = query.order_by(Circular.published_at.desc(),
                          Circular.created_at.desc()).all()
    return jsonify([
        _circular_list_item(circ, ack.status if ack else None) for circ, ack in rows
    ])


@circulars_bp.get("/<int:circular_id>")
@jwt_required()
def get_circular(circular_id):
    circular = Circular.query.get(circular_id)
    if not circular:
        return jsonify({"error": "Circular not found"}), 404

    uid = int(get_jwt_identity())
    ack = Acknowledgement.query.filter_by(circular_id=circular_id, user_id=uid).first()
    # SD-02: opening an unread circular marks it Read.
    if ack and ack.status == "Unread":
        ack.status = "Read"
        ack.read_at = datetime.utcnow()
        db.session.commit()

    data = circular.to_dict(include_text=True)
    data["my_status"] = ack.status if ack else None
    data["my_ack"] = ack.to_dict() if ack else None
    data["summary"] = circular.summary.to_dict() if circular.summary else None
    data["classifications"] = [c.to_dict() for c in circular.classifications]
    return jsonify(data)


@circulars_bp.get("/<int:circular_id>/download")
@jwt_required()
def download_circular(circular_id):
    """FR-30: download the original PDF of a circular."""
    circular = Circular.query.get(circular_id)
    if not circular or not circular.file_path or not os.path.exists(circular.file_path):
        return jsonify({"error": "Original PDF not available."}), 404
    audit.record("CIRCULAR_DOWNLOADED", user_id=int(get_jwt_identity()),
                 entity_type="Circular", entity_id=circular.id)
    download_name = f"Circular_{circular.circular_number.replace('/', '-')}.pdf"
    return send_file(circular.file_path, mimetype="application/pdf",
                     as_attachment=True, download_name=download_name)


@circulars_bp.get("/<int:circular_id>/preview")
@jwt_required()
def preview_circular(circular_id):
    """FR-30: stream the original PDF inline for in-browser preview (no download)."""
    circular = Circular.query.get(circular_id)
    if not circular or not circular.file_path or not os.path.exists(circular.file_path):
        return jsonify({"error": "Original PDF not available."}), 404
    audit.record("CIRCULAR_PREVIEWED", user_id=int(get_jwt_identity()),
                 entity_type="Circular", entity_id=circular.id)
    return send_file(circular.file_path, mimetype="application/pdf",
                     as_attachment=False)


@circulars_bp.patch("/<int:circular_id>")
@jwt_required()
@roles_required("Administrator")
def edit_circular(circular_id):
    """Administrators edit a circular's metadata (number, title, date, priority)."""
    circular = Circular.query.get(circular_id)
    if not circular:
        return jsonify({"error": "Circular not found."}), 404
    data = request.get_json(silent=True) or {}

    if "circular_number" in data:
        num = (data["circular_number"] or "").strip().strip("\"'").strip()
        if not num:
            return jsonify({"error": "Circular number cannot be empty."}), 400
        clash = Circular.query.filter(Circular.circular_number == num,
                                      Circular.id != circular.id).first()
        if clash:
            return jsonify({"error": f"Circular '{num}' already exists."}), 409
        circular.circular_number = num
    if "title" in data and data["title"].strip():
        circular.title = data["title"].strip()
    if "priority" in data and data["priority"] in Circular.PRIORITIES:
        circular.priority = data["priority"]
    if "issue_date" in data:
        raw = (data["issue_date"] or "").strip()
        if raw:
            try:
                circular.issue_date = datetime.strptime(raw, "%Y-%m-%d").date()
            except ValueError:
                return jsonify({"error": "issue_date must be YYYY-MM-DD."}), 400
        else:
            circular.issue_date = None
    if "amends_circular_id" in data:
        raw = data["amends_circular_id"]
        if raw in (None, "", 0, "0"):
            circular.amends_circular_id = None
        else:
            try:
                aid = int(raw)
            except (TypeError, ValueError):
                return jsonify({"error": "amends_circular_id must be a circular id."}), 400
            if aid == circular.id:
                return jsonify({"error": "A circular cannot amend itself."}), 400
            if not Circular.query.get(aid):
                return jsonify({"error": "The circular being amended was not found."}), 400
            circular.amends_circular_id = aid

    db.session.commit()
    audit.record("CIRCULAR_EDITED", user_id=int(get_jwt_identity()),
                 entity_type="Circular", entity_id=circular.id)
    return jsonify(circular.to_dict())


@circulars_bp.delete("/<int:circular_id>")
@jwt_required()
@roles_required("Administrator")
def delete_circular(circular_id):
    """Administrators delete a circular and all of its related records."""
    circular = Circular.query.get(circular_id)
    if not circular:
        return jsonify({"error": "Circular not found."}), 404

    number = circular.circular_number
    # Remove the stored PDF from disk.
    if circular.file_path and os.path.exists(circular.file_path):
        try:
            os.remove(circular.file_path)
        except OSError:
            pass

    # Delete children explicitly (avoids ORM null-ing NOT NULL FKs), then the row.
    Acknowledgement.query.filter_by(circular_id=circular.id).delete()
    Notification.query.filter_by(circular_id=circular.id).delete()
    Classification.query.filter_by(circular_id=circular.id).delete()
    CircularDepartment.query.filter_by(circular_id=circular.id).delete()
    ChangeRequest.query.filter_by(circular_id=circular.id).delete()
    Summary.query.filter_by(circular_id=circular.id).delete()
    Circular.query.filter_by(id=circular.id).delete()
    db.session.commit()

    # FR-40: rebuild the vector index so the deleted circular is no longer searchable.
    try:
        get_index(current_app.config).build(
            Circular.query.filter_by(status="published").all()
        )
    except Exception:  # noqa: BLE001
        pass

    audit.record("CIRCULAR_DELETED", user_id=int(get_jwt_identity()),
                 entity_type="Circular", entity_id=circular_id, detail=number)
    return jsonify({"message": f"Circular {number} deleted."})


@circulars_bp.post("/<int:circular_id>/request")
@jwt_required()
@roles_required("Manager", "Administrator")
def request_change(circular_id):
    """Managers flag a problem with a circular; all administrators are notified."""
    circular = Circular.query.get(circular_id)
    if not circular:
        return jsonify({"error": "Circular not found."}), 404
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Please describe the issue."}), 400

    requester = User.query.get(int(get_jwt_identity()))
    change = ChangeRequest(circular_id=circular.id, requester_id=requester.id,
                           message=message)
    db.session.add(change)

    note = (f"Change request from {requester.full_name} on circular "
            f"{circular.circular_number}: {message}")
    admins = User.query.filter_by(role="Administrator", is_active=True).all()
    for admin in admins:
        db.session.add(Notification(user_id=admin.id, circular_id=circular.id, message=note,
                                    link="/requests"))
    db.session.commit()
    audit.record("CIRCULAR_CHANGE_REQUESTED", user_id=requester.id,
                 entity_type="Circular", entity_id=circular.id, detail=message[:200])
    return jsonify({"message": "Your request has been sent to the administrators."})


@circulars_bp.get("/requests")
@jwt_required()
@roles_required("Manager", "Administrator")
def list_requests():
    """Managers see their own change requests; administrators see all."""
    uid = int(get_jwt_identity())
    role = get_jwt().get("role")
    requester = db.aliased(User)
    resolver = db.aliased(User)
    query = (db.session.query(ChangeRequest, Circular, requester, resolver)
             .join(Circular, Circular.id == ChangeRequest.circular_id)
             .join(requester, requester.id == ChangeRequest.requester_id)
             .outerjoin(resolver, resolver.id == ChangeRequest.resolved_by))
    if role == "Manager":
        query = query.filter(ChangeRequest.requester_id == uid)
    rows = query.order_by(ChangeRequest.created_at.desc()).all()
    return jsonify([
        {
            "id": cr.id,
            "circular_id": cr.circular_id,
            "circular_number": circ.circular_number,
            "circular_title": circ.title,
            "message": cr.message,
            "status": cr.status,
            "admin_reply": cr.admin_reply,
            "requester": req.full_name,
            "resolved_by": res.full_name if res else None,
            "created_at": cr.created_at.isoformat() if cr.created_at else None,
            "resolved_at": cr.resolved_at.isoformat() if cr.resolved_at else None,
        }
        for cr, circ, req, res in rows
    ])


@circulars_bp.post("/requests/<int:req_id>/resolve")
@jwt_required()
@roles_required("Administrator")
def resolve_request(req_id):
    """Administrator replies to a request, marking it Solved or Not Solved."""
    change = ChangeRequest.query.get(req_id)
    if not change:
        return jsonify({"error": "Request not found."}), 404
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    reply = (data.get("reply") or "").strip()
    if status not in ("Solved", "Not Solved"):
        return jsonify({"error": "status must be 'Solved' or 'Not Solved'."}), 400

    change.status = status
    change.admin_reply = reply
    change.resolved_by = int(get_jwt_identity())
    change.resolved_at = datetime.utcnow()

    circular = Circular.query.get(change.circular_id)
    num = circular.circular_number if circular else change.circular_id
    db.session.add(Notification(
        user_id=change.requester_id, circular_id=change.circular_id,
        message=f"Your request on circular {num} was marked {status}"
                + (f": {reply}" if reply else "."),
        link="/requests",
    ))
    db.session.commit()
    audit.record("CHANGE_REQUEST_RESOLVED", user_id=int(get_jwt_identity()),
                 entity_type="ChangeRequest", entity_id=change.id, detail=status)
    return jsonify({"message": f"Request marked {status}."})


@circulars_bp.post("/upload")
@jwt_required()
@roles_required("Administrator")
def upload_circular():
    """FR-06–FR-10: validate + store a CBSL circular PDF and extract its text.

    Pipeline: validate file (FR-09) -> duplicate check (FR-10) -> save PDF ->
    extract text via PyMuPDF (FR-07) -> capture metadata (FR-08) -> create record.
    AI summarization (Phase 3) runs separately on the stored circular.
    """
    # ---- file presence & type (FR-09) ----
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "A PDF file is required."}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "Only PDF files are accepted."}), 400

    # ---- metadata from form (FR-08) ----
    # Strip whitespace AND stray quotes so a pasted number like 'X"' is cleaned.
    circular_number = (request.form.get("circular_number") or "").strip().strip("\"'").strip()
    title = (request.form.get("title") or "").strip()
    priority = request.form.get("priority", "Medium")
    issue_date_raw = (request.form.get("issue_date") or "").strip()
    if not circular_number or not title:
        return jsonify({"error": "Circular number and title are required."}), 400
    if priority not in Circular.PRIORITIES:
        priority = "Medium"
    issue_date = None
    if issue_date_raw:
        try:
            issue_date = datetime.strptime(issue_date_raw, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "issue_date must be YYYY-MM-DD."}), 400

    # Optional: the earlier circular this one amends (FR — amendments).
    amends_raw = (request.form.get("amends_circular_id") or "").strip()
    amends_id = int(amends_raw) if amends_raw.isdigit() else None
    if amends_id and not Circular.query.get(amends_id):
        return jsonify({"error": "The circular being amended was not found."}), 400

    # ---- duplicate detection (FR-10) ----
    if Circular.query.filter_by(circular_number=circular_number).first():
        return jsonify({
            "error": f"A circular numbered '{circular_number}' already exists.",
            "duplicate": True,
        }), 409

    # ---- save the PDF ----
    safe_name = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    save_path = os.path.join(current_app.config["UPLOAD_FOLDER"], safe_name)
    file.save(save_path)
    size_kb = max(1, round(os.path.getsize(save_path) / 1024))

    # ---- extract text via PyMuPDF (FR-07) ----
    try:
        text, page_count = pdf_extract.extract_text_with_meta(save_path)
    except ValueError as exc:
        os.remove(save_path)  # not a valid PDF — clean up
        return jsonify({"error": str(exc)}), 400

    # ---- persist (FR-27 storage) ----
    circular = Circular(
        circular_number=circular_number,
        title=title,
        issue_date=issue_date,
        file_path=save_path,
        file_size_kb=size_kb,
        extracted_text=text,
        priority=priority,
        status="uploaded",
        uploaded_by=int(get_jwt_identity()),
        amends_circular_id=amends_id,
    )
    db.session.add(circular)
    db.session.commit()
    audit.record("CIRCULAR_UPLOADED", user_id=int(get_jwt_identity()),
                 entity_type="Circular", entity_id=circular.id,
                 detail=f"{circular_number} ({size_kb} KB, {page_count} pages)")

    return jsonify({
        "circular": circular.to_dict(),
        "extraction": {
            "page_count": page_count,
            "char_count": len(text),
            "word_count": len(text.split()),
            "preview": text[:600],
        },
        "message": "Uploaded and text extracted. Ready for AI summarization.",
    }), 201


@circulars_bp.post("/<int:circular_id>/summarize")
@jwt_required()
@roles_required("Administrator")
def summarize_circular(circular_id):
    """FR-11–FR-16: run the spaCy->BERT->BART pipeline on a stored circular.

    Generates the abstractive summary + NER entities and auto-classifies the
    compliance category (FR-18). This does NOT distribute — the circular moves to
    'review' so an administrator can check the summary before publishing. Use the
    /publish endpoint to distribute. (regenerate=true refreshes an already-
    published summary in place without changing status or re-notifying.)
    """
    circular = Circular.query.get(circular_id)
    if not circular:
        return jsonify({"error": "Circular not found."}), 404
    # Refresh extracted text from the stored PDF so extraction improvements
    # (header/footer + table-artifact stripping, OCR) apply on every (re)summarize.
    if circular.file_path and os.path.exists(circular.file_path):
        try:
            fresh, _ = pdf_extract.extract_text_with_meta(circular.file_path)
            if fresh.strip():
                circular.extracted_text = fresh
        except ValueError:
            pass
    if not (circular.extracted_text or "").strip():
        return jsonify({"error": "Circular has no extracted text to summarize."}), 400

    # 1-page rule: condense to ~page_words (default 500). Optional override.
    page_words = request.args.get("page_words")
    page_words = int(page_words) if page_words else None
    # regenerate=true: refresh the summary of an already-published circular only.
    regenerate = request.args.get("regenerate", "false").lower() == "true"

    # Sanitize so a stuck "processing"/"failed" state can't trap the circular:
    # a regenerate returns to published (if it was live) else review.
    prev_status = "published" if circular.status == "published" else "review"
    circular.status = "processing"  # FR-17 status the UI can show
    db.session.commit()

    engine = get_engine(current_app.config)
    try:
        result = engine.summarize(circular.extracted_text, page_words=page_words)
    except Exception as exc:  # noqa: BLE001 — surface failure, mark circular failed
        circular.status = "failed"
        db.session.commit()
        return jsonify({"error": f"Summarization failed: {exc}"}), 500

    # Replace ALL previous summaries so re-running is idempotent (deleting every
    # row, not just the one the relationship returns, prevents duplicates).
    Summary.query.filter_by(circular_id=circular.id).delete()
    db.session.flush()
    summary = Summary(
        circular_id=circular.id,
        summary_text=result.summary_text,
        entities=result.entities,
        word_count=result.word_count,
        bert_model=result.bert_model,
        bart_model=result.bart_model,
        processing_seconds=result.processing_seconds,
    )
    db.session.add(summary)

    # No auto-classification: categories are assigned manually by an administrator
    # from the managed taxonomy at publish time (FR-18/20).

    # Regenerate keeps the (published) status; a fresh summary goes to review.
    circular.status = prev_status if regenerate else "review"
    db.session.commit()
    audit.record("CIRCULAR_RESUMMARIZED" if regenerate else "CIRCULAR_SUMMARIZED",
                 user_id=int(get_jwt_identity()), entity_type="Circular",
                 entity_id=circular.id,
                 detail=f"{result.bart_model} in {result.processing_seconds}s")

    # Regenerate rebuilds the index in place (text unchanged but summary refreshed).
    if regenerate:
        try:
            get_index(current_app.config).build(
                Circular.query.filter_by(status="published").all())
        except Exception:  # noqa: BLE001
            pass

    return jsonify({
        "circular": circular.to_dict(),
        "summary": summary.to_dict(),
        "classifications": [c.to_dict() for c in circular.classifications],
    })


def _finalize_publish(circular):
    """Publish a circular using its stored distribution intent: set the deadline,
    distribute + notify, and rebuild the index. Returns the distribution result."""
    intent = circular.distribution_intent or {}
    department_ids = intent.get("department_ids")
    broadcast = bool(intent.get("broadcast", False))
    ack_days = int(intent.get("ack_days", 7))

    circular.ack_deadline = datetime.utcnow() + timedelta(days=max(1, ack_days))
    circular.status = "published"
    circular.published_at = circular.published_at or datetime.utcnow()
    db.session.commit()

    dist = distribution.route_and_notify(circular, broadcast=broadcast,
                                         department_ids=department_ids)
    try:
        get_index(current_app.config).build(
            Circular.query.filter_by(status="published").all())
    except Exception:  # noqa: BLE001 — indexing failure shouldn't fail publishing
        pass
    return dist


@circulars_bp.post("/<int:circular_id>/submit")
@jwt_required()
@roles_required("Administrator")
def submit_for_approval(circular_id):
    """Maker step: an admin submits a reviewed circular (with its category and
    target departments) to a Compliance Officer for approval. Nothing is
    distributed yet."""
    circular = Circular.query.get(circular_id)
    if not circular:
        return jsonify({"error": "Circular not found."}), 404
    if not circular.summary:
        return jsonify({"error": "Generate a summary before submitting."}), 400
    if circular.status == "published":
        return jsonify({"error": "This circular is already published."}), 400

    data = request.get_json(silent=True) or {}
    # Manual classification (required): categories from the managed taxonomy.
    valid = {c.name for c in Category.query.all()}
    chosen = [c for c in (data.get("categories") or []) if c in valid]
    if not chosen:
        return jsonify({"error": "Select at least one valid category."}), 400
    Classification.query.filter_by(circular_id=circular.id).delete()
    for name in chosen:
        db.session.add(Classification(circular_id=circular.id, category=name,
                                      confidence=None, is_manual=True))

    # Target departments (the distribution intent, applied on approval).
    department_ids = data.get("department_ids")
    broadcast = bool(data.get("broadcast", False))
    department_ids = [int(d) for d in department_ids] if department_ids else []
    if not broadcast and not department_ids:
        return jsonify({"error": "Select at least one department (or broadcast)."}), 400
    circular.distribution_intent = {
        "department_ids": department_ids,
        "broadcast": broadcast,
        "ack_days": int(data.get("ack_days", 7)),
    }
    circular.status = "pending_approval"
    db.session.commit()

    # Notify all Compliance Officers that something awaits approval.
    submitter = User.query.get(int(get_jwt_identity()))
    note = (f"Circular {circular.circular_number} submitted for approval"
            + (f" by {submitter.full_name}" if submitter else "") + ".")
    for officer in User.query.filter_by(role="Compliance Officer", is_active=True).all():
        db.session.add(Notification(user_id=officer.id, circular_id=circular.id,
                                    message=note, link="/approvals"))
    db.session.commit()
    audit.record("CIRCULAR_SUBMITTED", user_id=int(get_jwt_identity()),
                 entity_type="Circular", entity_id=circular.id)
    return jsonify({"circular": circular.to_dict(),
                    "message": "Submitted for Compliance Officer approval."})


@circulars_bp.post("/<int:circular_id>/approve")
@jwt_required()
@roles_required("Compliance Officer")
def approve_circular(circular_id):
    """Checker step: a Compliance Officer approves a pending circular, which
    publishes and distributes it."""
    circular = Circular.query.get(circular_id)
    if not circular:
        return jsonify({"error": "Circular not found."}), 404
    if circular.status != "pending_approval":
        return jsonify({"error": "This circular is not pending approval."}), 400

    uid = int(get_jwt_identity())
    circular.approved_by = uid
    circular.approved_at = datetime.utcnow()
    dist = _finalize_publish(circular)

    approver = User.query.get(uid)
    if circular.uploaded_by:
        db.session.add(Notification(
            user_id=circular.uploaded_by, circular_id=circular.id,
            message=(f"Your circular {circular.circular_number} was approved and "
                     f"published by {approver.full_name}."),
            link=f"/circulars/{circular.id}"))
        db.session.commit()
    audit.record("CIRCULAR_APPROVED", user_id=uid, entity_type="Circular",
                 entity_id=circular.id, detail=f"{dist['recipient_count']} recipients")
    return jsonify({"circular": circular.to_dict(), "distribution": dist})


@circulars_bp.post("/<int:circular_id>/reject")
@jwt_required()
@roles_required("Compliance Officer")
def reject_circular(circular_id):
    """Checker step: a Compliance Officer rejects a pending circular with a reason,
    sending it back to the admin for revision."""
    circular = Circular.query.get(circular_id)
    if not circular:
        return jsonify({"error": "Circular not found."}), 404
    if circular.status != "pending_approval":
        return jsonify({"error": "This circular is not pending approval."}), 400
    reason = ((request.get_json(silent=True) or {}).get("reason") or "").strip()
    if not reason:
        return jsonify({"error": "Please provide a reason for rejection."}), 400

    circular.status = "review"
    db.session.commit()
    approver = User.query.get(int(get_jwt_identity()))
    if circular.uploaded_by:
        db.session.add(Notification(
            user_id=circular.uploaded_by, circular_id=circular.id,
            message=(f"Your circular {circular.circular_number} was rejected by "
                     f"{approver.full_name}: {reason}"),
            link=f"/circulars/{circular.id}"))
        db.session.commit()
    audit.record("CIRCULAR_REJECTED", user_id=int(get_jwt_identity()),
                 entity_type="Circular", entity_id=circular.id, detail=reason[:200])
    return jsonify({"circular": circular.to_dict(),
                    "message": "Circular sent back for revision."})


@circulars_bp.get("/approval-history")
@jwt_required()
@roles_required("Compliance Officer", "Administrator")
def approval_history():
    """The four-eyes trail: submit / approve / reject events, most recent first."""
    _ACTIONS = {
        "CIRCULAR_SUBMITTED": "Submitted",
        "CIRCULAR_APPROVED": "Approved",
        "CIRCULAR_REJECTED": "Rejected",
    }
    actor = db.aliased(User)
    rows = (db.session.query(AuditLog, Circular, actor)
            .outerjoin(Circular, Circular.id == AuditLog.entity_id)
            .outerjoin(actor, actor.id == AuditLog.user_id)
            .filter(AuditLog.entity_type == "Circular",
                    AuditLog.action.in_(list(_ACTIONS)))
            .order_by(AuditLog.created_at.desc())
            .limit(100).all())
    return jsonify([
        {
            "id": log.id,
            "action": _ACTIONS.get(log.action, log.action),
            "actor": act.full_name if act else "—",
            "circular_id": circ.id if circ else log.entity_id,
            "circular_number": circ.circular_number if circ else None,
            "circular_title": circ.title if circ else None,
            "detail": log.detail,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log, circ, act in rows
    ])


@circulars_bp.get("/pending")
@jwt_required()
@roles_required("Compliance Officer", "Administrator")
def list_pending():
    """The approval queue: circulars awaiting Compliance Officer approval."""
    rows = (Circular.query.filter_by(status="pending_approval")
            .order_by(Circular.created_at.desc()).all())
    return jsonify([{**c.to_dict(),
                     "categories": [cl.category for cl in c.classifications],
                     "has_summary": c.summary is not None} for c in rows])


@circulars_bp.patch("/<int:circular_id>/classification")
@jwt_required()
@roles_required("Manager", "Administrator")
def override_classification(circular_id):
    """FR-20: compliance officer overrides the auto-classification and re-routes."""
    circular = Circular.query.get(circular_id)
    if not circular:
        return jsonify({"error": "Circular not found."}), 404
    data = request.get_json(silent=True) or {}
    categories = data.get("categories") or []
    allowed = {c.name for c in Category.query.all()}
    valid = [c for c in categories if c in allowed]
    if not valid:
        return jsonify({"error": "Provide at least one valid category."}), 400

    Classification.query.filter_by(circular_id=circular.id).delete()
    for cat in valid:
        db.session.add(Classification(circular_id=circular.id, category=cat,
                                      confidence=None, is_manual=True))
    db.session.commit()
    audit.record("CLASSIFICATION_OVERRIDDEN", user_id=int(get_jwt_identity()),
                 entity_type="Circular", entity_id=circular.id,
                 detail=", ".join(valid))

    # Re-route if the circular is already published.
    dist = None
    if circular.status == "published":
        dist = distribution.route_and_notify(circular)
    return jsonify({
        "classifications": [c.to_dict() for c in circular.classifications],
        "distribution": dist,
    })


@circulars_bp.post("/<int:circular_id>/broadcast")
@jwt_required()
@roles_required("Manager", "Administrator")
def broadcast_circular(circular_id):
    """Send an existing published circular to ALL departments (re-route)."""
    circular = Circular.query.get(circular_id)
    if not circular:
        return jsonify({"error": "Circular not found."}), 404
    if circular.status != "published":
        return jsonify({"error": "Only published circulars can be broadcast."}), 400

    dist = distribution.route_and_notify(circular, broadcast=True)
    audit.record("CIRCULAR_BROADCAST", user_id=int(get_jwt_identity()),
                 entity_type="Circular", entity_id=circular.id,
                 detail=f"{dist['recipient_count']} recipients")
    return jsonify({"distribution": dist})


@circulars_bp.post("/reminders/run")
@jwt_required()
@roles_required("Manager", "Administrator")
def run_reminders():
    """FR-26: send reminders for un-acknowledged circulars near/after deadline."""
    result = distribution.run_reminders()
    return jsonify(result)
