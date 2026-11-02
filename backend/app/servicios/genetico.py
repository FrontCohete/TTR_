"""Algoritmo genético de cada agente (etapa 5): el orden de visita de los hotspots de un grafo.

Traducción de `frontend/src/mocks/genetico.js` con las decisiones de DECISIONES_ETAPA5_GENETICO.md:
  * individuo = permutación de los hotspots; aptitud = distancia total del circuito con la matriz D
    (desde la versión solo-calles: metros por calles con sentido, D[i][j] ≠ D[j][i]), con regreso al
    inicio si `ruta_cerrada`; menos es mejor;
  * generación 0: P permutaciones al azar;
  * para cada hijo h = 0 … P − 1 − n_elite: dos torneos de K participantes con reemplazo
    (torneos[2h] da el padre A, torneos[2h+1] el B) → cruce OX (o PMX) con probabilidad
    `prob_cruce` y cortes [c1, c2) → mutación con probabilidad `prob_mutacion`:
      inversion (voltea un tramo) · insercion (saca un hotspot y lo mete más adelante, sin voltear)
      · mixta (inversión si a + b es par, inserción si es impar; por defecto) · swap (intercambio);
  * élite: las `n_elite` mejores rutas de la generación anterior pasan intactas a las ÚLTIMAS
    posiciones (origen "elite", padre_1 = su posición anterior, padre_2 = None);
  * resultado: la mejor ruta HISTÓRICA (`generacion_mejor` = la primera vez que apareció);
  * reproducible: numpy.random.default_rng(semilla).

Pulido final (`pulir`, versión solo-calles, 1 nov 2026): búsqueda local or-opt CON SENTIDO sobre la
mejor ruta: mueve 1, 2 o 3 hotspots seguidos a otra posición sin voltearlos mientras la ruta se
acorte. Se aplica fuera de `ejecutar_ag` (agentes.py), así que no altera la evolución registrada.
Mixta + pulido salió de experimento_mutacion.py y experimento_grandes.py (PLAN_SOLO_CALLES.md).

No toca la base ni FastAPI. Para no gastar memoria, cada generación se guarda en arreglos de NumPy
(índices 0 … n − 1); los diccionarios del contrato de la vista Rutas se arman solo al pedirlos.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, fields

import numpy as np

LIMITE_POBLACION_X_GENERACIONES = 100_000
ORIGENES = ("aleatorio", "cruce", "mutacion", "elite")      # códigos 0, 1, 2, 3
ALEATORIO, CRUCE, MUTACION, ELITE = range(4)
MUTACIONES = ("mixta", "inversion", "insercion", "swap")


class ParametrosInvalidos(ValueError):
    """Algún parámetro está fuera de rango. La ruta responde 422 con este mensaje."""


@dataclass(frozen=True)
class Parametros:
    tam_poblacion: int = 100
    n_generaciones: int = 1000
    tam_torneo: int = 5
    prob_cruce: float = 0.9
    prob_mutacion: float = 0.5
    op_cruce: str = "OX"
    op_mutacion: str = "mixta"
    semilla: int = 42
    ruta_cerrada: bool = True
    n_elite: int = 1

    @classmethod
    def desde(cls, datos: dict) -> "Parametros":
        """Toma solo las claves conocidas (el frontend puede mandar de más)."""
        nombres = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in datos.items() if k in nombres})

    def validar(self) -> None:
        reglas = [
            (2 <= self.tam_poblacion <= 500, "La población debe tener entre 2 y 500 rutas."),
            (1 <= self.n_generaciones <= 2000, "Las generaciones deben estar entre 1 y 2,000."),
            (self.tam_poblacion * self.n_generaciones <= LIMITE_POBLACION_X_GENERACIONES,
             f"La población por el número de generaciones no puede pasar de {LIMITE_POBLACION_X_GENERACIONES:,} "
             f"(por ejemplo, 100 × 1,000)."),
            (2 <= self.tam_torneo <= self.tam_poblacion,
             "El torneo debe tener entre 2 participantes y el tamaño de la población."),
            (0 <= self.prob_cruce <= 1, "La probabilidad de cruce debe estar entre 0 y 1."),
            (0 <= self.prob_mutacion <= 1, "La probabilidad de mutación debe estar entre 0 y 1."),
            (self.op_cruce in ("OX", "PMX"), "El cruce debe ser OX o PMX."),
            (self.op_mutacion in MUTACIONES, "La mutación debe ser mixta, inversion, insercion o swap."),
            (0 <= self.semilla <= 999_999, "La semilla debe estar entre 0 y 999,999."),
            (0 <= self.n_elite < self.tam_poblacion, "La élite debe ser menor que la población."),
        ]
        for ok, mensaje in reglas:
            if not ok:
                raise ParametrosInvalidos(mensaje)


# ------------------------------------------------------------------ operadores (sobre listas)
def cruce_ox(a: list, b: list, c1: int, c2: int) -> list:
    """Copia a[c1:c2] y llena desde c2, dando la vuelta, con los genes de b leídos desde c2."""
    n = len(a)
    hijo = [None] * n
    hijo[c1:c2] = a[c1:c2]
    usados = set(a[c1:c2])
    resto = [g for g in b[c2:] + b[:c2] if g not in usados]
    for pos, g in zip(list(range(c2, n)) + list(range(c1)), resto):
        hijo[pos] = g
    return hijo


def cruce_pmx(a: list, b: list, c1: int, c2: int) -> list:
    """Cruce parcialmente mapeado, igual que crucePMX de genetico.js."""
    n = len(a)
    hijo = [None] * n
    hijo[c1:c2] = a[c1:c2]
    en_segmento = set(a[c1:c2])
    pos_en_b = {g: i for i, g in enumerate(b)}
    for i in range(c1, c2):
        g = b[i]
        if g in en_segmento:
            continue
        pos = i
        while c1 <= pos < c2:
            pos = pos_en_b[a[pos]]
        hijo[pos] = g
    return [b[i] if h is None else h for i, h in enumerate(hijo)]


def invertir(p: list, a: int, b: int) -> list:
    """Invierte el tramo de la posición a a la b (ambas incluidas)."""
    return p[:a] + p[a:b + 1][::-1] + p[b + 1:]


def intercambiar(p: list, a: int, b: int) -> list:
    q = list(p)
    q[a], q[b] = q[b], q[a]
    return q


def insertar(p: list, a: int, b: int) -> list:
    """Saca el hotspot de la posición a y lo mete en la posición b (a < b). No voltea ningún tramo."""
    q = list(p)
    q.insert(b, q.pop(a))
    return q


def tipo_mixta(a: int, b: int) -> str:
    """Qué hace la mutación mixta con las posiciones a y b: inversión si a + b es par, si no inserción."""
    return "inversion" if (a + b) % 2 == 0 else "insercion"


def mixta(p: list, a: int, b: int) -> list:
    return invertir(p, a, b) if tipo_mixta(a, b) == "inversion" else insertar(p, a, b)


OPERADOR_MUTACION = {"inversion": invertir, "insercion": insertar, "mixta": mixta, "swap": intercambiar}


def distancias(pob: np.ndarray, D: np.ndarray, cerrada: bool) -> np.ndarray:
    """Aptitud de toda la población (P × n índices) de una vez."""
    if pob.shape[1] < 2:
        return np.zeros(pob.shape[0])
    d = D[pob[:, :-1], pob[:, 1:]].sum(axis=1)
    if cerrada:
        d = d + D[pob[:, -1], pob[:, 0]]
    return d


# ------------------------------------------------------------------ registro
@dataclass
class Generacion:
    """Una generación guardada en arreglos (índices de nodo, no ids de la base)."""
    numero: int
    poblacion: np.ndarray            # (P, n) int32
    distancia: np.ndarray            # (P,) float64
    origen: np.ndarray               # (P,) int8, códigos de ORIGENES
    padres: np.ndarray               # (P, 2) int32, −1 = sin padre
    participantes: np.ndarray | None = None   # (2H, K) posiciones de la generación anterior
    ganadores: np.ndarray | None = None       # (2H,)
    cortes: np.ndarray | None = None          # (H, 2); −1 si no hubo cruce
    mutaciones: list = field(default_factory=list)   # [(hijo, a, b)]

    @property
    def mejor(self) -> int:
        return int(np.argmin(self.distancia))       # la primera en caso de empate, como genetico.js


@dataclass
class Resultado:
    ids: list[int]
    parametros: Parametros
    generaciones: list[Generacion] | None     # None si se corrió con registro=False
    resumen: list[dict]                       # numero, mejor, promedio, peor, mejor_permutacion
    mejor_distancia: float
    ruta_optima: list[int]                    # ids, en el orden que encontró el algoritmo
    generacion_mejor: int
    duracion_s: float

    def _ids(self, fila) -> list[int]:
        return [self.ids[i] for i in fila]

    def individuos(self, numero: int) -> list[dict]:
        """Las P rutas de una generación con el formato del contrato (README_PRUEBASGEN §3.3)."""
        g = self.generaciones[numero]
        return [{
            "posicion": i,
            "permutacion": self._ids(g.poblacion[i]),
            "distancia": round(float(g.distancia[i]), 1),
            "origen": ORIGENES[g.origen[i]],
            "padre_1": None if g.padres[i, 0] < 0 else int(g.padres[i, 0]),
            "padre_2": None if g.padres[i, 1] < 0 else int(g.padres[i, 1]),
        } for i in range(len(g.distancia))]

    def operaciones(self, numero: int) -> dict | None:
        """El registro de operaciones de una generación; None en la generación 0 (no {})."""
        g = self.generaciones[numero]
        if g.participantes is None:
            return None
        torneos = [{"participantes": [int(x) for x in g.participantes[t]], "ganador": int(g.ganadores[t]), "hijo": t // 2}
                   for t in range(len(g.ganadores))]
        cruces = []
        for h, (c1, c2) in enumerate(g.cortes):
            aplicado = bool(c1 >= 0)
            cruces.append({"padres": [int(g.ganadores[2 * h]), int(g.ganadores[2 * h + 1])],
                           "puntos_corte": [int(c1), int(c2)] if aplicado else None,
                           "hijo": h, "aplicado": aplicado})
        op = self.parametros.op_mutacion
        tipo = (lambda a, b: tipo_mixta(a, b)) if op == "mixta" else (lambda a, b: op)
        return {
            "seleccion_azar": [int(x) for x in g.participantes.ravel()],
            "torneos": torneos,
            "cruces": cruces,
            "mutaciones": [{"individuo": h, "posiciones": [a, b], "tipo": tipo(a, b)} for h, a, b in g.mutaciones],
        }


# ------------------------------------------------------------------ el algoritmo
def ejecutar_ag(ids: list[int], D: np.ndarray, parametros: Parametros | None = None, *,
                registro: bool = True, al_avanzar=None) -> Resultado:
    """Corre el genético sobre un grafo.

    ids: los id_hotspot del grafo (filas/columnas de D, en ese orden).
    D: matriz n × n de distancias en metros (simétrica, diagonal 0).
    al_avanzar(fraccion): se llama de vez en cuando con un número de 0 a 1 (para la barra de avance).
    """
    p = parametros or Parametros()
    p.validar()
    D = np.asarray(D, dtype=float)
    n = len(ids)
    if D.shape != (n, n):
        raise ValueError(f"La matriz de distancias debe ser {n} × {n}.")
    P, G, K, E = p.tam_poblacion, p.n_generaciones, p.tam_torneo, p.n_elite
    H = P - E                                            # hijos que pasan por torneo y cruce
    rng = np.random.default_rng(p.semilla)
    cruzar = cruce_pmx if p.op_cruce == "PMX" else cruce_ox
    mutar = OPERADOR_MUTACION[p.op_mutacion]
    t0 = time.perf_counter()

    pob = np.argsort(rng.random((P, n)), axis=1).astype(np.int32) if n > 1 else np.zeros((P, n), np.int32)
    dist = distancias(pob, D, p.ruta_cerrada)
    gen0 = Generacion(0, pob, dist, np.full(P, ALEATORIO, np.int8), np.full((P, 2), -1, np.int32))
    generaciones = [gen0] if registro else None
    resumen = [_resumen(gen0)]
    mejor = (float(dist.min()), pob[int(np.argmin(dist))].copy(), 0)

    for numero in range(1, G + 1):
        # selección al azar + torneo: dos por hijo
        part = rng.integers(P, size=(2 * H, K)).astype(np.int32)
        gan = part[np.arange(2 * H), np.argmin(dist[part], axis=1)]
        sorteo = rng.random((H, 2))                       # [cruce?, mutación?]
        # cortes y posiciones de mutación sorteados de una vez (sacarlos uno por uno es lo lento)
        cortes_azar = _cortes_de_la_generacion(n, H, rng) if n > 2 else None
        if n > 1:
            mx = rng.integers(n, size=H)
            my = rng.integers(n - 1, size=H)
            my = my + (my >= mx)                          # dos posiciones distintas, uniformes
            mut_a, mut_b = np.minimum(mx, my).tolist(), np.maximum(mx, my).tolist()
        cortes = np.full((H, 2), -1, np.int32)
        nueva = np.empty((P, n), np.int32)
        origen = np.empty(P, np.int8)
        padres = np.full((P, 2), -1, np.int32)
        mutaciones = []
        filas = pob.tolist()
        for h in range(H):
            a, b = filas[gan[2 * h]], filas[gan[2 * h + 1]]
            if n > 2 and sorteo[h, 0] < p.prob_cruce:
                c1, c2 = cortes_azar[h]
                hijo = cruzar(a, b, c1, c2)
                cortes[h] = (c1, c2)
            else:
                hijo = list(a)
            origen[h] = CRUCE
            if n > 1 and sorteo[h, 1] < p.prob_mutacion:
                x, y = mut_a[h], mut_b[h]
                hijo = mutar(hijo, x, y)
                mutaciones.append((h, x, y))
                origen[h] = MUTACION
            nueva[h] = hijo
            padres[h] = (gan[2 * h], gan[2 * h + 1])
        if E:                                             # élite al final, sin tocar
            orden = np.argsort(dist, kind="stable")[:E]
            nueva[H:] = pob[orden]
            origen[H:] = ELITE
            padres[H:, 0] = orden
        nueva_dist = distancias(nueva, D, p.ruta_cerrada)
        if E:
            nueva_dist[H:] = dist[orden]                  # idéntica, sin redondeos nuevos
        pob, dist = nueva, nueva_dist
        g = Generacion(numero, pob, dist, origen, padres, part, gan, cortes, mutaciones)
        if registro:
            generaciones.append(g)
        resumen.append(_resumen(g))
        if dist.min() < mejor[0]:
            mejor = (float(dist.min()), pob[int(np.argmin(dist))].copy(), numero)
        if al_avanzar and (numero % 50 == 0 or numero == G):
            al_avanzar(numero / G)

    return Resultado(
        ids=list(ids), parametros=p, generaciones=generaciones,
        resumen=[{**r, "mejor_permutacion": [ids[i] for i in r["mejor_permutacion"]]} for r in resumen],
        mejor_distancia=round(mejor[0], 1), ruta_optima=[ids[i] for i in mejor[1]],
        generacion_mejor=mejor[2], duracion_s=round(time.perf_counter() - t0, 3),
    )


def _puntos_de_corte(n: int, rng) -> tuple[int, int]:
    """Dos cortes [c1, c2) con un segmento de 1 a n − 1 genes (igual que genetico.js)."""
    while True:
        c1, c2 = rng.integers(n + 1, size=2).tolist()
        if c1 == c2:
            continue
        if c1 > c2:
            c1, c2 = c2, c1
        if c1 == 0 and c2 == n:
            continue
        return c1, c2


def _cortes_de_la_generacion(n: int, H: int, rng) -> list[tuple[int, int]]:
    """H pares de cortes válidos a la vez: se vuelven a sortear solo los que no sirven."""
    c = rng.integers(n + 1, size=(H, 2))
    while True:
        malos = (c[:, 0] == c[:, 1]) | ((np.minimum(c[:, 0], c[:, 1]) == 0) & (np.maximum(c[:, 0], c[:, 1]) == n))
        if not malos.any():
            break
        c[malos] = rng.integers(n + 1, size=(int(malos.sum()), 2))
    c.sort(axis=1)
    return [tuple(x) for x in c.tolist()]


def _resumen(g: Generacion) -> dict:
    m = g.mejor
    return {"numero": g.numero, "mejor_fitness": round(float(g.distancia[m]), 1),
            "fitness_promedio": round(float(g.distancia.mean()), 1),
            "peor_fitness": round(float(g.distancia.max()), 1),
            "mejor_permutacion": g.poblacion[m].tolist()}


# ------------------------------------------------------------------ presentación de la ruta
def presentar_ruta(ruta: list[int], prioridad: dict[int, tuple]) -> list[int]:
    """Rota la ruta cerrada para que empiece en el hotspot de mayor prioridad.

    prioridad[id] = tupla comparable; se usa (n_puntos × indice_gravedad, n_puntos, −etiqueta).
    Rotar un circuito no cambia sus tramos ni su distancia.
    """
    if len(ruta) < 2:
        return list(ruta)
    inicio = max(ruta, key=lambda h: prioridad.get(h, ()))
    i = ruta.index(inicio)
    return list(ruta[i:]) + list(ruta[:i])


def prioridad_hotspots(hotspots: list[dict]) -> dict[int, tuple]:
    """A partir de filas con id_hotspot, n_puntos, indice_gravedad y etiqueta."""
    return {int(h["id_hotspot"]): (float(h["n_puntos"]) * float(h["indice_gravedad"] or 0), int(h["n_puntos"]),
                                   -int(h["etiqueta"]))
            for h in hotspots}


# ------------------------------------------------------------------ pulido final (or-opt con sentido)
def largo(orden: list[int], D, cerrada: bool = True) -> float:
    """Metros de recorrer `orden` (índices de D) respetando la dirección de cada tramo."""
    d = sum(float(D[a][b]) for a, b in zip(orden, orden[1:]))
    if cerrada and len(orden) > 1:
        d += float(D[orden[-1]][orden[0]])
    return d


def _or_opt(t: list[int], D: list[list[float]], movimientos: list, max_pasadas: int, fijo: int | None = None) -> list[int]:
    """Circuito cerrado. Para cada segmento de 1–3 hotspots, el mejor lugar donde reinsertarlo sin voltearlo.

    `fijo`: un nodo que nunca se mueve (el ficticio que cierra una ruta abierta).
    """
    t = list(t)
    n = len(t)
    for _ in range(max_pasadas):
        mejoro = False
        for L in (1, 2, 3):
            if L >= n - 1:
                break
            i = 0
            while i < n:
                seg = [t[(i + k) % n] for k in range(L)]
                if fijo is not None and fijo in seg:
                    i += 1
                    continue
                prev, nxt = t[(i - 1) % n], t[(i + L) % n]
                quita = D[prev][seg[0]] + D[seg[-1]][nxt] - D[prev][nxt]
                resto = [t[(i + L + k) % n] for k in range(n - L)]       # empieza en nxt, termina en prev
                mejor_j, mejor_d = -1, -1e-7
                for j in range(n - L - 1):                               # entre resto[j] y resto[j + 1]
                    u, v = resto[j], resto[j + 1]
                    d = D[u][seg[0]] + D[seg[-1]][v] - D[u][v] - quita
                    if d < mejor_d:
                        mejor_j, mejor_d = j, d
                if mejor_j >= 0:
                    movimientos.append((seg, resto[mejor_j], resto[mejor_j + 1], -mejor_d))
                    t = resto[:mejor_j + 1] + seg + resto[mejor_j + 1:]
                    mejoro = True
                i += 1
        if not mejoro:
            break
    return t


def pulir(orden: list[int], D, cerrada: bool = True, max_pasadas: int = 60) -> tuple[list[int], list[dict]]:
    """Pulido final: or-opt con sentido sobre una ruta (índices de D). Nunca la alarga.

    Devuelve (ruta pulida, movimientos [{segmento, entre: [u, v], ahorro_m}]). En una ruta abierta,
    `None` en `entre` significa «al inicio» o «al final».
    """
    n = len(orden)
    if n < 4:
        return list(orden), []
    Dl = np.asarray(D, dtype=float).tolist()
    crudos: list = []
    if cerrada:
        t = _or_opt(orden, Dl, crudos, max_pasadas)
    else:                                   # ruta abierta: un nodo ficticio a distancia 0 la cierra
        for fila in Dl:
            fila.append(0.0)
        Dl.append([0.0] * (n + 1))
        c = _or_opt(list(orden) + [n], Dl, crudos, max_pasadas, fijo=n)
        k = c.index(n)
        t = c[k + 1:] + c[:k]
    movimientos = [{"segmento": list(seg), "entre": [None if u == n else u, None if v == n else v],
                    "ahorro_m": round(float(ahorro), 1)} for seg, u, v, ahorro in crudos]
    return t, movimientos
