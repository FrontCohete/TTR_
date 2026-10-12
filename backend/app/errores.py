"""Manejo uniforme de errores: siempre {"detail": "texto en español"}.

El frontend muestra el texto de "detail" tal cual a la persona usuaria
(README_INTEGRACION §3), así que nunca debe llegar en inglés ni como lista.
"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Mensajes que FastAPI genera por su cuenta, en inglés
_TRADUCCIONES = {
    "Not Found": "Esa dirección no existe en la API.",
    "Method Not Allowed": "Esa dirección existe, pero no acepta este tipo de petición.",
}

# Partes de la ubicación de un error que no aportan nada a quien lo lee
_SECCIONES = {"body", "query", "path", "header", "cookie"}


def _campo(loc) -> str:
    """('body', 'parametros', 'tam_poblacion') -> 'parametros.tam_poblacion'"""
    partes = [str(p) for p in loc if p not in _SECCIONES]
    return ".".join(partes) or "la petición"


def _mensaje(error: dict) -> str:
    """Traduce un error de validación de Pydantic a una frase en español."""
    campo = _campo(error.get("loc", ()))
    tipo = error.get("type", "")
    ctx = error.get("ctx") or {}

    if tipo == "missing":
        return f"Falta el campo «{campo}»."
    if tipo in ("int_parsing", "int_type", "int_from_float"):
        return f"«{campo}» debe ser un número entero."
    if tipo in ("float_parsing", "float_type"):
        return f"«{campo}» debe ser un número."
    if tipo in ("bool_parsing", "bool_type"):
        return f"«{campo}» debe ser verdadero o falso."
    if tipo == "greater_than_equal":
        return f"«{campo}» debe ser mayor o igual que {ctx.get('ge')}."
    if tipo == "less_than_equal":
        return f"«{campo}» debe ser menor o igual que {ctx.get('le')}."
    if tipo == "greater_than":
        return f"«{campo}» debe ser mayor que {ctx.get('gt')}."
    if tipo == "less_than":
        return f"«{campo}» debe ser menor que {ctx.get('lt')}."
    if tipo == "literal_error":
        opciones = str(ctx.get("expected", "")).replace(" or ", " o ")
        return f"«{campo}» debe ser uno de estos valores: {opciones}."
    if tipo == "json_invalid":
        return "El cuerpo de la petición no es un JSON válido."
    return f"El valor de «{campo}» no es válido."


def registrar_manejadores(app: FastAPI) -> None:
    """Conecta los tres traductores de errores a la API."""

    @app.exception_handler(StarletteHTTPException)
    async def error_http(request: Request, exc: StarletteHTTPException):
        detalle = exc.detail
        if isinstance(detalle, str):
            detalle = _TRADUCCIONES.get(detalle, detalle)
        return JSONResponse(
            {"detail": detalle},
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def error_validacion(request: Request, exc: RequestValidationError):
        mensajes = [_mensaje(e) for e in exc.errors()]
        return JSONResponse(
            {"detail": " ".join(mensajes) or "La petición no es válida."},
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def error_inesperado(request: Request, exc: Exception):
        # El detalle técnico sigue apareciendo en la terminal de uvicorn
        return JSONResponse(
            {"detail": "Ocurrió un error inesperado en el servidor. Revisa la terminal del backend."},
            status_code=500,
        )