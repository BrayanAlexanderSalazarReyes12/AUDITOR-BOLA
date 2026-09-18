"""Correcciones controladas para una copia LOCAL de Tramitia 2.4.0-rc2.

El corrector nunca escribe en un sistema remoto. Solo modifica archivos dentro
de target_root y crea una copia de respaldo antes de cada cambio.
"""

from __future__ import annotations

import difflib
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from .evidence import EvidenceSession, sha256_file


@dataclass
class CorrectionResult:
    control_id: str
    archivo: str
    applied: bool
    before_hash: str
    after_hash: str
    backup: str
    diff: str
    mensaje: str

    def as_dict(self) -> dict:
        return asdict(self)


def _replace_exact(texto: str, old: str, new: str, control_id: str) -> str:
    if old not in texto:
        raise RuntimeError(
            f"{control_id}: no se encontró el bloque esperado; no se modifica el archivo"
        )
    return texto.replace(old, new, 1)


def _patch(control_id: str, relative: str, texto: str) -> str:
    if control_id in {"P1-BOLA-001", "P1-BOLA-002"}:
        old = '''def puede_acceder(row) -> bool:
    """Verifica que la identidad actual tenga sesion valida sobre la solicitud."""
    usuario = current_user()
    return usuario is not None
'''
        new = '''def puede_acceder(row) -> bool:
    """Autoriza al propietario del objeto o a un coordinador."""
    usuario = current_user()
    return (
        usuario["role"] == COORDINADOR
        or row["propietario"] == usuario["username"]
    )
'''
        return _replace_exact(texto, old, new, control_id)

    if control_id == "P1-SCOPE-003":
        texto = texto.replace(
            "from ..auth import COORDINADOR, CUENTA_SERVICIO, authenticated, current_user",
            "from ..auth import COORDINADOR, authenticated, current_user",
            1,
        )
        old = '''def identidad_efectiva(usuario: dict) -> dict:
    """Identidad con la que se ejecutaran las herramientas del asistente.

    Ver ADR-004: el asistente resuelve sus consultas con la cuenta tecnica de
    la plataforma para no depender del perfil de cada analista.
    """
    return dict(CUENTA_SERVICIO)
'''
        new = '''def identidad_efectiva(usuario: dict) -> dict:
    """Propaga la identidad real del solicitante hacia las herramientas."""
    return dict(usuario)
'''
        return _replace_exact(texto, old, new, control_id)

    if control_id == "P1-RBAC-004":
        texto = texto.replace(
            "from .auth import authenticated",
            "from .auth import COORDINADOR, authenticated, current_user",
            1,
        )
        old = '''def auditoria():
    """Ultimos eventos registrados por la plataforma.

    Lo consume el tablero de soporte para diagnosticar reclamos de usuarios sin
    tener que pedir acceso al servidor.
    """
    limite = request.args.get("limite", type=int) or 100
'''
        new = '''def auditoria():
    """Ultimos eventos registrados, restringidos a coordinación."""
    if current_user()["role"] != COORDINADOR:
        return jsonify(error="acceso no autorizado"), 403
    limite = request.args.get("limite", type=int) or 100
'''
        return _replace_exact(texto, old, new, control_id)

    if control_id == "P2-CORS-001":
        old = '''        origen = request.headers.get("Origin")
        if origen:
            response.headers["Access-Control-Allow-Origin"] = origen
            response.headers["Access-Control-Allow-Credentials"] = "true"
        return response
'''
        new = '''        origen = request.headers.get("Origin")
        permitidos = {
            item.strip()
            for item in os.getenv("TRAMITIA_CORS_ORIGINS", "").split(",")
            if item.strip()
        }
        if origen and origen in permitidos:
            response.headers["Access-Control-Allow-Origin"] = origen
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Vary"] = "Origin"
        return response
'''
        return _replace_exact(texto, old, new, control_id)

    if control_id == "P2-SECRET-002":
        old = '''    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=os.getenv("TRAMITIA_DATABASE", "tramitia.sqlite3"),
        SECRET_KEY=os.getenv("TRAMITIA_SECRET", SECRETO_POR_DEFECTO),
'''
        new = '''    app = Flask(__name__)
    entorno = os.getenv("TRAMITIA_ENV", "development").lower()
    secreto = os.getenv("TRAMITIA_SECRET")
    if entorno == "production" and (not secreto or secreto == SECRETO_POR_DEFECTO):
        raise RuntimeError("TRAMITIA_SECRET debe definirse con un valor seguro en producción")
    secreto = secreto or SECRETO_POR_DEFECTO
    app.config.from_mapping(
        DATABASE=os.getenv("TRAMITIA_DATABASE", "tramitia.sqlite3"),
        SECRET_KEY=secreto,
'''
        return _replace_exact(texto, old, new, control_id)

    if control_id == "P2-LIMIT-003":
        old = '''    # Las tareas marcadas 'urgente' las resuelve el comite fuera de turno,
    # cuando hay una alerta activa, sin esperar los topes ordinarios (ADR-009).
    urgente = bool(data.get("urgente"))

    tarea = str(data.get("tarea", "")).strip()
'''
        new = '''    # La excepción urgente es una capacidad privilegiada del rol coordinador.
    solicita_urgente = bool(data.get("urgente"))
    usuario = current_user()
    if solicita_urgente and usuario["role"] != COORDINADOR:
        record("asistente.urgencia_denegada", solicitante=usuario["username"])
        return problem("la vía urgente requiere el rol coordinador", 403)
    urgente = solicita_urgente

    tarea = str(data.get("tarea", "")).strip()
'''
        texto = _replace_exact(texto, old, new, control_id)
        texto = texto.replace(
            '''
    usuario = current_user()
    presupuesto = current_app.config["ASSISTANT_BUDGET"]
''',
            '''
    presupuesto = current_app.config["ASSISTANT_BUDGET"]
''',
            1,
        )
        return texto

    raise ValueError(f"no existe una corrección automática para {control_id}")


CONTROL_FILES = {
    "P1-BOLA-001": "tramitia/api.py",
    "P1-BOLA-002": "tramitia/api.py",
    "P1-SCOPE-003": "tramitia/asistente/api.py",
    "P1-RBAC-004": "tramitia/admin.py",
    "P2-CORS-001": "tramitia/__init__.py",
    "P2-SECRET-002": "tramitia/__init__.py",
    "P2-LIMIT-003": "tramitia/asistente/api.py",
}


def correction_available(control_id: str) -> bool:
    return control_id in CONTROL_FILES


def apply_correction(
    control_id: str,
    target_root: str | Path,
    evidence: EvidenceSession,
) -> CorrectionResult:
    root = Path(target_root).resolve()
    relative = CONTROL_FILES.get(control_id)
    if not relative:
        raise ValueError(f"no existe corrección automática para {control_id}")

    archivo = (root / relative).resolve()
    if root not in archivo.parents:
        raise ValueError("ruta de corrección fuera del target_root")
    if not archivo.exists():
        raise FileNotFoundError(archivo)

    antes = archivo.read_text(encoding="utf-8")
    before_hash = sha256_file(archivo)

    backup_dir = evidence.root / "cambios" / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / relative.replace("/", "__")
    shutil.copy2(archivo, backup)

    despues = _patch(control_id, relative, antes)
    archivo.write_text(despues, encoding="utf-8")
    after_hash = sha256_file(archivo)

    diff = "".join(
        difflib.unified_diff(
            antes.splitlines(keepends=True),
            despues.splitlines(keepends=True),
            fromfile=f"{relative}.before",
            tofile=f"{relative}.after",
        )
    )
    (evidence.root / "cambios" / f"{control_id}.diff").write_text(
        diff, encoding="utf-8"
    )

    return CorrectionResult(
        control_id=control_id,
        archivo=relative,
        applied=True,
        before_hash=before_hash,
        after_hash=after_hash,
        backup=str(backup),
        diff=diff,
        mensaje="corrección aplicada a la copia local; requiere verificación",
    )


def rollback(result: CorrectionResult, target_root: str | Path) -> None:
    root = Path(target_root).resolve()
    archivo = (root / result.archivo).resolve()
    backup = Path(result.backup)
    if root not in archivo.parents:
        raise ValueError("ruta de rollback fuera del target_root")
    shutil.copy2(backup, archivo)
