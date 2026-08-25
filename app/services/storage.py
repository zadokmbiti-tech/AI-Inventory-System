"""
File storage for uploaded documents (receipts, invoices, delivery notes).

On Vercel, the filesystem is ephemeral and mostly read-only, so local disk
writes silently fail or vanish between invocations. This module uses
Vercel Blob when BLOB_READ_WRITE_TOKEN is set (i.e. in production, once
you've created a Blob store and connected it to the project), and falls
back to local disk for local development where that token isn't set.

Documents can contain sensitive business data, so files are uploaded to a
PUBLIC blob store but with a long random pathname (nobody can guess the
URL), and reads always go through our own authenticated /file endpoint,
which fetches the bytes server-side and streams them back — the blob URL
itself is never exposed to the browser, so ownership is still enforced
on every read exactly like before.
"""
import os
import uuid
from typing import Optional, Tuple

import httpx

try:
    import vercel_blob
except ImportError:  # pragma: no cover - always installed via requirements.txt
    vercel_blob = None

LOCAL_UPLOAD_DIR = os.path.join("uploads", "documents")


def _use_blob() -> bool:
    return bool(os.environ.get("BLOB_READ_WRITE_TOKEN")) and vercel_blob is not None


def save_file(contents: bytes, original_filename: str, user_id: int) -> str:
    """
    Save uploaded file contents. Returns a string that should be stored in
    DocumentRecord.file_path — a Vercel Blob URL in production, or a local
    path in development. Content-type for the blob is inferred from the
    file extension by the vercel_blob library, so the pathname keeps the
    original extension.
    """
    ext = os.path.splitext(original_filename)[1][:10]
    pathname = f"documents/{user_id}_{uuid.uuid4().hex}{ext}"

    if _use_blob():
        resp = vercel_blob.put(
            pathname,
            contents,
            {"addRandomSuffix": "false"},
        )
        return resp["url"]

    # Local dev fallback
    os.makedirs(LOCAL_UPLOAD_DIR, exist_ok=True)
    dest_path = os.path.join(LOCAL_UPLOAD_DIR, os.path.basename(pathname))
    with open(dest_path, "wb") as f:
        f.write(contents)
    return dest_path


def read_file(file_path: str) -> Optional[bytes]:
    """
    Fetch file bytes for a stored file_path — works whether it's a Blob
    URL or a local path, so callers don't need to care which backend
    is active.
    """
    if file_path.startswith("http://") or file_path.startswith("https://"):
        try:
            resp = httpx.get(file_path, timeout=15)
            resp.raise_for_status()
            return resp.content
        except httpx.HTTPError:
            return None

    if not os.path.exists(file_path):
        return None
    with open(file_path, "rb") as f:
        return f.read()


def delete_file(file_path: str) -> None:
    if file_path.startswith("http://") or file_path.startswith("https://"):
        if _use_blob():
            try:
                vercel_blob.delete([file_path])
            except Exception:
                pass  # best-effort — don't block deleting the DB record over a storage hiccup
        return

    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except OSError:
        pass
