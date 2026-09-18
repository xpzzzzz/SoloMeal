from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select

from ..core.errors import AppError
from ..models.receipts import ReceiptImport
from ..schemas.food import VersionInput
from ..schemas.receipts import ReceiptEditInput
from ..services import receipts
from ..services.food import owned
from ..services.receipt_parser import configured
from .food import Key
from .pagination import Page
from .routes import get_db, get_identity

router = APIRouter(prefix="/api/v1/receipts")


@router.post("", status_code=201)
async def upload(request: Request, key: Key, current=Depends(get_identity), db=Depends(get_db)):
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > receipts.MAX_UPLOAD_BYTES:
            raise AppError(413, "RECEIPT_SIZE", "Image exceeds 5 MiB")
        content.extend(chunk)
    return receipts.upload(db, current[0].id, key, bytes(content),
                           request.headers.get("content-type", ""), request.app.state.settings.receipt_storage_dir)


@router.get("")
def listing(page: Page = Depends(), current=Depends(get_identity), db=Depends(get_db)):
    return [receipts.view(row) for row in db.scalars(select(ReceiptImport).where(
        ReceiptImport.user_id == current[0].id).order_by(ReceiptImport.created_at.desc(), ReceiptImport.id).limit(page.limit).offset(page.offset))]


@router.get("/capabilities")
def capabilities(request: Request, current=Depends(get_identity)):
    return {"vision_enabled": configured(request.app.state.settings),
            "daily_limit": request.app.state.settings.receipt_parse_daily_limit}


@router.get("/{receipt_id}")
def detail(receipt_id: UUID, current=Depends(get_identity), db=Depends(get_db)):
    return receipts.view(owned(db, ReceiptImport, receipt_id, current[0].id))


@router.get("/{receipt_id}/file")
def download(receipt_id: UUID, request: Request, current=Depends(get_identity), db=Depends(get_db)):
    row = owned(db, ReceiptImport, receipt_id, current[0].id)
    content = receipts.read_file(request.app.state.settings.receipt_storage_dir, row)
    suffix = "png" if row.media_type == "image/png" else "jpg"
    return Response(content, media_type=row.media_type, headers={
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'attachment; filename="receipt.{suffix}"'})


@router.post("/{receipt_id}/edit")
def edit(receipt_id: UUID, body: ReceiptEditInput, key: Key,
         current=Depends(get_identity), db=Depends(get_db)):
    return receipts.edit(db, current[0].id, key, receipt_id, body)


@router.post("/{receipt_id}/parse")
async def parse(receipt_id: UUID, body: VersionInput, key: Key, request: Request,
                current=Depends(get_identity), db=Depends(get_db)):
    return await receipts.parse(db, current[0].id, key, receipt_id, body,
                                request.app.state.settings.receipt_storage_dir,
                                request.app.state.receipt_parser,
                                request.app.state.settings.receipt_parser_timeout_seconds,
                                request.app.state.settings.receipt_parse_daily_limit)


@router.post("/{receipt_id}/confirm")
def confirm(receipt_id: UUID, body: VersionInput, key: Key,
            current=Depends(get_identity), db=Depends(get_db)):
    return receipts.change(db, current[0].id, key, receipt_id, body, "confirm")


@router.post("/{receipt_id}/cancel")
def cancel(receipt_id: UUID, body: VersionInput, key: Key,
           current=Depends(get_identity), db=Depends(get_db)):
    return receipts.change(db, current[0].id, key, receipt_id, body, "cancel")
