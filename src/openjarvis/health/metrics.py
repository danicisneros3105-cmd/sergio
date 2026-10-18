"""What Salud measures: one catalog for the store, the importers and the app.

Each metric has a unit, how a day is summarised (``sum`` for counts like steps,
``avg``/``last``/``min``/``max`` for readings), which way is better, and, when
there is clear public guidance, a range with its source. Ranges describe adults
in general; they are orientation, never a diagnosis.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    unit: str
    category: str  # one of CATEGORIES
    daily: str = "avg"  # sum | avg | last | min | max
    better: str = ""  # up | down | range | ""
    low: Optional[float] = None  # healthy range (when there is clear guidance)
    high: Optional[float] = None
    guide: str = ""  # where the range comes from
    decimals: int = 0
    aliases: Tuple[str, ...] = field(default_factory=tuple)

    def public(self) -> Dict:
        data = asdict(self)
        data.pop("aliases")
        return data


CATEGORIES: Tuple[Tuple[str, str], ...] = (
    ("actividad", "Actividad"),
    ("corazon", "Corazón"),
    ("sueno", "Sueño"),
    ("cuerpo", "Medidas corporales"),
    ("signos", "Signos vitales"),
    ("nutricion", "Nutrición"),
    ("mente", "Mente"),
)

METRICS: Tuple[Metric, ...] = (
    # -- activity
    Metric(
        "steps",
        "Pasos",
        "pasos",
        "actividad",
        "sum",
        "up",
        7000,
        None,
        "Más de 7000 pasos al día se asocian a menor mortalidad (Lancet Public Health, 2022).",
        aliases=(
            "step_count",
            "stepcount",
            "hkquantitytypeidentifierstepcount",
            "pasos",
        ),
    ),
    Metric(
        "active_kcal",
        "Energía activa",
        "kcal",
        "actividad",
        "sum",
        "up",
        aliases=(
            "active_energy",
            "activeenergyburned",
            "hkquantitytypeidentifieractiveenergyburned",
            "calories_active",
        ),
    ),
    Metric(
        "exercise_min",
        "Minutos de ejercicio",
        "min",
        "actividad",
        "sum",
        "up",
        21,
        None,
        "OMS: 150 minutos semanales de actividad moderada (unos 21 al día).",
        aliases=(
            "apple_exercise_time",
            "appleexercisetime",
            "hkquantitytypeidentifierappleexercisetime",
            "exercise_minutes",
            "active_minutes",
        ),
    ),
    Metric(
        "distance_km",
        "Distancia",
        "km",
        "actividad",
        "sum",
        "up",
        decimals=1,
        aliases=(
            "walking_running_distance",
            "distancewalkingrunning",
            "hkquantitytypeidentifierdistancewalkingrunning",
            "distance",
        ),
    ),
    Metric(
        "vo2max",
        "VO2 máx",
        "ml/kg/min",
        "actividad",
        "last",
        "up",
        35,
        None,
        "Forma cardiorrespiratoria: por encima de ~35 es buena en adultos (varía con edad y sexo).",
        decimals=1,
        aliases=("vo2_max", "hkquantitytypeidentifiervo2max"),
    ),
    # -- heart
    Metric(
        "resting_hr",
        "Pulso en reposo",
        "lpm",
        "corazon",
        "avg",
        "down",
        50,
        80,
        "Entre 50 y 80 lpm es lo habitual en adultos sanos.",
        aliases=(
            "resting_heart_rate",
            "restingheartrate",
            "hkquantitytypeidentifierrestingheartrate",
        ),
    ),
    Metric(
        "heart_rate",
        "Pulso",
        "lpm",
        "corazon",
        "avg",
        "",
        aliases=("heartrate", "hkquantitytypeidentifierheartrate", "hr"),
    ),
    Metric(
        "hrv",
        "Variabilidad cardiaca",
        "ms",
        "corazon",
        "avg",
        "up",
        aliases=(
            "heart_rate_variability",
            "heartratevariabilitysdnn",
            "hkquantitytypeidentifierheartratevariabilitysdnn",
            "hrv_ms",
            "rmssd",
        ),
    ),
    Metric(
        "bp_sys",
        "Tensión sistólica",
        "mmHg",
        "corazon",
        "avg",
        "down",
        90,
        120,
        "AHA: normal por debajo de 120/80 mmHg.",
        aliases=(
            "blood_pressure_systolic",
            "bloodpressuresystolic",
            "hkquantitytypeidentifierbloodpressuresystolic",
            "systolic",
        ),
    ),
    Metric(
        "bp_dia",
        "Tensión diastólica",
        "mmHg",
        "corazon",
        "avg",
        "down",
        60,
        80,
        "AHA: normal por debajo de 120/80 mmHg.",
        aliases=(
            "blood_pressure_diastolic",
            "bloodpressurediastolic",
            "hkquantitytypeidentifierbloodpressurediastolic",
            "diastolic",
        ),
    ),
    # -- sleep
    Metric(
        "sleep_h",
        "Sueño",
        "h",
        "sueno",
        "sum",
        "range",
        7,
        9,
        "Adultos: de 7 a 9 horas (Academia Americana de Medicina del Sueño).",
        decimals=1,
        aliases=("sleep_analysis", "sleep", "sleep_hours", "total_sleep", "asleep"),
    ),
    Metric(
        "sleep_deep_h",
        "Sueño profundo",
        "h",
        "sueno",
        "sum",
        "up",
        decimals=1,
        aliases=("deep_sleep", "sleep_deep"),
    ),
    Metric(
        "sleep_rem_h",
        "Sueño REM",
        "h",
        "sueno",
        "sum",
        "up",
        decimals=1,
        aliases=("rem_sleep", "sleep_rem"),
    ),
    # -- body
    Metric(
        "weight_kg",
        "Peso",
        "kg",
        "cuerpo",
        "last",
        "",
        decimals=1,
        aliases=("weight", "body_mass", "bodymass", "hkquantitytypeidentifierbodymass"),
    ),
    Metric(
        "body_fat_pct",
        "Grasa corporal",
        "%",
        "cuerpo",
        "last",
        "down",
        decimals=1,
        aliases=(
            "body_fat_percentage",
            "bodyfatpercentage",
            "hkquantitytypeidentifierbodyfatpercentage",
            "fat_ratio",
        ),
    ),
    Metric(
        "bmi",
        "Índice de masa corporal",
        "",
        "cuerpo",
        "last",
        "range",
        18.5,
        25,
        "OMS: de 18,5 a 24,9 es el rango normal.",
        decimals=1,
        aliases=(
            "body_mass_index",
            "bodymassindex",
            "hkquantitytypeidentifierbodymassindex",
        ),
    ),
    # -- vitals
    Metric(
        "spo2",
        "Oxígeno en sangre",
        "%",
        "signos",
        "avg",
        "up",
        95,
        100,
        "En reposo y a nivel del mar, lo normal es 95 % o más.",
        aliases=(
            "blood_oxygen_saturation",
            "oxygen_saturation",
            "oxygensaturation",
            "hkquantitytypeidentifieroxygensaturation",
        ),
    ),
    Metric(
        "resp_rate",
        "Frecuencia respiratoria",
        "rpm",
        "signos",
        "avg",
        "range",
        12,
        20,
        "En reposo, de 12 a 20 respiraciones por minuto.",
        decimals=1,
        aliases=(
            "respiratory_rate",
            "respiratoryrate",
            "hkquantitytypeidentifierrespiratoryrate",
        ),
    ),
    Metric(
        "temp_c",
        "Temperatura",
        "°C",
        "signos",
        "avg",
        "range",
        36.1,
        37.2,
        "Entre 36,1 y 37,2 °C es lo habitual.",
        decimals=1,
        aliases=(
            "body_temperature",
            "temperature",
            "temp",
            "bodytemperature",
            "hkquantitytypeidentifierbodytemperature",
        ),
    ),
    Metric(
        "glucose",
        "Glucosa",
        "mg/dL",
        "signos",
        "avg",
        "range",
        70,
        140,
        "Entre 70 y 140 mg/dL a lo largo del día en personas sin diabetes.",
        aliases=(
            "blood_glucose",
            "bloodglucose",
            "hkquantitytypeidentifierbloodglucose",
        ),
    ),
    # -- nutrition
    Metric(
        "kcal_in",
        "Energía consumida",
        "kcal",
        "nutricion",
        "sum",
        "",
        aliases=(
            "dietary_energy",
            "dietaryenergyconsumed",
            "hkquantitytypeidentifierdietaryenergyconsumed",
            "calories_in",
        ),
    ),
    Metric(
        "protein_g",
        "Proteína",
        "g",
        "nutricion",
        "sum",
        "up",
        aliases=("dietaryprotein", "hkquantitytypeidentifierdietaryprotein", "protein"),
    ),
    Metric(
        "water_ml",
        "Agua",
        "ml",
        "nutricion",
        "sum",
        "up",
        2000,
        None,
        "Orientación general: unos 2 litros al día, más con calor o ejercicio.",
        aliases=(
            "dietary_water",
            "dietarywater",
            "hkquantitytypeidentifierdietarywater",
            "water",
        ),
    ),
    Metric(
        "caffeine_mg",
        "Cafeína",
        "mg",
        "nutricion",
        "sum",
        "down",
        None,
        400,
        "FDA: hasta 400 mg al día en adultos sanos.",
        aliases=(
            "dietary_caffeine",
            "dietarycaffeine",
            "hkquantitytypeidentifierdietarycaffeine",
            "caffeine",
        ),
    ),
    # -- mind
    Metric(
        "mood",
        "Ánimo",
        "/5",
        "mente",
        "avg",
        "up",
        aliases=("state_of_mind", "stateofmind", "animo"),
    ),
    Metric(
        "mindful_min",
        "Minutos de calma",
        "min",
        "mente",
        "sum",
        "up",
        aliases=(
            "mindful_minutes",
            "mindfulsession",
            "hkcategorytypeidentifiermindfulsession",
        ),
    ),
)

BY_KEY: Dict[str, Metric] = {m.key: m for m in METRICS}


def _norm(name: str) -> str:
    return "".join(
        ch for ch in (name or "").lower() if ch.isalnum() or ch == "_"
    ).replace("__", "_")


_ALIASES: Dict[str, str] = {}
for _m in METRICS:
    _ALIASES[_norm(_m.key)] = _m.key
    _ALIASES[_norm(_m.key).replace("_", "")] = _m.key
    for _a in _m.aliases:
        _ALIASES[_norm(_a)] = _m.key
        _ALIASES[_norm(_a).replace("_", "")] = _m.key


def resolve(name: str) -> Optional[str]:
    """Our key for a metric name from any app ("step_count", "HKQuantity…StepCount")."""
    n = _norm(name)
    return _ALIASES.get(n) or _ALIASES.get(n.replace("_", ""))


def classify(metric: Metric, value: float) -> str:
    """'ok' | 'low' | 'high' | '' (no guidance) for one value."""
    if metric.low is None and metric.high is None:
        return ""
    if metric.low is not None and value < metric.low:
        return "low"
    if metric.high is not None and value > metric.high:
        return "high"
    return "ok"


def catalog() -> List[Dict]:
    return [m.public() for m in METRICS]


__all__ = [
    "BY_KEY",
    "CATEGORIES",
    "METRICS",
    "Metric",
    "catalog",
    "classify",
    "resolve",
]
