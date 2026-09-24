"""Motor determinista del Pilar 1: Identidad y Control de Acceso."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
import requests
from typing import Any, Callable

from .agent_scope import ResultadoAlcanceAgente, evaluar_alcance_agente
from .config import ConfigObjetivo, Cuenta, Endpoint
from .transport import request_http


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Hallazgo:
    sistema: str
    endpoint: str
    metodo: str
    cuenta: str
    rol: str
    acceso_esperado: bool
    acceso_real: bool
    http_status: int
    confirmado_bola: bool
    ts: str
    id_control: str | None = None
    descripcion: str | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ResultadoAcceso:
    sistema: str
    id_control: str
    nombre: str
    cuenta: str
    rol: str
    endpoint: str
    metodo: str
    acceso_esperado: bool
    acceso_real: bool
    http_status: int
    vulnerable: bool
    ts: str
    error: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ResultadoMatrizAcceso:
    sistema: str
    cuenta: str
    rol: str
    endpoint_detectado: str
    endpoint_ejecutado: str | None
    metodo: str
    http_status: int | None
    acceso_real: bool | None
    acceso_esperado: bool | None
    vulnerable: bool | None
    clasificacion: str
    fuente_politica: str | None
    confianza: str | None
    id_control_referencia: str | None
    detalle: str
    ts: str
    response_signature: str | None = None
    response_shape: dict[str, Any] | None = None
    object_count: int | None = None
    object_ids: list[str] | None = None
    response_comparison: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class HallazgoAgente:
    sistema: str
    id_control: str
    nombre_chequeo: str
    cuenta: str
    resultado: ResultadoAlcanceAgente
    ts: str

    def as_dict(self) -> dict:
        data = asdict(self)
        data["resultado"] = asdict(self.resultado)
        return data


def _acceso_esperado(
    cuenta: Cuenta, endpoint: Endpoint, roles_privilegiados: list[str]
) -> bool:
    es_propietario = cuenta.username == endpoint.propietario_esperado
    es_privilegiado = cuenta.role in roles_privilegiados
    return es_propietario or es_privilegiado


def _armar_url(base_url: str, endpoint: Endpoint) -> str:
    return base_url + endpoint.ruta.format(id=endpoint.id_prueba)


def _disparar(base_url: str, endpoint: Endpoint, cuenta: Cuenta):
    return request_http(
        endpoint.metodo,
        _armar_url(base_url, endpoint),
        cuenta=cuenta,
        base_url=base_url,
        cuerpo=endpoint.cuerpo_prueba,
    )


def auditar(
    cfg: ConfigObjetivo,
    progress_callback: Callable[[str], None] | None = None,
) -> list[Hallazgo]:
    """Prueba BOLA para cada combinación cuenta + endpoint declarada."""
    hallazgos: list[Hallazgo] = []
    for endpoint in cfg.endpoints:
        start_index = len(hallazgos)
        for cuenta in cfg.cuentas:
            esperado = _acceso_esperado(cuenta, endpoint, cfg.roles_privilegiados)
            error = None
            status = 0
            try:
                resp = _disparar(cfg.base_url, endpoint, cuenta)
                status = resp.status_code
                if status not in (*endpoint.codigos_permitidos, 401, 403, 404):
                    error = f"Respuesta no concluyente: HTTP {status}"
                elif esperado and status not in endpoint.codigos_permitidos:
                    error = f"La cuenta autorizada no pudo acceder al objeto (HTTP {status})"
            except requests.RequestException as exc:
                error = f"No se pudo ejecutar la prueba: {type(exc).__name__}"
            real = status in endpoint.codigos_permitidos and error is None
            confirmado = real and not esperado
            hallazgos.append(
                Hallazgo(
                    sistema=cfg.sistema,
                    endpoint=endpoint.ruta,
                    metodo=endpoint.metodo.upper(),
                    cuenta=cuenta.username,
                    rol=cuenta.role,
                    acceso_esperado=esperado,
                    acceso_real=real,
                    http_status=status,
                    confirmado_bola=confirmado,
                    ts=_ts(),
                    id_control=endpoint.id_control,
                    descripcion=endpoint.descripcion,
                    error=error,
                )
            )
            if progress_callback:
                progress_callback(
                    "Pilar 1 · BOLA · "
                    f"{endpoint.metodo.upper()} {endpoint.ruta} · "
                    f"cuenta {cuenta.username}"
                )
        baseline = [item for item in hallazgos[start_index:] if item.acceso_esperado]
        if baseline and not any(item.acceso_real for item in baseline):
            for item in hallazgos[start_index:]:
                item.error = item.error or "Objeto no validado con una cuenta autorizada"
                item.confirmado_bola = False
    return hallazgos


def auditar_controles_acceso(
    cfg: ConfigObjetivo,
    progress_callback: Callable[[str], None] | None = None,
) -> list[ResultadoAcceso]:
    """Ejecuta controles RBAC/ABAC puntuales declarados en la configuración."""
    resultados: list[ResultadoAcceso] = []
    for chequeo in cfg.chequeos_acceso:
        cuenta = cfg.cuenta_por_username(chequeo.cuenta)
        if cuenta is None:
            raise ValueError(
                f"control '{chequeo.id_control}': cuenta '{chequeo.cuenta}' no configurada"
            )
        error = None
        status = 0
        try:
            resp = request_http(
                chequeo.metodo, cfg.base_url + chequeo.ruta,
                cuenta=cuenta, base_url=cfg.base_url, cuerpo=chequeo.cuerpo,
            )
            status = resp.status_code
            if status not in (*chequeo.codigos_permitidos, 401, 403):
                error = f"Respuesta no concluyente: HTTP {status}"
        except requests.RequestException as exc:
            error = f"No se pudo ejecutar la prueba: {type(exc).__name__}"
        real = status in chequeo.codigos_permitidos and error is None
        resultados.append(
            ResultadoAcceso(
                sistema=cfg.sistema,
                id_control=chequeo.id_control,
                nombre=chequeo.nombre,
                cuenta=cuenta.username,
                rol=cuenta.role,
                endpoint=chequeo.ruta,
                metodo=chequeo.metodo.upper(),
                acceso_esperado=chequeo.acceso_esperado,
                acceso_real=real,
                http_status=status,
                vulnerable=error is None and real != chequeo.acceso_esperado,
                ts=_ts(),
                error=error,
            )
        )
        if progress_callback:
            progress_callback(
                "Pilar 1 · Acceso · "
                f"{chequeo.metodo.upper()} {chequeo.ruta} · "
                f"cuenta {cuenta.username}"
            )
    return resultados


def _normalizar_ruta_matriz(ruta: str) -> str:
    valor = str(ruta or "").strip()
    valor = re.sub(r"<(?:[^:<>]+:)?[^<>]+>", "{id}", valor)
    valor = re.sub(r"\{[^{}]+\}", "{id}", valor)
    valor = re.sub(
        r":(?:id|[A-Za-z_][A-Za-z0-9_]*_id)(?=/|$)",
        "{id}",
        valor,
        flags=re.I,
    )
    return valor


def _ruta_ejecutable_matriz(
    cfg: ConfigObjetivo,
    metodo: str,
    ruta: str,
) -> tuple[str | None, str]:
    """Materializa rutas parametrizadas solo con evidencia ya disponible."""
    original = str(ruta or "").strip()
    if not original:
        return None, "ruta vacía"

    normalizada = _normalizar_ruta_matriz(original)
    if "{id}" not in normalizada:
        return original, "ruta literal"

    for endpoint in cfg.endpoints:
        if endpoint.metodo.upper() != metodo.upper():
            continue
        if _normalizar_ruta_matriz(endpoint.ruta) != normalizada:
            continue
        return (
            normalizada.format(id=endpoint.id_prueba),
            (
                "ruta parametrizada materializada con id de control BOLA "
                f"{endpoint.id_control or 'P1-BOLA'}"
            ),
        )

    # Si el inventario contiene también una variante literal de la misma ruta,
    # se utilizará en su propia fila. No inventamos IDs para esta variante.
    return None, "ruta parametrizada sin identificador de prueba verificable"


def _clasificar_status_matriz(status: int) -> tuple[bool | None, str]:
    if 200 <= status < 300:
        return True, "ACCESO"
    if status in {401, 403}:
        return False, "DENEGADO"
    if status in {400, 404, 405, 409, 415, 422}:
        return None, "NO_CONCLUYENTE"
    if 500 <= status:
        return None, "ERROR_SERVIDOR"
    return None, "OBSERVADO"


def _roles_normalizados(cfg: ConfigObjetivo) -> set[str]:
    return {
        str(role or "").strip().lower()
        for role in cfg.roles_privilegiados
        if str(role or "").strip()
    }


def _politica_esperada_matriz(
    cfg: ConfigObjetivo,
    cuenta: Cuenta,
    metodo: str,
    ruta: str,
) -> tuple[
    bool | None,
    str | None,
    str | None,
    str | None,
]:
    """Deriva expectativa de acceso sin inventarla.

    Prioridad:
    1) control RBAC/ABAC explícito para la cuenta;
    2) política BOLA ya resuelta;
    3) consenso de un control explícito para el mismo rol;
    4) candidato RBAC + rol claramente no privilegiado (confianza media).
    """
    method = metodo.upper()
    normalized = _normalizar_ruta_matriz(ruta)

    # 1. Control exacto por cuenta.
    for check in cfg.chequeos_acceso:
        if check.metodo.upper() != method:
            continue
        if _normalizar_ruta_matriz(check.ruta) != normalized:
            continue
        if check.cuenta != cuenta.username:
            continue
        return (
            bool(check.acceso_esperado),
            "control_acceso",
            "alta",
            check.id_control,
        )

    # 2. Política BOLA por propiedad/rol.
    privileged_roles = _roles_normalizados(cfg)
    for endpoint in cfg.endpoints:
        if endpoint.metodo.upper() != method:
            continue
        if _normalizar_ruta_matriz(endpoint.ruta) != normalized:
            continue
        expected = (
            cuenta.username == endpoint.propietario_esperado
            or cuenta.role.strip().lower() in privileged_roles
        )
        return (
            expected,
            "control_bola",
            "alta",
            endpoint.id_control or "P1-BOLA",
        )

    # 3. Si existe un control explícito para otra cuenta del mismo rol,
    # reutilizamos la política solo cuando todos los controles de ese rol
    # coinciden.
    role_expectations: list[tuple[bool, str]] = []
    for check in cfg.chequeos_acceso:
        if check.metodo.upper() != method:
            continue
        if _normalizar_ruta_matriz(check.ruta) != normalized:
            continue
        other = cfg.cuenta_por_username(check.cuenta)
        if other is None:
            continue
        if other.role.strip().lower() != cuenta.role.strip().lower():
            continue
        role_expectations.append(
            (bool(check.acceso_esperado), check.id_control)
        )

    if role_expectations:
        values = {item[0] for item in role_expectations}
        if len(values) == 1:
            expected = next(iter(values))
            refs = ",".join(
                sorted({item[1] for item in role_expectations})
            )
            return (
                expected,
                "politica_mismo_rol",
                "alta",
                refs,
            )

    # 4. Candidato RBAC: solo inferimos que una cuenta NO privilegiada debe
    # ser rechazada. No asumimos automáticamente que todo privilegiado deba
    # entrar, porque puede haber políticas más finas.
    if (
        cuenta.role.strip().lower() not in privileged_roles
        and privileged_roles
    ):
        for candidate in cfg.candidatos_pilar1:
            if str(candidate.get("familia") or "").upper() != "RBAC_ABAC":
                continue
            candidate_method = str(
                candidate.get("metodo") or ""
            ).upper()
            candidate_route = str(
                candidate.get("ruta_detectada") or ""
            )
            if candidate_method != method:
                continue
            if _normalizar_ruta_matriz(candidate_route) != normalized:
                continue
            return (
                False,
                "candidato_rbac",
                "media",
                None,
            )

    return None, None, None, None


def _cuerpo_matriz(
    cfg: ConfigObjetivo,
    cuenta: Cuenta,
    metodo: str,
    ruta: str,
) -> dict | None:
    if metodo.upper() not in {"POST", "PUT", "PATCH"}:
        return None

    normalized = _normalizar_ruta_matriz(ruta)

    # Reutilizamos únicamente cuerpos ya declarados como pruebas de seguridad.
    for check in cfg.chequeos_acceso:
        if check.cuenta != cuenta.username:
            continue
        if check.metodo.upper() != metodo.upper():
            continue
        if _normalizar_ruta_matriz(check.ruta) != normalized:
            continue
        if isinstance(check.cuerpo, dict):
            return dict(check.cuerpo)

    for endpoint in cfg.endpoints:
        if endpoint.metodo.upper() != metodo.upper():
            continue
        if _normalizar_ruta_matriz(endpoint.ruta) != normalized:
            continue
        if isinstance(endpoint.cuerpo_prueba, dict):
            return dict(endpoint.cuerpo_prueba)

    # Para el barrido general no fabricamos datos de negocio. Una mutación
    # sin cuerpo validado queda pendiente/no ejecutable en vez de dispararse.
    return None


def _response_shape(value: Any, depth: int = 0) -> dict[str, Any]:
    """Describe estructura sin persistir valores de negocio o secretos."""
    if depth >= 4:
        return {"tipo": type(value).__name__}
    if isinstance(value, dict):
        keys = sorted(str(key) for key in value.keys())[:80]
        return {
            "tipo": "object",
            "keys": keys,
            "campos": {
                str(key): _response_shape(nested, depth + 1)
                for key, nested in list(value.items())[:40]
            },
        }
    if isinstance(value, list):
        sample = value[0] if value else None
        return {
            "tipo": "array",
            "cantidad": len(value),
            "item": (
                _response_shape(sample, depth + 1)
                if sample is not None
                else None
            ),
        }
    if value is None:
        return {"tipo": "null"}
    if isinstance(value, bool):
        return {"tipo": "boolean"}
    if isinstance(value, (int, float)):
        return {"tipo": "number"}
    return {"tipo": "string"}


def _object_ids_from_payload(value: Any, limit: int = 30) -> list[str]:
    ids: list[str] = []

    def walk(current: Any) -> None:
        if len(ids) >= limit:
            return
        if isinstance(current, dict):
            for key, nested in current.items():
                normalized = re.sub(
                    r"[^a-z0-9]+",
                    "_",
                    str(key).lower(),
                ).strip("_")
                is_id = (
                    normalized in {
                        "id", "uuid", "pk", "key", "code", "codigo",
                        "object_id", "resource_id", "record_id",
                    }
                    or normalized.endswith("_id")
                    or normalized.endswith("_uuid")
                )
                if (
                    is_id
                    and isinstance(nested, (str, int))
                    and not isinstance(nested, bool)
                ):
                    text = str(nested)
                    if text not in ids:
                        ids.append(text)
                        if len(ids) >= limit:
                            return
                if isinstance(nested, (dict, list)):
                    walk(nested)
        elif isinstance(current, list):
            for nested in current:
                walk(nested)
                if len(ids) >= limit:
                    return

    walk(value)
    return ids


def _object_count_from_payload(value: Any) -> int | None:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        lists = [
            nested
            for nested in value.values()
            if isinstance(nested, list)
        ]
        if lists:
            return max(len(nested) for nested in lists)
        return 1
    return None


def _observe_response(resp: Any) -> tuple[
    str | None,
    dict[str, Any] | None,
    int | None,
    list[str],
]:
    try:
        payload = resp.json()
    except Exception:
        return None, None, None, []

    shape = _response_shape(payload)
    object_ids = _object_ids_from_payload(payload)
    object_count = _object_count_from_payload(payload)
    canonical = json.dumps(
        {
            "shape": shape,
            "object_count": object_count,
            "object_ids": object_ids,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    signature = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()[:20]
    return signature, shape, object_count, object_ids


def _annotate_matrix_response_differences(
    results: list[ResultadoMatrizAcceso],
) -> None:
    grouped: dict[tuple[str, str], list[ResultadoMatrizAcceso]] = {}
    for item in results:
        if not item.response_signature:
            continue
        grouped.setdefault(
            (item.metodo.upper(), _normalizar_ruta_matriz(item.endpoint_detectado)),
            [],
        ).append(item)

    for items in grouped.values():
        signatures = {
            item.response_signature
            for item in items
            if item.response_signature
        }
        if len(signatures) <= 1:
            continue

        counts = sorted({
            item.object_count
            for item in items
            if item.object_count is not None
        })
        message = (
            "La forma/alcance de la respuesta cambia entre identidades"
            + (f" (conteos observados: {counts})" if counts else "")
            + ". La diferencia es evidencia contextual, no una "
            "vulnerabilidad por sí sola."
        )
        for item in items:
            item.response_comparison = message
            if message not in item.detalle:
                item.detalle += " · " + message


def auditar_matriz_acceso(
    cfg: ConfigObjetivo,
    progress_callback: Callable[[str], None] | None = None,
) -> list[ResultadoMatrizAcceso]:
    """Prueba cada endpoint detectado con cada cuenta configurada.

    La matriz es observacional: no inventa una política de acceso. GET/HEAD/
    OPTIONS se ejecutan normalmente. POST/PUT/PATCH solo se ejecutan cuando
    existe un cuerpo de prueba previamente derivado de evidencia; si no, se
    marcan NO_EJECUTABLE. DELETE no se dispara salvo una estrategia aislada
    fuera de esta matriz. Las respuestas JSON se comparan por estructura,
    cantidad e identificadores sin convertir una diferencia en vulnerabilidad
    por sí sola.
    """
    resultados: list[ResultadoMatrizAcceso] = []
    if not cfg.probar_todos_endpoints_con_todos_usuarios:
        return resultados
    if not cfg.endpoints_detectados or not cfg.cuentas:
        return resultados

    vistos: set[tuple[str, str]] = set()
    inventario: list[dict[str, Any]] = []
    for item in cfg.endpoints_detectados:
        metodo = str(item.get("metodo") or "GET").upper().strip()
        ruta = str(item.get("ruta") or "").strip()
        if not ruta:
            continue
        key = (metodo, ruta)
        if key in vistos:
            continue
        vistos.add(key)
        inventario.append(item)

    for item in inventario:
        metodo = str(item.get("metodo") or "GET").upper().strip()
        ruta = str(item.get("ruta") or "").strip()
        ejecutable, razon_ruta = _ruta_ejecutable_matriz(
            cfg,
            metodo,
            ruta,
        )

        for cuenta in cfg.cuentas:
            if ejecutable is None:
                resultados.append(
                    ResultadoMatrizAcceso(
                        sistema=cfg.sistema,
                        cuenta=cuenta.username,
                        rol=cuenta.role,
                        endpoint_detectado=ruta,
                        endpoint_ejecutado=None,
                        metodo=metodo,
                        http_status=None,
                        acceso_real=None,
                        acceso_esperado=None,
                        vulnerable=None,
                        clasificacion="NO_EJECUTABLE",
                        fuente_politica=None,
                        confianza=None,
                        id_control_referencia=None,
                        detalle=razon_ruta,
                        ts=_ts(),
                    )
                )
            elif metodo == "DELETE":
                resultados.append(
                    ResultadoMatrizAcceso(
                        sistema=cfg.sistema,
                        cuenta=cuenta.username,
                        rol=cuenta.role,
                        endpoint_detectado=ruta,
                        endpoint_ejecutado=ejecutable,
                        metodo=metodo,
                        http_status=None,
                        acceso_real=None,
                        acceso_esperado=None,
                        vulnerable=None,
                        clasificacion="NO_EJECUTABLE",
                        fuente_politica=None,
                        confianza=None,
                        id_control_referencia=None,
                        detalle=(
                            "DELETE omitido en matriz automática para evitar "
                            "eliminar datos del objetivo"
                        ),
                        ts=_ts(),
                    )
                )
            else:
                cuerpo = _cuerpo_matriz(
                    cfg,
                    cuenta,
                    metodo,
                    ruta,
                )
                if metodo in {"POST", "PUT", "PATCH"} and cuerpo is None:
                    resultados.append(
                        ResultadoMatrizAcceso(
                            sistema=cfg.sistema,
                            cuenta=cuenta.username,
                            rol=cuenta.role,
                            endpoint_detectado=ruta,
                            endpoint_ejecutado=ejecutable,
                            metodo=metodo,
                            http_status=None,
                            acceso_real=None,
                            acceso_esperado=None,
                            vulnerable=None,
                            clasificacion="NO_EJECUTABLE",
                            fuente_politica=None,
                            confianza=None,
                            id_control_referencia=None,
                            detalle=(
                                "Mutación omitida: no existe payload de prueba "
                                "seguro derivado de evidencia"
                            ),
                            ts=_ts(),
                        )
                    )
                    if progress_callback:
                        progress_callback(
                            "Pilar 1 · Matriz de acceso · "
                            f"{metodo} {ruta} · cuenta {cuenta.username}"
                        )
                    continue

                (
                    acceso_esperado,
                    fuente_politica,
                    confianza,
                    id_control_referencia,
                ) = _politica_esperada_matriz(
                    cfg,
                    cuenta,
                    metodo,
                    ruta,
                )
                response_signature = None
                response_shape = None
                object_count = None
                object_ids: list[str] = []
                try:
                    resp = request_http(
                        metodo,
                        cfg.base_url + ejecutable,
                        cuenta=cuenta,
                        base_url=cfg.base_url,
                        cuerpo=cuerpo,
                    )
                    (
                        response_signature,
                        response_shape,
                        object_count,
                        object_ids,
                    ) = _observe_response(resp)
                    acceso_real, clasificacion_base = (
                        _clasificar_status_matriz(resp.status_code)
                    )
                    vulnerable = (
                        acceso_real != acceso_esperado
                        if (
                            acceso_real is not None
                            and acceso_esperado is not None
                        )
                        else None
                    )

                    if vulnerable is True:
                        clasificacion = (
                            "HALLAZGO_CONFIRMADO"
                            if confianza == "alta"
                            else "POSIBLE_HALLAZGO"
                        )
                    elif vulnerable is False:
                        clasificacion = "CUMPLE"
                    else:
                        clasificacion = clasificacion_base

                    detalle = (
                        f"HTTP {resp.status_code} · {razon_ruta}"
                    )
                    if acceso_esperado is not None:
                        detalle += (
                            f" · esperado={acceso_esperado}"
                            f" real={acceso_real}"
                            f" · política={fuente_politica}"
                            f" · confianza={confianza}"
                        )
                except Exception as exc:
                    resp = None
                    acceso_real = None
                    vulnerable = None
                    clasificacion = "ERROR"
                    detalle = f"{type(exc).__name__}: {exc}"

                resultados.append(
                    ResultadoMatrizAcceso(
                        sistema=cfg.sistema,
                        cuenta=cuenta.username,
                        rol=cuenta.role,
                        endpoint_detectado=ruta,
                        endpoint_ejecutado=ejecutable,
                        metodo=metodo,
                        http_status=(
                            resp.status_code if resp is not None else None
                        ),
                        acceso_real=acceso_real,
                        acceso_esperado=acceso_esperado,
                        vulnerable=vulnerable,
                        clasificacion=clasificacion,
                        fuente_politica=fuente_politica,
                        confianza=confianza,
                        id_control_referencia=id_control_referencia,
                        detalle=detalle,
                        ts=_ts(),
                        response_signature=response_signature,
                        response_shape=response_shape,
                        object_count=object_count,
                        object_ids=object_ids,
                    )
                )

            if progress_callback:
                progress_callback(
                    "Pilar 1 · Matriz de acceso · "
                    f"{metodo} {ruta} · cuenta {cuenta.username}"
                )

    _annotate_matrix_response_differences(resultados)
    return resultados


def auditar_alcance_agente(
    cfg: ConfigObjetivo,
    progress_callback: Callable[[str], None] | None = None,
) -> list[HallazgoAgente]:
    resultados: list[HallazgoAgente] = []
    for chequeo in cfg.chequeos_agente:
        cuenta = cfg.cuenta_por_username(chequeo.cuenta)
        if cuenta is None:
            raise ValueError(
                f"chequeo '{chequeo.nombre}': cuenta '{chequeo.cuenta}' no configurada"
            )

        resp_directa = request_http(
            chequeo.direct_metodo,
            cfg.base_url + chequeo.direct_ruta,
            cuenta=cuenta,
            base_url=cfg.base_url,
        )
        resp_agente = request_http(
            "POST",
            cfg.base_url + chequeo.agent_ruta,
            cuenta=cuenta,
            base_url=cfg.base_url,
            cuerpo=chequeo.agent_cuerpo,
            timeout=15,
        )

        resp_directa.raise_for_status()
        resp_agente.raise_for_status()

        resultado = evaluar_alcance_agente(
            resp_directa.json(),
            resp_agente.json(),
            direct_json_path=chequeo.direct_json_path,
            steps_json_path=chequeo.steps_json_path,
            tool_name=chequeo.tool_name,
            tool_field=chequeo.tool_field,
            count_field=chequeo.count_field,
            id_field=chequeo.id_field,
            agent_items_json_path=chequeo.agent_items_json_path,
        )
        resultados.append(
            HallazgoAgente(
                sistema=cfg.sistema,
                id_control=chequeo.id_control,
                nombre_chequeo=chequeo.nombre,
                cuenta=cuenta.username,
                resultado=resultado,
                ts=_ts(),
            )
        )
        if progress_callback:
            progress_callback(
                "Pilar 1 · Alcance del agente · "
                f"{chequeo.nombre} · cuenta {cuenta.username}"
            )
    return resultados
