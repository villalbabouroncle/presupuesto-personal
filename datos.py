"""
Lectura, limpieza y escritura de datos del presupuesto.

Fuentes soportadas:
  1. Google Sheets (lectura + escritura) con una cuenta de servicio de Google.
  2. Un archivo .xlsx descargado de la hoja (solo lectura), útil para probar en local.

La estructura esperada es la de tu hoja "Presupuesto Personal":
  - Pestaña "Presupuesto Mensual": conceptos en la columna A, meses desde la columna C.
  - Pestaña "Registro": tres bloques lado a lado (Necesarios A:D, Discrecionales F:I,
    Situacionales K:N), cada uno con Categoría | Detalle | Periodo | Monto.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

HOJA_PRESUPUESTO = "Presupuesto Mensual"
HOJA_REGISTRO = "Registro"

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
NOMBRE_MES = {v: k for k, v in MESES.items() if k != "setiembre"}

# Secciones de la pestaña "Presupuesto Mensual" -> grupo
SECCIONES = {
    "INGRESOS": "Ingresos",
    "GASTOS NECESARIOS": "Necesarios",
    "GASTOS DISCRECIONALES": "Discrecionales",
    "GASTOS SITUACIONALES": "Situacionales",
}
GRUPOS_GASTO = ["Necesarios", "Discrecionales", "Situacionales"]

# Bloques de la pestaña "Registro": grupo -> índice (0-based) de la columna "Categoría"
BLOQUES_REGISTRO = {"Necesarios": 0, "Discrecionales": 5, "Situacionales": 10}


# ---------------------------------------------------------------------------
# Utilidades de limpieza
# ---------------------------------------------------------------------------
def _sin_tildes(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def a_numero(valor) -> float | None:
    """Convierte '1.898,45', '7,67', 100, 22.0 o '' en float (o None si está vacío)."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace("S/", "").replace(" ", "")
    if texto == "" or texto == "-":
        return None
    if "," in texto:  # formato peruano/español: punto de miles, coma decimal
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def a_mes(valor) -> pd.Timestamp | None:
    """Convierte 'junio 2026', 'Enero 2026', una fecha o un número de serie de Sheets
    en el primer día del mes."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, (datetime, date, pd.Timestamp)):
        return pd.Timestamp(valor.year, valor.month, 1)
    if isinstance(valor, (int, float)):
        if 20000 < valor < 80000:  # número de serie de fecha de Google Sheets / Excel
            d = datetime(1899, 12, 30) + timedelta(days=float(valor))
            return pd.Timestamp(d.year, d.month, 1)
        return None
    texto = _sin_tildes(str(valor)).strip().lower()
    m = re.match(r"^([a-z]+)\s*(?:de\s*)?(?:del\s*)?(\d{4})$", texto)
    if m and m.group(1) in MESES:
        return pd.Timestamp(int(m.group(2)), MESES[m.group(1)], 1)
    return None


def texto_periodo(mes: pd.Timestamp) -> str:
    """Formato que usa tu hoja en la columna Periodo: 'octubre 2026'."""
    return f"{NOMBRE_MES[mes.month]} {mes.year}"


def etiqueta_mes(mes: pd.Timestamp, corto: bool = False) -> str:
    nombre = NOMBRE_MES[mes.month].capitalize()
    if corto:
        return f"{nombre[:3]} {str(mes.year)[2:]}"
    return f"{nombre} {mes.year}"


def _celda(fila: list, i: int):
    return fila[i] if i < len(fila) else None


def _texto(valor) -> str:
    return "" if valor is None else str(valor).strip()


# ---------------------------------------------------------------------------
# Parseo de las pestañas
# ---------------------------------------------------------------------------
@dataclass
class Datos:
    presupuesto: pd.DataFrame          # mes, grupo, categoria, monto
    registro: pd.DataFrame             # grupo, categoria, detalle, periodo, mes, monto
    ahorros: list[tuple[str, float]] = field(default_factory=list)
    tarjetas: list[tuple[str, float]] = field(default_factory=list)
    categorias: dict[str, list[str]] = field(default_factory=dict)  # grupo -> categorías
    periodos: list[pd.Timestamp] = field(default_factory=list)      # columnas de meses
    fuente: str = ""
    puede_escribir: bool = False

    # ---- vistas derivadas ----
    @property
    def mensual(self) -> pd.DataFrame:
        """Una fila por mes: ingresos, gastos por grupo, total, saldo, tasa de ahorro."""
        p = self.presupuesto
        tabla = p.pivot_table(index="mes", columns="grupo", values="monto",
                              aggfunc="sum", fill_value=0.0)
        for g in ["Ingresos", *GRUPOS_GASTO]:
            if g not in tabla:
                tabla[g] = 0.0
        tabla = tabla.reindex(self.periodos, fill_value=0.0)
        tabla["Gastos"] = tabla[GRUPOS_GASTO].sum(axis=1)
        tabla["Saldo"] = tabla["Ingresos"] - tabla["Gastos"]
        tabla["Tasa"] = tabla["Saldo"] / tabla["Ingresos"].where(tabla["Ingresos"] != 0)
        tabla.index.name = "mes"
        return tabla

    @property
    def meses_con_gastos(self) -> list[pd.Timestamp]:
        """Meses ya registrados (con gastos > 0). Excluye meses futuros proyectados."""
        m = self.mensual
        return [mes for mes in m.index if m.loc[mes, "Gastos"] > 0]


def parsear_presupuesto(filas: list[list]):
    """Devuelve (df_largo, periodos, ahorros, tarjetas, categorias_por_grupo)."""
    # 1) Fila de encabezado: la que tiene meses reconocibles desde la columna C
    fila_meses, columnas_mes = None, {}
    for i, fila in enumerate(filas[:10]):
        cols = {j: a_mes(v) for j, v in enumerate(fila) if j >= 2}
        cols = {j: m for j, m in cols.items() if m is not None}
        if len(cols) >= 3:
            fila_meses, columnas_mes = i, cols
            break
    if fila_meses is None:
        raise ValueError("No encontré la fila de meses en 'Presupuesto Mensual'.")

    registros, categorias = [], {g: [] for g in SECCIONES.values()}
    ahorros, tarjetas = [], []
    grupo_actual, en_tarjetas = None, False

    for fila in filas[fila_meses + 1:]:
        etiqueta = _texto(_celda(fila, 0))
        if not etiqueta:
            continue
        mayus = etiqueta.upper()

        if mayus in SECCIONES:
            grupo_actual = SECCIONES[mayus]
            continue
        if mayus.startswith("TOTAL") or mayus.startswith("SALDO") or mayus == "INGRESOS DEL MES":
            if mayus.startswith("SALDO"):
                grupo_actual = None  # fin de la parte mensual
            if mayus.startswith("TOTAL DE L"):
                en_tarjetas = False
            continue
        if mayus.startswith("TARJETAS DE CR"):
            en_tarjetas = True
            continue
        if mayus.startswith("TARJETAS DE D"):
            en_tarjetas = False
            continue

        if grupo_actual:
            categorias[grupo_actual].append(etiqueta)
            for j, mes in columnas_mes.items():
                monto = a_numero(_celda(fila, j))
                if monto:
                    registros.append({"mes": mes, "grupo": grupo_actual,
                                      "categoria": etiqueta, "monto": monto})
            continue

        valor = a_numero(_celda(fila, 1))
        if en_tarjetas and valor is not None:
            tarjetas.append((etiqueta, valor))
        elif valor is not None and re.match(r"^(ahorro|inter[eé]s)", etiqueta, re.I):
            ahorros.append((etiqueta, valor))

    df = pd.DataFrame(registros, columns=["mes", "grupo", "categoria", "monto"])
    periodos = sorted(set(columnas_mes.values()))
    return df, periodos, ahorros, tarjetas, categorias


def parsear_registro(filas: list[list]) -> pd.DataFrame:
    """Une los tres bloques de la pestaña Registro en una sola tabla."""
    inicio = 0
    for i, fila in enumerate(filas[:10]):
        if _sin_tildes(_texto(_celda(fila, 0))).lower() == "categoria":
            inicio = i + 1
            break

    registros = []
    for k, fila in enumerate(filas[inicio:]):
        n_fila = inicio + k + 1  # número de fila en la hoja (1-based)
        for grupo, c in BLOQUES_REGISTRO.items():
            categoria = _texto(_celda(fila, c))
            monto = a_numero(_celda(fila, c + 3))
            if not categoria or monto is None:
                continue
            periodo = _celda(fila, c + 2)
            registros.append({
                "grupo": grupo,
                "categoria": categoria,
                "detalle": _texto(_celda(fila, c + 1)),
                "periodo": _texto(periodo),
                "mes": a_mes(periodo),
                "monto": monto,
                "fila": n_fila,
            })
    return pd.DataFrame(registros, columns=["grupo", "categoria", "detalle",
                                            "periodo", "mes", "monto", "fila"])


def construir(filas_presupuesto, filas_registro, fuente, puede_escribir) -> Datos:
    df, periodos, ahorros, tarjetas, categorias = parsear_presupuesto(filas_presupuesto)
    return Datos(
        presupuesto=df,
        registro=parsear_registro(filas_registro),
        ahorros=ahorros,
        tarjetas=tarjetas,
        categorias=categorias,
        periodos=periodos,
        fuente=fuente,
        puede_escribir=puede_escribir,
    )


# ---------------------------------------------------------------------------
# Fuentes de datos
# ---------------------------------------------------------------------------
class FuenteExcel:
    """Lee un .xlsx descargado desde Google Sheets (Archivo > Descargar > .xlsx)."""

    puede_escribir = False

    def __init__(self, ruta: str | Path):
        self.ruta = Path(ruta)

    def _filas(self, hoja: str) -> list[list]:
        from openpyxl import load_workbook
        libro = load_workbook(self.ruta, data_only=True, read_only=True)
        return [list(f) for f in libro[hoja].iter_rows(values_only=True)]

    def cargar(self) -> Datos:
        return construir(self._filas(HOJA_PRESUPUESTO), self._filas(HOJA_REGISTRO),
                         f"Archivo local: {self.ruta.name}", False)

    def agregar_gasto(self, *args, **kwargs):
        raise RuntimeError("El archivo .xlsx local es solo de lectura. "
                           "Conecta Google Sheets para registrar gastos.")


class FuenteGoogle:
    """Lee y escribe directamente en tu Google Sheet con una cuenta de servicio."""

    puede_escribir = True

    def __init__(self, sheet_id: str, credenciales: dict):
        import gspread
        self._gc = gspread.service_account_from_dict(credenciales)
        self._libro = self._gc.open_by_key(sheet_id)

    def _filas(self, hoja: str) -> list[list]:
        from gspread.utils import ValueRenderOption
        return self._libro.worksheet(hoja).get_all_values(
            value_render_option=ValueRenderOption.unformatted)

    def cargar(self) -> Datos:
        return construir(self._filas(HOJA_PRESUPUESTO), self._filas(HOJA_REGISTRO),
                         f"Google Sheets: {self._libro.title}", True)

    def agregar_gasto(self, grupo: str, categoria: str, detalle: str,
                      mes: pd.Timestamp, monto: float) -> int:
        """Escribe el gasto en la primera fila libre del bloque del grupo.
        Devuelve el número de fila usado."""
        from gspread.utils import rowcol_to_a1
        hoja = self._libro.worksheet(HOJA_REGISTRO)
        c = BLOQUES_REGISTRO[grupo]
        valores = hoja.get_all_values()

        # última fila con categoría en ese bloque
        ultima = 2
        for i, fila in enumerate(valores):
            if i >= 2 and _texto(_celda(fila, c)):
                ultima = i + 1
        # primera fila después de esa con las 4 celdas del bloque vacías
        destino = ultima + 1
        while destino <= len(valores) and any(
            _texto(_celda(valores[destino - 1], c + k)) for k in range(4)
        ):
            destino += 1

        rango = f"{rowcol_to_a1(destino, c + 1)}:{rowcol_to_a1(destino, c + 4)}"
        # RAW: el periodo queda como texto ('octubre 2026'), igual que en tu hoja,
        # para que las fórmulas SUMIFS de "Presupuesto Mensual" lo sigan sumando.
        hoja.update(range_name=rango,
                    values=[[categoria, detalle, texto_periodo(mes), float(monto)]],
                    value_input_option="RAW")
        return destino


def crear_fuente():
    """Elige la fuente según la configuración disponible.

    Variables de entorno:
      GOOGLE_CREDENTIALS : contenido JSON de la cuenta de servicio (recomendado en la nube)
      GOOGLE_CREDENTIALS_FILE : ruta al .json (por defecto 'credenciales.json')
      SHEET_ID : ID de tu hoja de Google
      ARCHIVO_XLSX : ruta a un .xlsx local (por defecto 'presupuesto.xlsx')
    """
    base = Path(__file__).parent
    sheet_id = os.environ.get("SHEET_ID", "").strip()

    credenciales = None
    if os.environ.get("GOOGLE_CREDENTIALS"):
        credenciales = json.loads(os.environ["GOOGLE_CREDENTIALS"])
    else:
        archivo = Path(os.environ.get("GOOGLE_CREDENTIALS_FILE", base / "credenciales.json"))
        if archivo.exists():
            credenciales = json.loads(archivo.read_text(encoding="utf-8"))

    if credenciales and sheet_id:
        return FuenteGoogle(sheet_id, credenciales)

    xlsx = Path(os.environ.get("ARCHIVO_XLSX", base / "presupuesto.xlsx"))
    if xlsx.exists():
        return FuenteExcel(xlsx)

    raise RuntimeError(
        "No encontré datos. Configura SHEET_ID + credenciales de Google, "
        "o coloca 'presupuesto.xlsx' junto a app.py (ver README)."
    )
