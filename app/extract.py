import re
from io import BytesIO
from zipfile import ZipFile

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from langdetect import DetectorFactory, LangDetectException, detect
from openpyxl import load_workbook
from pypdf import PdfReader

from app.schema import Alternative, Item, Questionnaire

MAX_BYTES = 8 * 1024 * 1024
DetectorFactory.seed = 0

QUESTION = re.compile(r"^(\d{1,4})[.)]\s+(.+)$")
CHOICE = re.compile(r"^([A-Za-z]|\d{1,2})[.):]\s+(.+)$")
ANSWER = re.compile(r"^(?:respuesta correcta|correct answer|risposta corretta)\s*:\s*(.+)$", re.I)
TYPE = re.compile(r"^\[(escala_likert|seleccion_multiple|verdadero_falso|desarrollo|emparejamiento)\]\s*", re.I)
BOOLEAN_LABELS = [{"verdadero", "falso"}, {"true", "false"}, {"vero", "falso"}]
LIKERT_LABELS = {
    "nunca", "a veces", "frecuentemente", "siempre", "mai", "a volte", "spesso", "sempre",
    "never", "sometimes", "often", "always", "rarely", "raramente", "casi nunca",
    "totalmente en desacuerdo", "en desacuerdo", "de acuerdo", "totalmente de acuerdo",
    "strongly disagree", "disagree", "neutral", "agree", "strongly agree",
}


class InvalidDocument(ValueError):
    pass


def read_lines(extension: str, data: bytes) -> list[str]:
    stream = BytesIO(data)
    if extension == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise InvalidDocument("El archivo no es un PDF válido.")
        reader = PdfReader(stream)
        if reader.is_encrypted or len(reader.pages) > 100:
            raise InvalidDocument("Se requiere un PDF sin contraseña de hasta 100 páginas.")
        return [line for page in reader.pages for line in (page.extract_text() or "").splitlines()]

    with ZipFile(stream) as archive:
        entries = archive.infolist()
        if len(entries) > 2000 or sum(entry.file_size for entry in entries) > 32 * 1024 * 1024:
            raise InvalidDocument("El documento descomprimido supera el límite.")
        required = "word/document.xml" if extension == ".docx" else "xl/workbook.xml"
        if required not in archive.namelist():
            raise InvalidDocument("El contenido no coincide con la extensión.")

    stream.seek(0)
    if extension == ".docx":
        doc = Document(stream)
        lines = []
        for block in doc.iter_inner_content():
            if isinstance(block, Paragraph):
                lines.extend(block.text.splitlines())
            elif isinstance(block, Table):
                for row in block.rows:
                    lines.extend(line for cell in row.cells for line in cell.text.splitlines())
        return lines

    book = load_workbook(stream, read_only=True, data_only=True)
    try:
        return [
            line
            for row in book.active.iter_rows(max_row=min(book.active.max_row or 10000, 10000),
                                             max_col=min(book.active.max_column or 30, 30),
                                             values_only=True)
            for cell in row if cell is not None
            for line in str(cell).splitlines()
        ]
    finally:
        book.close()


def answer_value(raw: str, choices: list[Alternative], kind: str):
    if kind == "emparejamiento":
        pairs = [re.fullmatch(r"([^=,]+)=([^=,]+)", pair.strip()) for pair in raw.split(",")]
        if all(pairs):
            return {pair[1].strip(): pair[2].strip() for pair in pairs}
    for choice in choices:
        if raw.casefold() in {str(choice.valor).casefold(), choice.texto.casefold()}:
            return choice.valor
    return raw or None


def build_item(number: int, statement: str, lines: list[str]) -> Item:
    tag = TYPE.match(statement)
    kind = tag[1].lower() if tag else None
    statement = statement[tag.end():] if tag else statement
    choices = []
    answer = ""
    for line in lines:
        if match := ANSWER.match(line):
            answer = match[1].strip()
        elif match := CHOICE.match(line):
            key, label = match.groups()
            choices.append(Alternative(valor=int(key) if key.isdigit() else key.upper(), texto=label))
        elif not choices and not answer:
            statement += " " + line

    labels = {choice.texto.casefold().rstrip(".") for choice in choices}
    if kind is None:
        if not choices:
            kind = "desarrollo"
        elif labels in BOOLEAN_LABELS:
            kind = "verdadero_falso"
        elif all("→" in choice.texto or "->" in choice.texto for choice in choices):
            kind = "emparejamiento"
        elif len(choices) >= 2 and labels <= LIKERT_LABELS:
            kind = "escala_likert"
        else:
            kind = "seleccion_multiple"
    return Item(numero=number, enunciado=statement, tipo=kind, alternativas=choices,
                respuesta_correcta=answer_value(answer, choices, kind))


def parse(lines: list[str]) -> Questionnaire:
    title = "Cuestionario"
    header = []
    items = []
    body = []
    current = None
    for raw in lines:
        line = " ".join(raw.split())
        if not line:
            continue
        match = QUESTION.match(line)
        if match:
            if current:
                items.append(build_item(*current, body))
            current = (int(match[1]), match[2])
            body = []
        elif current:
            body.append(line)
        else:
            header.append(line)
    if current:
        items.append(build_item(*current, body))
    if not items:
        raise InvalidDocument("No se detectaron ítems numerados en el documento.")
    if header:
        title = header[0]
    language_text = " ".join([title] + [item.enunciado for item in items])
    try:
        language = detect(language_text)
    except LangDetectException:
        language = "und"
    return Questionnaire(titulo=title, idioma=language if language in {"it", "es", "en"} else "und",
                         total_items=len(items), items=items)
