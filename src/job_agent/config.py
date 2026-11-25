"""Rutas del proyecto y carga de los criterios de búsqueda."""

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field

RAIZ = Path(__file__).resolve().parents[2]
PRIVADO = RAIZ / "private"  # ignorado por git: CV, criterios, resultados
CRITERIOS = PRIVADO / "criterios.json"
CV = PRIVADO / "cv-en.md"
CANDIDATAS = PRIVADO / "candidatas.json"
EVALUADAS = PRIVADO / "evaluadas.json"

# Modelo por tarea. Evaluar es leer y clasificar, se repite mucho y es lo que más cupo gasta:
# va con el modelo chico. Cartas y agente escriben o deciden: modelo intermedio.
# Se cambian sin tocar código, por ej.: JOB_AGENT_MODELO_EVALUADOR=sonnet
MODELO_EVALUADOR = os.environ.get("JOB_AGENT_MODELO_EVALUADOR", "haiku")
MODELO_CARTA = os.environ.get("JOB_AGENT_MODELO_CARTA", "sonnet")
MODELO_AGENTE = os.environ.get("JOB_AGENT_MODELO_AGENTE", "sonnet")


class ZonaHoraria(BaseModel):
    min_utc: float = Field(alias="minUTC")
    max_utc: float = Field(alias="maxUTC")
    tolerancia_horas: float = Field(default=0, alias="toleranciaHoras")


class Criterios(BaseModel):
    nombre: str = ""  # firma de las cartas
    roles: list[str]
    idioma: str = ""
    zona_horaria: ZonaHoraria = Field(alias="zonaHoraria")
    paises_residencia: list[str] = Field(alias="paisesResidencia")
    # Lugares entre los que se reparte el año, cada uno como lista de países. Una oferta tiene
    # "cobertura total" si acepta al menos un país de cada grupo (o cualquier país).
    zonas_residencia: list[list[str]] = Field(default_factory=list, alias="zonasResidencia")
    incluir_parciales: bool = Field(default=False, alias="incluirParciales")
    excluir_seniority: list[str] = Field(default_factory=list, alias="excluirSeniority")
    salario_minimo_usd_mes: float = Field(alias="salarioMinimoUSDMes")
    situacion: str = ""  # texto libre para el LLM: residencia, modalidad, etc.


def cargar_criterios(ruta: Path = CRITERIOS) -> Criterios:
    return Criterios.model_validate(json.loads(ruta.read_text(encoding="utf-8")))
