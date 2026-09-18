"""Transporte HTTP genérico y autenticación configurable."""

from __future__ import annotations

import requests

from .config import Cuenta


def preparar_autenticacion(
    cuenta: Cuenta | None,
    headers: dict[str, str] | None = None,
):
    finales = dict(headers or {})
    auth = None

    if cuenta is None or cuenta.auth_type == "none":
        return auth, finales

    finales.update(cuenta.headers)

    if cuenta.auth_type == "basic":
        if cuenta.password is None:
            raise ValueError(f"{cuenta.username}: falta password para auth basic")
        auth = (cuenta.username, cuenta.password)
    elif cuenta.auth_type == "bearer":
        if not cuenta.token:
            raise ValueError(f"{cuenta.username}: falta token para auth bearer")
        finales["Authorization"] = f"Bearer {cuenta.token}"
    elif cuenta.auth_type == "header":
        if not cuenta.headers:
            raise ValueError(f"{cuenta.username}: auth header requiere headers")
    else:
        raise ValueError(f"auth_type no soportado: {cuenta.auth_type}")

    return auth, finales


def request_http(
    metodo: str,
    url: str,
    *,
    cuenta: Cuenta | None = None,
    cuerpo: dict | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 10,
) -> requests.Response:
    auth, finales = preparar_autenticacion(cuenta, headers)
    return requests.request(
        metodo.upper(),
        url,
        auth=auth,
        json=cuerpo,
        headers=finales,
        timeout=timeout,
    )
