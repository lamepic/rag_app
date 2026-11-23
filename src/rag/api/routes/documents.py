"""Upload papers into a collection and read them back."""

import uuid

from fastapi import APIRouter, HTTPException, UploadFile, status

from rag.api.deps import BlobStoreDep, CurrentUserDep, SettingsDep, UnitOfWorkDep
from rag.api.schemas import DocumentList, DocumentOut
from rag.core.collections import CollectionNotFoundError
from rag.core.documents import DuplicateDocumentError
from rag.core.storage import BlobStoreError
from rag.ingestion.upload import FileTooLargeError, NotAPdfError, upload_document

router = APIRouter(prefix="/v1", tags=["documents"])


# Functions, not shared instances: raising modifies an exception (traceback, __cause__),
# so one instance re-raised by concurrent requests would mix their state.
def collection_not_found() -> HTTPException:
    # 404 even when it exists for someone else: a 403 would confirm it exists.
    return HTTPException(status.HTTP_404_NOT_FOUND, "Collection not found")


def document_not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")


@router.post(
    "/collections/{collection_id}/documents",
    status_code=status.HTTP_202_ACCEPTED,  # stored and queued; processing happens later
)
async def upload(
    collection_id: uuid.UUID,
    file: UploadFile,
    user: CurrentUserDep,
    uow: UnitOfWorkDep,
    blobs: BlobStoreDep,
    settings: SettingsDep,
) -> DocumentOut:
    try:
        document = await upload_document(
            uow=uow,
            blobs=blobs,
            owner_id=user.id,
            collection_id=collection_id,
            filename=file.filename,
            file=file.file,
            max_bytes=settings.max_upload_bytes,
        )
    except CollectionNotFoundError as exc:
        raise collection_not_found() from exc
    except NotAPdfError as exc:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only PDF files are accepted"
        ) from exc
    except FileTooLargeError as exc:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"File exceeds {exc.max_bytes} bytes"
        ) from exc
    except DuplicateDocumentError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "message": "This file is already in the collection",
                "document_id": str(exc.existing_id) if exc.existing_id else None,
            },
        ) from exc
    except BlobStoreError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Storage unavailable") from exc
    return DocumentOut.model_validate(document)


@router.get("/collections/{collection_id}/documents")
async def list_documents(
    collection_id: uuid.UUID, user: CurrentUserDep, uow: UnitOfWorkDep
) -> DocumentList:
    if await uow.collections.get(collection_id, owner_id=user.id) is None:
        raise collection_not_found()
    documents = await uow.documents.list_for_collection(collection_id, owner_id=user.id)
    return DocumentList(items=[DocumentOut.model_validate(d) for d in documents])


@router.get("/documents/{document_id}")
async def get_document(
    document_id: uuid.UUID, user: CurrentUserDep, uow: UnitOfWorkDep
) -> DocumentOut:
    document = await uow.documents.get(document_id, owner_id=user.id)
    if document is None:
        raise document_not_found()
    return DocumentOut.model_validate(document)
