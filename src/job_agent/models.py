"""Modelos de datos: la oferta cruda, la candidata filtrada y la evaluación del LLM."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Job(BaseModel):
    """Una oferta tal como la devuelve la API de Himalayas (solo los campos que usamos)."""

    model_config = ConfigDict(extra="ignore")

    guid: str
    title: str
    company_name: str = Field(alias="companyName")
    employment_type: str | None = Field(default=None, alias="employmentType")
    min_salary: float | None = Field(default=None, alias="minSalary")
    max_salary: float | None = Field(default=None, alias="maxSalary")
    salary_period: str | None = Field(default=None, alias="salaryPeriod")
    currency: str | None = None
    seniority: list[str] = Field(default_factory=list)
    location_restrictions: list[str] = Field(default_factory=list, alias="locationRestrictions")
    timezone_restrictions: list[float] = Field(default_factory=list, alias="timezoneRestrictions")
    description: str = ""
    pub_date: int | None = Field(default=None, alias="pubDate")
    expiry_date: int | None = Field(default=None, alias="expiryDate")
    application_link: str = Field(alias="applicationLink")


class RangoSalario(BaseModel):
    min: int
    max: int


class Candidata(BaseModel):
    """Oferta que pasó los filtros determinísticos y va a evaluar el LLM."""

    titulo: str
    empresa: str
    tipo: str | None
    seniority: list[str]
    salario_usd_mes: RangoSalario | None
    salario_original: str
    por_hora: bool
    paises_validos: list[str]
    publicada: str | None
    link: str
    descripcion: str


class Evaluacion(BaseModel):
    """Lo que devuelve el LLM. Su JSON Schema es el que se le pasa al SDK (output_format)."""

    encaje: int = Field(ge=0, le=100)
    veredicto: Literal["aplicar", "dudoso", "descartar"]
    tipo_puesto: Literal[
        "ingeniería AI/LLM",
        "full stack / frontend",
        "entrenamiento de IA / gig",
        "otro (ventas, research, etc.)",
    ]
    elegible_ubicacion: Literal["sí", "no", "no claro"]
    salario_detectado: str
    cumple: list[str]
    falta: list[str]
    red_flags: list[str]
    resumen: str


class CandidataEvaluada(BaseModel):
    candidata: Candidata
    evaluacion: Evaluacion
    costo_usd: float | None = None
    duracion_ms: int | None = None
