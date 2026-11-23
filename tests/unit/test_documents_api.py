"""Document routes: status codes, body limits and owner isolation."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

from rag.config import Settings
from tests.fakes import InMemoryBlobStore
from tests.unit.conftest import AuthHeaders

MAX_UPLOAD = 10_000
PDF = b"%PDF-1.7\n" + b"x" * 1000


@pytest.fixture
def settings(settings: Settings) -> Settings:
    """A small upload limit so size tests don't need megabytes of data."""
    return settings.model_copy(update={"max_upload_bytes": MAX_UPLOAD})


async def make_collection(client: httpx.AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post("/v1/collections", json={"name": "thesis"}, headers=headers)
    collection_id: str = response.json()["id"]
    return collection_id


def pdf_upload(data: bytes = PDF, filename: str = "paper.pdf") -> dict[str, tuple[str, bytes, str]]:
    return {"file": (filename, data, "application/pdf")}


# --- upload -----------------------------------------------------------------------------


async def test_upload_returns_202_with_a_queued_document(
    client: httpx.AsyncClient, auth_headers: AuthHeaders, blobs: InMemoryBlobStore
) -> None:
    headers = auth_headers()
    collection_id = await make_collection(client, headers)

    response = await client.post(
        f"/v1/collections/{collection_id}/documents", files=pdf_upload(), headers=headers
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["filename"] == "paper.pdf"
    assert body["size_bytes"] == len(PDF)
    assert body["collection_id"] == collection_id
    assert "storage_key" not in body and "owner_id" not in body
    assert len(blobs.objects) == 1


async def test_content_type_header_is_not_trusted(
    client: httpx.AsyncClient, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers()
    collection_id = await make_collection(client, headers)

    response = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("evil.pdf", b"MZ\x90\x00 an .exe", "application/pdf")},
        headers=headers,
    )

    assert response.status_code == 415


async def test_duplicate_is_409_with_the_existing_id(
    client: httpx.AsyncClient, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers()
    collection_id = await make_collection(client, headers)
    url = f"/v1/collections/{collection_id}/documents"
    first = await client.post(url, files=pdf_upload(), headers=headers)

    response = await client.post(url, files=pdf_upload(filename="copy.pdf"), headers=headers)

    assert response.status_code == 409
    assert response.json()["detail"]["document_id"] == first.json()["id"]


async def test_file_over_the_limit_is_413(
    client: httpx.AsyncClient, auth_headers: AuthHeaders, blobs: InMemoryBlobStore
) -> None:
    """Over max_upload_bytes but under the body limit: caught by the service's exact count."""
    headers = auth_headers()
    collection_id = await make_collection(client, headers)

    response = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files=pdf_upload(b"%PDF-" + b"x" * MAX_UPLOAD),
        headers=headers,
    )

    assert response.status_code == 413
    assert blobs.objects == {}


async def test_body_over_the_route_limit_is_cut_off(
    client: httpx.AsyncClient, auth_headers: AuthHeaders
) -> None:
    """Over max_upload_bytes + 1 MiB: rejected by the body limit before the route runs."""
    headers = auth_headers()
    collection_id = await make_collection(client, headers)

    response = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files=pdf_upload(b"%PDF-" + b"x" * (2 * 1024 * 1024)),
        headers=headers,
    )

    assert response.status_code == 413


async def test_streamed_body_without_content_length_is_cut_off(
    client: httpx.AsyncClient, auth_headers: AuthHeaders
) -> None:
    """Chunked encoding has no Content-Length; the limit counts bytes as they arrive."""
    headers = auth_headers()
    collection_id = await make_collection(client, headers)

    async def endless() -> AsyncIterator[bytes]:
        # A valid multipart opening, then a file part that keeps going: 4 MiB in 64 KiB chunks.
        yield (
            b"--x\r\n"
            b'Content-Disposition: form-data; name="file"; filename="big.pdf"\r\n'
            b"Content-Type: application/pdf\r\n\r\n%PDF-"
        )
        for _ in range(64):
            yield b"x" * 65536

    response = await client.post(
        f"/v1/collections/{collection_id}/documents",
        content=endless(),
        headers={**headers, "Content-Type": "multipart/form-data; boundary=x"},
    )

    assert response.status_code == 413


async def test_json_endpoints_have_a_small_body_limit(
    client: httpx.AsyncClient, auth_headers: AuthHeaders
) -> None:
    response = await client.post(
        "/v1/collections",
        json={"name": "x", "description": "y" * (2 * 1024 * 1024)},
        headers=auth_headers(),
    )
    assert response.status_code == 413


async def test_missing_file_field_is_422(
    client: httpx.AsyncClient, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers()
    collection_id = await make_collection(client, headers)

    response = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"wrong_field": ("paper.pdf", PDF, "application/pdf")},
        headers=headers,
    )

    assert response.status_code == 422


async def test_storage_down_is_503(
    client: httpx.AsyncClient, auth_headers: AuthHeaders, blobs: InMemoryBlobStore
) -> None:
    headers = auth_headers()
    collection_id = await make_collection(client, headers)
    blobs.fail = True

    response = await client.post(
        f"/v1/collections/{collection_id}/documents", files=pdf_upload(), headers=headers
    )

    assert response.status_code == 503


# --- owner isolation --------------------------------------------------------------------


async def test_other_users_collection_looks_missing(
    client: httpx.AsyncClient, auth_headers: AuthHeaders
) -> None:
    owner, intruder = auth_headers(), auth_headers()
    collection_id = await make_collection(client, owner)
    url = f"/v1/collections/{collection_id}/documents"

    upload = await client.post(url, files=pdf_upload(), headers=intruder)
    listing = await client.get(url, headers=intruder)

    assert upload.status_code == 404
    assert listing.status_code == 404


async def test_other_users_document_looks_missing(
    client: httpx.AsyncClient, auth_headers: AuthHeaders
) -> None:
    owner, intruder = auth_headers(), auth_headers()
    collection_id = await make_collection(client, owner)
    uploaded = await client.post(
        f"/v1/collections/{collection_id}/documents", files=pdf_upload(), headers=owner
    )
    document_id = uploaded.json()["id"]

    mine = await client.get(f"/v1/documents/{document_id}", headers=owner)
    theirs = await client.get(f"/v1/documents/{document_id}", headers=intruder)

    assert mine.status_code == 200
    assert theirs.status_code == 404


async def test_unknown_ids_are_404(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    headers = auth_headers()
    assert (await client.get(f"/v1/documents/{uuid.uuid4()}", headers=headers)).status_code == 404
    assert (
        await client.get(f"/v1/collections/{uuid.uuid4()}/documents", headers=headers)
    ).status_code == 404


# --- listing ----------------------------------------------------------------------------


async def test_list_returns_documents_newest_first(
    client: httpx.AsyncClient, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers()
    collection_id = await make_collection(client, headers)
    url = f"/v1/collections/{collection_id}/documents"
    await client.post(url, files=pdf_upload(PDF + b"1", "first.pdf"), headers=headers)
    await client.post(url, files=pdf_upload(PDF + b"2", "second.pdf"), headers=headers)

    response = await client.get(url, headers=headers)

    assert response.status_code == 200
    assert [d["filename"] for d in response.json()["items"]] == ["second.pdf", "first.pdf"]
