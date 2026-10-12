"""Comprueba que los errores salen como {"detail": "texto en español"}."""
from typing import Literal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.errores import registrar_manejadores

# Mini-API solo para la prueba; no toca la base de datos
app_prueba = FastAPI()
registrar_manejadores(app_prueba)


class Pedido(BaseModel):
    n_grafos: int = Field(ge=1, le=5)
    op_cruce: Literal["OX", "PMX"] = "OX"


@app_prueba.post("/eco")
def eco(pedido: Pedido):
    return pedido


cliente = TestClient(app_prueba)


def test_404_en_espanol():
    r = cliente.get("/no-existe")
    assert r.status_code == 404
    assert r.json() == {"detail": "Esa dirección no existe en la API."}


def test_422_fuera_de_rango():
    r = cliente.post("/eco", json={"n_grafos": 9})
    assert r.status_code == 422
    assert r.json() == {"detail": "«n_grafos» debe ser menor o igual que 5."}


def test_422_campo_vacio():
    # Así llega cuando la persona borra un número en el formulario
    r = cliente.post("/eco", json={"n_grafos": ""})
    assert r.status_code == 422
    assert r.json() == {"detail": "«n_grafos» debe ser un número entero."}


def test_422_falta_campo():
    r = cliente.post("/eco", json={})
    assert r.json() == {"detail": "Falta el campo «n_grafos»."}


def test_422_operador_invalido():
    r = cliente.post("/eco", json={"n_grafos": 3, "op_cruce": "XYZ"})
    assert r.status_code == 422
    assert r.json()["detail"].startswith("«op_cruce» debe ser uno de estos valores:")