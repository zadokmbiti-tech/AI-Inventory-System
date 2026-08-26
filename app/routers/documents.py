from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import DocumentRecord, DocumentType, User
from app.schemas.schemas import DocumentRecordOut
from app.services.auth import get_current_user
from app.services.storage import save_file, read_file, delete_file

router = APIRouter(prefix="/api/documents", tags=["Documents"])

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _sniff_file_type(contents: bytes) -> Optional[str]:
    """
    Identify a file by its magic bytes instead of trusting the
    client-supplied Content-Type header, which is easy to spoof (e.g.
    naming a script "receipt.pdf" and sending Content-Type: application/pdf).
    Returns None for HEIC, since its signature check is less standardized —
    those fall back to the declared header.
    """
    if contents.startswith(b"%PDF-"):
        return "application/pdf"
    if contents.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if contents.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if contents[:4] == b"RIFF" and contents[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.post("", response_model=DocumentRecordOut, status_code=201)
async def upload_document(
    doc_type: DocumentType = Form(...),
    reference_number: Optional[str] = Form(None),
    party_name: Optional[str] = Form(None),
    amount: Optional[float] = Form(None),
    doc_date: Optional[datetime] = Form(None),
    notes: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    file_path = None
    original_filename = None
    content_type = None
    file_size = None

    if file is not None and file.filename:
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail="Unsupported file type. Please upload a PDF, JPG, PNG, or WEBP file.",
            )

        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="File too large (max 10MB)")
        if not contents:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        # Verify the actual file bytes match a real, allowed file type —
        # don't just trust the Content-Type header the browser sent.
        sniffed = _sniff_file_type(contents)
        if sniffed is not None and sniffed != file.content_type:
            raise HTTPException(
                status_code=400,
                detail="File contents don't match the declared file type.",
            )
        if sniffed is None and file.content_type != "image/heic":
            raise HTTPException(
                status_code=400,
                detail="Unsupported or unrecognized file type. Please upload a PDF, JPG, PNG, or WEBP file.",
            )

        file_path = save_file(contents, file.filename, user.id)
        original_filename = file.filename
        content_type = file.content_type
        file_size = len(contents)

    record = DocumentRecord(
        user_id=user.id,
        doc_type=doc_type,
        reference_number=reference_number,
        party_name=party_name,
        amount=amount,
        doc_date=doc_date,
        notes=notes,
        file_path=file_path,
        original_filename=original_filename,
        content_type=content_type,
        file_size=file_size,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("", response_model=List[DocumentRecordOut])
def list_documents(
    doc_type: Optional[DocumentType] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(DocumentRecord).filter(DocumentRecord.user_id == user.id)
    if doc_type:
        q = q.filter(DocumentRecord.doc_type == doc_type)
    return q.order_by(DocumentRecord.created_at.desc()).limit(limit).all()


@router.get("/{doc_id}/file")
def get_document_file(
    doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    record = (
        db.query(DocumentRecord)
        .filter(DocumentRecord.id == doc_id, DocumentRecord.user_id == user.id)
        .first()
    )
    if not record or not record.file_path:
        raise HTTPException(status_code=404, detail="File not found")

    contents = read_file(record.file_path)
    if contents is None:
        raise HTTPException(status_code=404, detail="File missing on server")

    filename = record.original_filename or f"document_{doc_id}"
    return Response(
        content=contents,
        media_type=record.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{doc_id}", status_code=204)
def delete_document(
    doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    record = (
        db.query(DocumentRecord)
        .filter(DocumentRecord.id == doc_id, DocumentRecord.user_id == user.id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.file_path:
        delete_file(record.file_path)
    db.delete(record)
    db.commit()
    return
