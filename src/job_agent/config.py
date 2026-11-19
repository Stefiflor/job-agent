"""Rutas del proyecto y carga de los criterios de búsqueda."""

import json
from pathlib import Path

from pydantic import BaseModel, Field

RAIZ = Path(__file__).resolve().parents[2]
PRIVADO = RAIZ / "private"  # ignorado por git: CV, criterios, resultados
CRITERIOS = PRIVADO / "criterios.json"
CV = PRIVADO / "cv-en.md"
CANDIDATAS = PRIVADO / "candidatas.json"
EVALUADAS = PRIVADO / "evaluadas.json"


class ZonaHoraria(BaseModel):
    min_utc: float = Field(alias="minUTC")
    max_utc: float = Field(alias="maxUTC")
    tolerancia_horas: float = Field(default=0, alias="toleranciaHoras")


class Criterios(BaseModel):
    roles: list[str]
    idioma: str = ""
    zona_horaria: ZonaHoraria = Field(alias="zonaHoraria")
    paises_residencia: list[str] = Field(alias="paisesResidencia")
    excluir_seniority: list[str] = Field(default_factory=list, alias="excluirSeniority")
    salario_minimo_usd_mes: float = Field(alias="salarioMinimoUSDMes")
    situacion: str = ""  # texto libre para el LLM: residencia, modalidad, etc.


def cargar_criterios(ruta: Path = CRITERIOS) -> Criterios:
    return Criterios.model_validate(json.loads(ruta.read_text(encoding="utf-8")))
