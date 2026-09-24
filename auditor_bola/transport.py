"""Transporte HTTP genérico y autenticación configurable."""

from __future__ import annotations

import requests
from urllib.parse import urlsplit

from .config import Cuenta


class AuthenticationError(requests.RequestException):
    """No se puede evaluar autorización sin una identidad autenticada."""


def _login(session, cuenta: Cuenta, base_url: str, timeout: int) -> None:
    config = cuenta.login
    route = str(config.get("ruta") or "")
    if not route.startswith("/") or route.startswith("//") or cuenta.password is None:
        raise AuthenticationError(f"{cuenta.username}: configure login.ruta y password")
    login_url = base_url.rstrip("/") + route
    payload = dict(config.get("campos") or {})
    payload[str(config.get("campo_usuario") or "username")] = cuenta.username
    payload[str(config.get("campo_password") or "password")] = cuenta.password
    encoding = config.get("formato", "form")
    if encoding not in {"form", "json"}:
        raise AuthenticationError("login.formato debe ser form o json")
    response = session.post(
        login_url, **{"json" if encoding == "json" else "data": payload},
        timeout=timeout, allow_redirects=False,
    )
    allowed = config.get("codigos_exito", [200, 201, 204, 302, 303])
    if response.status_code not in allowed:
        raise AuthenticationError(f"{cuenta.username}: login rechazado (HTTP {response.status_code})")
    if cuenta.auth_type == "login_bearer":
        try:
            token = response.json()
            for part in str(config.get("token_json_path", "token")).removeprefix("$.").split("."):
                token = token[part]
            if not isinstance(token, str) or not token.strip():
                raise ValueError("token vacío")
        except (ValueError, KeyError, TypeError):
            raise AuthenticationError(f"{cuenta.username}: login no devolvió un token válido") from None
        session.headers["Authorization"] = f"Bearer {token}"
    elif not session.cookies:
        raise AuthenticationError(f"{cuenta.username}: login no creó una sesión")


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
    base_url: str | None = None,
) -> requests.Response:
    if cuenta is not None and cuenta.auth_type in {"session", "login_bearer"}:
        parsed = urlsplit(url)
        auth_base = base_url or f"{parsed.scheme}://{parsed.netloc}"
        auth_origin = urlsplit(auth_base)
        if (parsed.scheme, parsed.netloc) != (auth_origin.scheme, auth_origin.netloc):
            raise AuthenticationError("El login y el recurso deben pertenecer al mismo origen")
        # Una sesión aislada por solicitud evita mezclar cuentas o reutilizar
        # credenciales obsoletas después de un reinicio/corrección del objetivo.
        with requests.Session() as session:
            session.headers.update(cuenta.headers)
            _login(session, cuenta, auth_base, timeout)
            return session.request(
                metodo.upper(), url, json=cuerpo, headers=headers,
                timeout=timeout, allow_redirects=False,
            )
    auth, finales = preparar_autenticacion(cuenta, headers)
    return requests.request(
        metodo.upper(),
        url,
        auth=auth,
        json=cuerpo,
        headers=finales,
        timeout=timeout,
        allow_redirects=False,
    )
