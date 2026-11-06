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
@pytest.mark.parametrize("stem", ["cuestionario", "cuestionario-en", "cuestionario-it"])
def test_extract_example(extension, stem):
    path = examples / f"{stem}.{extension}"
    response = client.post("/api/extract", files={"file": (path.name, path.read_bytes())})
    assert response.status_code == 200, response.text
    expected = json.loads((examples / f"{stem}.json").read_text(encoding="utf-8"))
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


def upload_questionnaire(*lines):
    from io import BytesIO
    from docx import Document

    doc = Document()
    for line in lines:
        doc.add_paragraph(line)
    buffer = BytesIO()
    doc.save(buffer)
    return client.post("/api/extract", files={"file": ("quiz.docx", buffer.getvalue())})


def test_dot_numbered_likert_choices():
    response = upload_questionnaire(
        "Practice quiz", "1. How often do you check your tools?", "0. Never", "1. Always",
        "2. Describe your process.",
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["total_items"] == 2
    assert result["items"][0]["tipo"] == "escala_likert"
    assert result["items"][0]["alternativas"] == [
        {"valor": 0, "texto": "Never"}, {"valor": 1, "texto": "Always"},
    ]
    assert result["items"][1]["numero"] == 2


@pytest.mark.parametrize("heading", ["Answer key", "Clave de respuestas:", "Soluzioni"])
def test_trailing_answer_key(heading):
    response = upload_questionnaire(
        "Practice quiz", "1. Which answer is correct?", "A) One", "B) Two",
        "2. Describe your reasoning.", heading, "1. B",
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["total_items"] == 2
    assert [item["respuesta_correcta"] for item in result["items"]] == ["B", None]


@pytest.mark.parametrize("entry", ["1. Z", "9. B"])
def test_reject_invalid_trailing_key(entry):
    response = upload_questionnaire(
        "Practice quiz", "1. Which answer is correct?", "A) One", "B) Two",
        "Answer key", entry,
    )
    assert response.status_code == 422


def test_reject_ambiguous_numbering():
    response = upload_questionnaire("Practice quiz", "1. Choose a color.", "1. Blue", "2. Green")
    assert response.status_code == 422
    assert "Numeración ambigua" in response.json()["detail"]


@pytest.mark.parametrize(("key", "status"), [("B", 200), ("Steel", 200), ("Z", 422)])
def test_inline_choice_key(key, status):
    response = upload_questionnaire(
        "Practice quiz", "1. Which material is correct?", "A) Copper", "B) Steel",
        f"Correct answer: {key}",
    )
    assert response.status_code == status, response.text
    if status == 200:
        assert response.json()["items"][0]["respuesta_correcta"] == "B"
    else:
        assert "alternativa del ítem 1" in response.json()["detail"]
