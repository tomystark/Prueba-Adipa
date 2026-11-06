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
KEY_HEADING = re.compile(r"^(?:answer key|clave de respuestas|soluzioni)\s*:?$", re.I)
KEY_ENTRY = re.compile(r"^(\d{1,4})[.):]\s*(\S.*)$")
DOT_CHOICE = re.compile(r"^(\d{1,2})\.\s+(.+)$")
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


def dot_scale_end(lines: list[str], start: int) -> int:
    """Find consecutive dot-numbered choices with distinct, recognized labels."""
    end = start
    labels = set()
    first = DOT_CHOICE.match(lines[start])
    if first is None or int(first[1]) not in {0, 1}:
        return start
    number = int(first[1])
    while end < len(lines):
        match = DOT_CHOICE.match(lines[end])
        if match is None or int(match[1]) != number:
            break
        label = match[2].casefold().rstrip(".")
        if label not in LIKERT_LABELS or label in labels:
            break
        labels.add(label)
        number += 1
        end += 1
    return end if len(labels) >= 2 else start


def apply_answer_key(items: list[Item], lines: list[str]) -> None:
    by_number = {item.numero: item for item in items}
    seen = set()
    if not lines:
        raise InvalidDocument("La clave de respuestas está vacía.")
    for line in lines:
        match = KEY_ENTRY.match(line)
        if match is None:
            raise InvalidDocument("Usa el formato «1. B» en la clave de respuestas.")
        number = int(match[1])
        if number not in by_number or number in seen:
            raise InvalidDocument(f"Número de ítem desconocido o repetido en la clave: {number}.")
        seen.add(number)
        item = by_number[number]
        answer = answer_value(match[2], item.alternativas, item.tipo)
        if item.tipo == "emparejamiento":
            if not isinstance(answer, dict):
                raise InvalidDocument(f"Usa pares «origen=destino» en la clave del ítem {number}.")
        elif item.alternativas and answer not in {choice.valor for choice in item.alternativas}:
            raise InvalidDocument(f"La respuesta de la clave no coincide con una alternativa del ítem {number}.")
        if item.respuesta_correcta is not None and item.respuesta_correcta != answer:
            raise InvalidDocument(f"Las claves del ítem {number} indican respuestas diferentes.")
        item.respuesta_correcta = answer


def parse(lines: list[str]) -> Questionnaire:
    title = "Cuestionario"
    header = []
    items = []
    body = []
    current = None
    normalized = [line for raw in lines if (line := " ".join(raw.split()))]
    key_lines = None
    index = 0
    seen_numbers = set()
    while index < len(normalized):
        line = normalized[index]
        if current and KEY_HEADING.fullmatch(line):
            key_lines = normalized[index + 1:]
            break
        if match := QUESTION.match(line):
            if current and not any(CHOICE.match(part) or ANSWER.match(part) for part in body):
                end = dot_scale_end(normalized, index)
                if end > index:
                    body.extend(normalized[index:end])
                    index = end
                    continue
            number = int(match[1])
            if number in seen_numbers or (current and number == 0):
                raise InvalidDocument(
                    f"Numeración ambigua en el ítem {number}. Usa «0: Nunca» para opciones numéricas "
                    "o agrega un encabezado a la clave de respuestas."
                )
            if current:
                items.append(build_item(*current, body))
            seen_numbers.add(number)
            current = (number, match[2])
            body = []
        elif current:
            body.append(line)
        else:
            header.append(line)
        index += 1
    if current:
        items.append(build_item(*current, body))
    if key_lines is not None:
        apply_answer_key(items, key_lines)
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
