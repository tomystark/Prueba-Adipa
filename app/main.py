import logging
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

from app.extract import MAX_BYTES, InvalidDocument, parse, read_lines
from app.schema import Questionnaire

app = FastAPI(title="Extractor de cuestionarios")
logger = logging.getLogger(__name__)


@app.post("/api/extract", response_model=Questionnaire)
def extract(file: UploadFile = File(...)):
    extension = Path(file.filename or "").suffix.lower()
    if extension not in {".pdf", ".docx", ".xlsx"}:
        raise HTTPException(415, "Selecciona un archivo PDF, DOCX o XLSX.")
    data = file.file.read(MAX_BYTES + 1)
    if not data:
        raise HTTPException(422, "El archivo está vacío.")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "El archivo supera el límite de 8 MiB.")
    try:
        lines = read_lines(extension, data)
    except InvalidDocument as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        logger.warning("Error al abrir %s (%s)", extension, type(exc).__name__)
        raise HTTPException(422, "No se pudo leer el documento. Revisa que sea válido.") from exc
    try:
        return parse(lines)
    except InvalidDocument as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        logger.error("Error durante la extracción (%s)", type(exc).__name__)
        raise HTTPException(500, "Ocurrió un error durante la extracción.") from exc


dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if dist.is_dir():
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
