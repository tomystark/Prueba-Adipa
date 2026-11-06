from typing import Literal

from pydantic import BaseModel, model_validator


class Alternative(BaseModel):
    valor: int | str
    texto: str


class Item(BaseModel):
    numero: int
    enunciado: str
    tipo: Literal["escala_likert", "seleccion_multiple", "verdadero_falso", "desarrollo", "emparejamiento"]
    alternativas: list[Alternative]
    respuesta_correcta: int | str | dict[str, str] | None = None


class Questionnaire(BaseModel):
    titulo: str
    idioma: Literal["it", "es", "en", "und"]
    total_items: int
    items: list[Item]

    @model_validator(mode="after")
    def check_count(self):
        if self.total_items != len(self.items) or not self.items:
            raise ValueError("total_items debe coincidir con la lista de ítems")
        return self
