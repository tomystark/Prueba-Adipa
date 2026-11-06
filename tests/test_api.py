import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schema import Questionnaire

client = TestClient(app)
examples = Path(__file__).resolve().parents[1] / "examples"


@pytest.mark.parametrize(("name", "content", "status"), [
    ("quiz.txt", b"1. A question", 415),
    ("quiz.pdf", b"invalid", 422),
    ("quiz.docx", b"", 422),
    ("quiz.xlsx", b"invalid", 422),
    pytest.param("quiz.pdf", b"x" * (8 * 1024 * 1024 + 1), 413, id="oversize"),
])
def test_invalid_upload(name, content, status):
    response = client.post("/api/extract", files={"file": (name, content)})
    assert response.status_code == status


@pytest.mark.parametrize("extension", ["docx", "pdf", "xlsx"])
def test_extract_example(extension):
    path = examples / f"cuestionario.{extension}"
    response = client.post("/api/extract", files={"file": (path.name, path.read_bytes())})
    assert response.status_code == 200, response.text
    expected = json.loads((examples / "cuestionario.json").read_text(encoding="utf-8"))
    assert Questionnaire.model_validate(response.json()).model_dump() == expected


def test_schema_rejects_inconsistent_count():
    expected = json.loads((examples / "cuestionario.json").read_text(encoding="utf-8"))
    expected["total_items"] += 1
    with pytest.raises(ValidationError):
        Questionnaire.model_validate(expected)


@pytest.mark.parametrize(("language", "title", "statement"), [
    ("it", "Questionario di esempio", "Descriva una situazione recente in cui si è sentito sotto pressione."),
    ("en", "Practice questionnaire", "Describe a recent situation where you helped someone at work."),
])
def test_detect_language(language, title, statement):
    from io import BytesIO
    from docx import Document

    doc = Document()
    doc.add_heading(title)
    doc.add_paragraph(f"1. {statement}")
    buffer = BytesIO()
    doc.save(buffer)
    response = client.post("/api/extract", files={"file": ("quiz.docx", buffer.getvalue())})
    assert response.status_code == 200, response.text
    assert response.json()["idioma"] == language


def test_document_without_items():
    from io import BytesIO
    from docx import Document

    doc = Document()
    doc.add_paragraph("Un documento sin preguntas numeradas.")
    buffer = BytesIO()
    doc.save(buffer)
    response = client.post("/api/extract", files={"file": ("quiz.docx", buffer.getvalue())})
    assert response.status_code == 422
    assert "No se detectaron" in response.json()["detail"]
