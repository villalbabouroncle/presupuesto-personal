"""
Dashboard de presupuesto personal — Shiny para Python.

Ejecutar en local:   shiny run --reload app.py
"""

from __future__ import annotations

import os
from datetime import date

import pandas as pd
import plotly.graph_objects as go
from shiny import App, reactive, render, req, ui
from shinywidgets import output_widget, render_plotly

import datos as D

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
CLAVE_APP = os.environ.get("APP_PASSWORD", "")  # si está vacía, no pide contraseña

# Paleta categórica validada (orden fijo: el color sigue a la entidad, no al rango)
AZUL, NARANJA, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
ROJO, GRIS = "#e34948", "#8a8984"
COLOR_GRUPO = {"Necesarios": AZUL, "Discrecionales": NARANJA, "Situacionales": AQUA}
SECUENCIAL = ["#f4f8fd", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
TINTA, TINTA_2, LINEA = "#0b0b0b", "#52514e", "#e6e5e0"

try:
    FUENTE = D.crear_fuente()
    ERROR_FUENTE = ""
except Exception as e:  # se muestra en la app
    FUENTE, ERROR_FUENTE = None, str(e)


# ---------------------------------------------------------------------------
# Formato
# ---------------------------------------------------------------------------
def soles(x: float, dec: int = 2) -> str:
    """S/ 1.898,45 (mismo formato que tu hoja)."""
    if x is None or pd.isna(x):
        return "—"
    s = f"{abs(x):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if x < 0 else ''}S/ {s}"


def pct(x: float) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{x * 100:.0f}%".replace(".", ",")


def variacion(actual: float, anterior: float | None, menos_es_mejor: bool = False):
    """Texto y clase CSS para la variación vs. el mes anterior."""
    if anterior is None or pd.isna(anterior) or anterior == 0:
        return ui.span("sin mes previo para comparar", class_="neutro")
    cambio = (actual - anterior) / abs(anterior)
    if abs(cambio) < 0.005:
        return ui.span("igual que el mes anterior", class_="neutro")
    sube = cambio > 0
    bueno = (not sube) if menos_es_mejor else sube
    flecha = "▲" if sube else "▼"
    return ui.span(f"{flecha} {abs(cambio) * 100:.0f}% vs. mes anterior",
                   class_="bueno" if bueno else "malo")


def figura_base(alto: int = 320) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        height=alto,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, system-ui, sans-serif", size=12, color=TINTA_2),
        separators=",.",
        hoverlabel=dict(bgcolor="white", font_size=12, font_color=TINTA),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, title=None),
        bargap=0.25,
        dragmode=False,
    )
    fig.update_xaxes(showgrid=False, linecolor=LINEA, fixedrange=True, tickfont_color=TINTA_2, automargin=True)
    fig.update_yaxes(gridcolor=LINEA, zerolinecolor="#c9c8c2", fixedrange=True, automargin=True,
                     tickprefix="S/ ", tickformat=",.0f", tickfont_color=TINTA_2)
    return fig


# ---------------------------------------------------------------------------
# Interfaz
# ---------------------------------------------------------------------------
CSS = """
:root { --tinta:#0b0b0b; --tinta-2:#52514e; --borde:#e6e5e0; --fondo:#f7f7f5; }
body { background: var(--fondo); }
.navbar { background: #fff !important; border-bottom: 1px solid var(--borde); }
.navbar-brand { font-weight: 700; letter-spacing: -0.01em; }
.barra-mes { display:flex; gap:12px; align-items:end; flex-wrap:wrap; margin: 4px 0 12px; }
.barra-mes .form-group { margin-bottom: 0; min-width: 200px; }
.barra-mes .fuente { color: var(--tinta-2); font-size: .8rem; margin-left:auto; }
.card { border: 1px solid var(--borde); box-shadow: none; border-radius: 12px; }
.card-header { background: #fff; font-weight: 600; border-bottom: 1px solid var(--borde); }
.kpi { background:#fff; border:1px solid var(--borde); border-radius:12px; padding:14px 16px; height:100%; }
.kpi .etiqueta { color: var(--tinta-2); font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; }
.kpi .valor { color: var(--tinta); font-size: 1.55rem; font-weight: 700; line-height: 1.2; margin: 4px 0 2px;
              font-variant-numeric: tabular-nums; }
.kpi .nota { font-size: .8rem; color: var(--tinta-2); }
.bueno { color: #0f7a3d; } .malo { color: #c0392b; } .neutro { color: var(--tinta-2); }
.fila-kpi { display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap:12px; margin-bottom:12px; }
@media (max-width: 992px) { .fila-kpi { grid-template-columns: repeat(2, minmax(0,1fr)); gap:8px; } }
.alerta { display:flex; justify-content:space-between; gap:8px; padding:8px 0; border-bottom:1px solid var(--borde); }
.alerta:last-child { border-bottom:none; }
.alerta .monto { font-variant-numeric: tabular-nums; white-space: nowrap; }
.seccion { font-size:.85rem; font-weight:600; color:var(--tinta-2); text-transform:uppercase;
           letter-spacing:.05em; margin: 18px 0 8px; }
.aviso { background:#fff8e6; border:1px solid #f3d37a; border-radius:10px; padding:10px 14px; }
.error { background:#fdecec; border:1px solid #f1a9a9; border-radius:10px; padding:14px; }
@media (max-width: 576px) { .kpi .valor { font-size: 1.25rem; } .barra-mes .fuente { margin-left:0; } }
"""



def kpi(id_: str):
    return ui.output_ui(id_)


def fila_kpi(*ids):
    """4 indicadores: 2 columnas en el celular, 4 en pantalla grande."""
    return ui.div(*[kpi(i) for i in ids], class_="fila-kpi")


panel_resumen = ui.nav_panel(
    "Resumen",
    fila_kpi("k_ingresos", "k_gastos", "k_saldo", "k_tasa"),
    ui.layout_columns(
        ui.card(ui.card_header("Ingresos vs. gastos por mes"), output_widget("g_ing_gas")),
        ui.card(ui.card_header("Saldo neto mensual"), output_widget("g_saldo")),
        col_widths={"xs": 12, "lg": (7, 5)}, gap="12px",
    ),
    ui.layout_columns(
        ui.card(ui.card_header(ui.output_text("titulo_categorias", inline=True)),
                output_widget("g_categorias_mes")),
        ui.card(ui.card_header("Categorías por encima de lo habitual"),
                ui.output_ui("alertas"),
                ui.p("Compara el mes elegido con el promedio de los 3 meses anteriores.",
                     class_="nota text-muted small mt-2 mb-0")),
        col_widths={"xs": 12, "lg": (7, 5)}, gap="12px",
    ),
    ui.div("Acumulado del año", class_="seccion"),
    fila_kpi("k_anio_ing", "k_anio_gas", "k_anio_saldo", "k_prom"),
    ui.div("Ahorros y crédito", class_="seccion"),
    fila_kpi("k_ahorro_pen", "k_ahorro_usd", "k_colchon", "k_credito"),
    ui.br(),
)

panel_categorias = ui.nav_panel(
    "Categorías",
    ui.card(ui.card_header("Gasto mensual por tipo"), output_widget("g_grupos")),
    ui.card(
        ui.card_header("Evolución de una categoría"),
        ui.input_select("cat_sel", None, choices=[], width="100%"),
        output_widget("g_cat_linea"),
        ui.output_ui("cat_resumen"),
    ),
    ui.card(ui.card_header("Mapa de calor: categoría × mes"), output_widget("g_heatmap")),
)

panel_movimientos = ui.nav_panel(
    "Movimientos",
    ui.layout_columns(
        ui.input_select("mov_mes", "Periodo", choices={"__todos__": "Todos los meses"}),
        ui.input_select("mov_grupo", "Tipo de gasto",
                        choices={"__todos__": "Todos", **{g: g for g in D.GRUPOS_GASTO}}),
        ui.input_text("mov_buscar", "Buscar en el detalle", placeholder="ej. salida, taxi…"),
        col_widths={"xs": 12, "md": (4, 4, 4)}, gap="12px",
    ),
    fila_kpi("k_mov_total", "k_mov_n", "k_mov_prom", "k_mov_max"),
    ui.card(ui.card_header("¿En qué se va el dinero? (por detalle)"), output_widget("g_detalles")),
    ui.card(ui.card_header("Movimientos"), ui.output_data_frame("tabla_mov")),
)

panel_registrar = ui.nav_panel(
    "Registrar",
    ui.layout_columns(
        ui.card(
            ui.card_header("Nuevo gasto"),
            ui.output_ui("aviso_escritura"),
            ui.input_select("r_grupo", "Tipo de gasto", choices=D.GRUPOS_GASTO, width="100%"),
            ui.input_select("r_categoria", "Categoría", choices=[], width="100%"),
            ui.input_text("r_detalle", "Detalle", placeholder="ej. Taxi a la oficina", width="100%"),
            ui.input_numeric("r_monto", "Monto (S/)", value=None, min=0, step=0.1, width="100%"),
            ui.input_select("r_periodo", "Periodo", choices=[], width="100%"),
            ui.input_action_button("r_guardar", "Guardar gasto", class_="btn-primary w-100 mt-2"),
        ),
        ui.card(ui.card_header("Últimos registros del periodo"), ui.output_ui("ultimos")),
        col_widths={"xs": 12, "lg": (5, 7)}, gap="12px",
    ),
    ui.p("Los ingresos se siguen editando directamente en la hoja (pestaña Presupuesto Mensual).",
         class_="text-muted small"),
)

app_ui = ui.page_navbar(
    panel_resumen,
    panel_categorias,
    panel_movimientos,
    panel_registrar,
    title="Mi presupuesto",
    id="pestanas",
    fillable=False,
    header=ui.div(
        ui.tags.head(
            ui.tags.style(CSS),
            ui.tags.meta(name="apple-mobile-web-app-capable", content="yes"),
            ui.tags.meta(name="apple-mobile-web-app-title", content="Presupuesto"),
        ),
        ui.div(
            ui.input_select("mes", "Mes", choices=[]),
            ui.input_action_button("recargar", "↻ Actualizar datos", class_="btn-outline-secondary"),
            ui.output_text("fuente_txt", inline=False),
            class_="barra-mes container-fluid",
        ),
        ui.output_ui("error_fuente"),
    ),
)


# ---------------------------------------------------------------------------
# Servidor
# ---------------------------------------------------------------------------
def server(input, output, session):
    autenticado = reactive.value(not CLAVE_APP)
    version = reactive.value(0)

    # ---------- acceso ----------
    if CLAVE_APP:
        ui.modal_show(ui.modal(
            ui.input_password("clave", "Contraseña", width="100%"),
            ui.output_ui("clave_error"),
            title="Mi presupuesto",
            footer=ui.input_action_button("entrar", "Entrar", class_="btn-primary"),
            easy_close=False,
        ))

        intento_fallido = reactive.value(False)

        @reactive.effect
        @reactive.event(input.entrar)
        def _():
            if input.clave() == CLAVE_APP:
                autenticado.set(True)
                ui.modal_remove()
            else:
                intento_fallido.set(True)

        @render.ui
        def clave_error():
            if intento_fallido():
                return ui.p("Contraseña incorrecta.", class_="malo small mb-0")

    # ---------- datos ----------
    @reactive.calc
    def datos() -> D.Datos:
        req(autenticado())
        version()
        req(FUENTE is not None)
        return FUENTE.cargar()

    @reactive.effect
    @reactive.event(input.recargar)
    def _():
        version.set(version() + 1)
        ui.notification_show("Datos actualizados", duration=2)

    @render.ui
    def error_fuente():
        if ERROR_FUENTE:
            return ui.div(ui.strong("No se pudieron cargar los datos. "), ERROR_FUENTE,
                          class_="error container-fluid")

    @render.text
    def fuente_txt():
        return datos().fuente

    # Opciones de mes, categorías y periodo cuando cambian los datos
    @reactive.effect
    def _():
        d = datos()
        meses = d.meses_con_gastos
        opciones = {m.strftime("%Y-%m"): D.etiqueta_mes(m) for m in reversed(meses)}
        actual = input.mes() if input.mes() in opciones else next(iter(opciones), None)
        ui.update_select("mes", choices=opciones, selected=actual)
        ui.update_select("mov_mes", choices={"__todos__": "Todos los meses", **opciones},
                         selected=input.mov_mes() if input.mov_mes() in opciones else actual)

        cats = [c for g in D.GRUPOS_GASTO for c in d.categorias.get(g, [])
                if c in set(d.presupuesto["categoria"])]
        ui.update_select("cat_sel", choices=cats,
                         selected=input.cat_sel() if input.cat_sel() in cats else
                         ("Consumo Doméstico" if "Consumo Doméstico" in cats else cats[0]))

        hoy = pd.Timestamp(date.today().year, date.today().month, 1)
        periodos = {m.strftime("%Y-%m"): D.etiqueta_mes(m) for m in d.periodos}
        por_defecto = hoy.strftime("%Y-%m") if hoy.strftime("%Y-%m") in periodos else actual
        ui.update_select("r_periodo", choices=periodos,
                         selected=input.r_periodo() if input.r_periodo() in periodos else por_defecto)

    @reactive.calc
    def mes() -> pd.Timestamp:
        req(input.mes())
        return pd.Timestamp(input.mes() + "-01")

    @reactive.calc
    def mensual() -> pd.DataFrame:
        d = datos()
        return d.mensual.loc[d.meses_con_gastos]

    def fila(m):
        tabla = mensual()
        return tabla.loc[m] if m in tabla.index else None

    def mes_anterior():
        tabla = mensual()
        previos = [x for x in tabla.index if x < mes()]
        return tabla.loc[previos[-1]] if previos else None

    def tarjeta(etiqueta, valor, nota=None):
        return ui.div(ui.div(etiqueta, class_="etiqueta"), ui.div(valor, class_="valor"),
                      ui.div(nota or "", class_="nota"), class_="kpi")

    # ---------- KPIs del mes ----------
    @render.ui
    def k_ingresos():
        f, a = fila(mes()), mes_anterior()
        return tarjeta("Ingresos", soles(f["Ingresos"]),
                       variacion(f["Ingresos"], None if a is None else a["Ingresos"]))

    @render.ui
    def k_gastos():
        f, a = fila(mes()), mes_anterior()
        return tarjeta("Gastos", soles(f["Gastos"]),
                       variacion(f["Gastos"], None if a is None else a["Gastos"], menos_es_mejor=True))

    @render.ui
    def k_saldo():
        f = fila(mes())
        clase = "bueno" if f["Saldo"] >= 0 else "malo"
        return tarjeta("Saldo neto", ui.span(soles(f["Saldo"]), class_=clase),
                       "lo que te quedó este mes" if f["Saldo"] >= 0 else "gastaste más de lo que ingresó")

    @render.ui
    def k_tasa():
        f = fila(mes())
        t = del_anio()
        tasa_anio = t["Saldo"].sum() / t["Ingresos"].sum() if t["Ingresos"].sum() else None
        return tarjeta("Tasa de ahorro", pct(f["Tasa"]), f"en lo que va del año: {pct(tasa_anio)}")

    # ---------- KPIs anuales ----------
    def del_anio():
        tabla = mensual()
        return tabla[(tabla.index.year == mes().year) & (tabla.index <= mes())]

    @render.ui
    def k_anio_ing():
        t = del_anio()
        return tarjeta(f"Ingresos {mes().year}", soles(t["Ingresos"].sum(), 0),
                       f"hasta {D.etiqueta_mes(mes()).lower()}")

    @render.ui
    def k_anio_gas():
        t = del_anio()
        return tarjeta(f"Gastos {mes().year}", soles(t["Gastos"].sum(), 0), f"{len(t)} meses")

    @render.ui
    def k_anio_saldo():
        t = del_anio()
        s = t["Saldo"].sum()
        tasa = s / t["Ingresos"].sum() if t["Ingresos"].sum() else None
        return tarjeta("Ahorro neto del año", ui.span(soles(s, 0), class_="bueno" if s >= 0 else "malo"),
                       f"{pct(tasa)} de tus ingresos")

    @render.ui
    def k_prom():
        t = mensual()
        ult = t[t.index <= mes()].tail(6)
        return tarjeta("Gasto promedio", soles(ult["Gastos"].mean(), 0),
                       f"por mes, últimos {len(ult)} meses")

    # ---------- Ahorros y crédito ----------
    def buscar_ahorro(*palabras):
        for nombre, valor in datos().ahorros:
            if all(p.lower() in nombre.lower() for p in palabras):
                return nombre, valor
        return None, None

    @render.ui
    def k_ahorro_pen():
        _, v = buscar_ahorro("ahorro", "pen")
        _, interes = buscar_ahorro("inter")
        return tarjeta("Ahorro en soles", soles(v, 0),
                       f"gana {soles(interes)} al mes" if interes else "")

    @render.ui
    def k_ahorro_usd():
        _, v = buscar_ahorro("ahorro", "usd")
        valor = soles(v, 0).replace("S/", "US$") if v is not None else "—"
        return tarjeta("Equivalente en dólares", valor, "aproximado, según tu hoja")

    @render.ui
    def k_colchon():
        _, v = buscar_ahorro("ahorro", "pen")
        t = mensual()
        prom = t[t.index <= mes()].tail(6)["Gastos"].mean()
        meses = v / prom if v and prom else None
        return tarjeta("Fondo de emergencia",
                       f"{meses:.1f} meses".replace(".", ",") if meses else "—",
                       "de gastos cubiertos con tu ahorro en soles")

    @render.ui
    def k_credito():
        total = sum(v for _, v in datos().tarjetas)
        return tarjeta("Línea de crédito", soles(total, 0) if total else "—",
                       f"{len(datos().tarjetas)} tarjetas")

    # ---------- Gráficos: Resumen ----------
    @render_plotly
    def g_ing_gas():
        t = mensual()
        x = [D.etiqueta_mes(m, corto=True) for m in t.index]
        fig = figura_base()
        fig.add_bar(name="Ingresos", x=x, y=t["Ingresos"], marker_color=AQUA,
                    marker_line_width=0, hovertemplate="Ingresos: S/ %{y:,.2f}<extra></extra>")
        fig.add_bar(name="Gastos", x=x, y=t["Gastos"], marker_color=NARANJA,
                    marker_line_width=0, hovertemplate="Gastos: S/ %{y:,.2f}<extra></extra>")
        fig.update_layout(barmode="group", bargroupgap=0.08, hovermode="x unified")
        return fig

    @render_plotly
    def g_saldo():
        t = mensual()
        x = [D.etiqueta_mes(m, corto=True) for m in t.index]
        colores = [AZUL if v >= 0 else ROJO for v in t["Saldo"]]
        fig = figura_base()
        fig.add_bar(x=x, y=t["Saldo"], marker_color=colores, marker_line_width=0,
                    text=[soles(v, 0) for v in t["Saldo"]], textposition="outside",
                    cliponaxis=False, textfont=dict(size=10, color=TINTA_2),
                    hovertemplate="%{x}<br>Saldo: S/ %{y:,.2f}<extra></extra>", showlegend=False)
        fig.update_layout(margin=dict(t=24))
        return fig

    @render.text
    def titulo_categorias():
        return f"Gasto por categoría — {D.etiqueta_mes(mes())}"

    @render_plotly
    def g_categorias_mes():
        d = datos()
        p = d.presupuesto[d.presupuesto["grupo"] != "Ingresos"]
        actual = p[p["mes"] == mes()].groupby(["categoria", "grupo"], as_index=False)["monto"].sum()
        actual = actual[actual["monto"] != 0].sort_values("monto")
        previos = [m for m in d.meses_con_gastos if m < mes()][-3:]
        prom = (p[p["mes"].isin(previos)].groupby("categoria")["monto"].sum() / max(len(previos), 1))

        fig = figura_base(alto=max(260, 34 * len(actual) + 60))
        for g in D.GRUPOS_GASTO:
            sub = actual[actual["grupo"] == g]
            if sub.empty:
                continue
            fig.add_bar(name=g, y=sub["categoria"], x=sub["monto"], orientation="h",
                        marker_color=COLOR_GRUPO[g], marker_line_width=0,
                        text=[soles(v, 0) for v in sub["monto"]], textposition="outside",
                        cliponaxis=False, textfont=dict(color=TINTA_2, size=11),
                        hovertemplate="%{y}<br>S/ %{x:,.2f}<extra>" + g + "</extra>")
        if previos:
            fig.add_scatter(name="Promedio 3 meses previos", y=actual["categoria"],
                            x=[prom.get(c, 0) for c in actual["categoria"]], mode="markers",
                            marker=dict(symbol="line-ns", size=18, line=dict(width=2.5, color=TINTA)),
                            hovertemplate="Promedio previo: S/ %{x:,.2f}<extra></extra>")
        fig.update_layout(barmode="overlay", margin=dict(r=56))
        fig.update_yaxes(tickfont=dict(size=11, color=TINTA))
        fig.update_yaxes(categoryorder="array", categoryarray=list(actual["categoria"]),
                         tickprefix="", gridcolor="rgba(0,0,0,0)", automargin=True)
        fig.update_xaxes(showgrid=False, showticklabels=False, showline=False, zeroline=True,
                         zerolinecolor="#c9c8c2")  # los montos ya van rotulados en cada barra
        return fig

    @render.ui
    def alertas():
        d = datos()
        p = d.presupuesto[d.presupuesto["grupo"] != "Ingresos"]
        previos = [m for m in d.meses_con_gastos if m < mes()][-3:]
        if not previos:
            return ui.p("Aún no hay meses previos para comparar.", class_="text-muted")
        actual = p[p["mes"] == mes()].groupby("categoria")["monto"].sum()
        prom = p[p["mes"].isin(previos)].groupby("categoria")["monto"].sum() / len(previos)
        filas = []
        for cat, monto in actual.items():
            base = prom.get(cat, 0.0)
            exceso = monto - base
            if exceso > 30 and (base == 0 or monto / base > 1.25):
                filas.append((exceso, cat, monto, base))
        if not filas:
            return ui.p("✓ Ninguna categoría se salió de lo habitual este mes.", class_="bueno")
        filas.sort(reverse=True)
        return ui.div(*[
            ui.div(
                ui.div(ui.strong(cat), ui.br(),
                       ui.span(f"promedio previo {soles(base, 0)}", class_="text-muted small")),
                ui.div(ui.span(soles(monto, 0)), ui.br(),
                       ui.span(f"+{soles(exceso, 0)}", class_="malo small"),
                       class_="monto text-end"),
                class_="alerta")
            for exceso, cat, monto, base in filas[:6]
        ])

    # ---------- Gráficos: Categorías ----------
    @render_plotly
    def g_grupos():
        t = mensual()
        x = [D.etiqueta_mes(m, corto=True) for m in t.index]
        fig = figura_base()
        for g in D.GRUPOS_GASTO:
            fig.add_bar(name=g, x=x, y=t[g], marker_color=COLOR_GRUPO[g],
                        marker_line=dict(color="white", width=2),
                        hovertemplate=g + ": S/ %{y:,.2f}<extra></extra>")
        fig.update_layout(barmode="stack", hovermode="x unified")
        return fig

    def serie_categoria():
        d = datos()
        req(input.cat_sel())
        p = d.presupuesto[d.presupuesto["categoria"] == input.cat_sel()]
        serie = p.groupby("mes")["monto"].sum().reindex(d.meses_con_gastos, fill_value=0.0)
        return serie

    @render_plotly
    def g_cat_linea():
        s = serie_categoria()
        x = [D.etiqueta_mes(m, corto=True) for m in s.index]
        grupo = datos().presupuesto.loc[
            datos().presupuesto["categoria"] == input.cat_sel(), "grupo"].iloc[0]
        fig = figura_base(alto=280)
        fig.add_scatter(x=x, y=s.values, mode="lines+markers", name=input.cat_sel(),
                        line=dict(color=COLOR_GRUPO.get(grupo, AZUL), width=2),
                        marker=dict(size=8, line=dict(color="white", width=2)),
                        hovertemplate="%{x}<br>S/ %{y:,.2f}<extra></extra>", showlegend=False)
        prom = s.mean()
        fig.add_hline(y=prom, line=dict(color=GRIS, width=1.5, dash="dash"),
                      annotation_text=f"promedio {soles(prom, 0)}", annotation_position="top left",
                      annotation_font=dict(color=TINTA_2, size=11))
        return fig

    @render.ui
    def cat_resumen():
        s = serie_categoria()
        d = datos()
        r = d.registro[(d.registro["categoria"] == input.cat_sel())]
        total = s.sum()
        partes = [f"Total del periodo: {soles(total, 0)}",
                  f"Mes más alto: {D.etiqueta_mes(s.idxmax())} ({soles(s.max(), 0)})" if total else ""]
        if not r.empty:
            top = (r.assign(d=r["detalle"].str.strip().str.lower())
                    .groupby("d")["monto"].sum().sort_values(ascending=False).head(3))
            partes.append("Más frecuente en el registro: " +
                          ", ".join(f"{k} ({soles(v, 0)})" for k, v in top.items()))
        return ui.div(*[ui.div(p_) for p_ in partes if p_], class_="small text-muted")

    @render_plotly
    def g_heatmap():
        d = datos()
        p = d.presupuesto[d.presupuesto["grupo"] != "Ingresos"]
        t = p.pivot_table(index="categoria", columns="mes", values="monto", aggfunc="sum", fill_value=0)
        t = t.reindex(columns=d.meses_con_gastos, fill_value=0)
        orden = [c for g in D.GRUPOS_GASTO for c in d.categorias.get(g, []) if c in t.index]
        t = t.loc[orden]
        t = t[(t != 0).any(axis=1)]
        x = [D.etiqueta_mes(m, corto=True) for m in t.columns]
        escala = [[i / (len(SECUENCIAL) - 1), c] for i, c in enumerate(SECUENCIAL)]
        fig = figura_base(alto=max(320, 30 * len(t) + 80))
        fig.add_heatmap(z=t.values, x=x, y=list(t.index), colorscale=escala, xgap=2, ygap=2,
                        hovertemplate="%{y}<br>%{x}: S/ %{z:,.2f}<extra></extra>",
                        colorbar=dict(thickness=10, tickprefix="S/ ", tickformat=",.0f", outlinewidth=0))
        fig.update_yaxes(autorange="reversed", tickprefix="", gridcolor="rgba(0,0,0,0)", automargin=True)
        return fig

    # ---------- Movimientos ----------
    @reactive.calc
    def movimientos() -> pd.DataFrame:
        r = datos().registro.copy()
        if input.mov_mes() and input.mov_mes() != "__todos__":
            r = r[r["mes"] == pd.Timestamp(input.mov_mes() + "-01")]
        if input.mov_grupo() and input.mov_grupo() != "__todos__":
            r = r[r["grupo"] == input.mov_grupo()]
        texto = (input.mov_buscar() or "").strip().lower()
        if texto:
            r = r[r["detalle"].str.lower().str.contains(texto, regex=False)
                  | r["categoria"].str.lower().str.contains(texto, regex=False)]
        return r

    @render.ui
    def k_mov_total():
        return tarjeta("Total", soles(movimientos()["monto"].sum()))

    @render.ui
    def k_mov_n():
        return tarjeta("Movimientos", str(len(movimientos())))

    @render.ui
    def k_mov_prom():
        r = movimientos()
        return tarjeta("Gasto promedio", soles(r["monto"].mean()) if len(r) else "—", "por movimiento")

    @render.ui
    def k_mov_max():
        r = movimientos()
        if r.empty:
            return tarjeta("Mayor gasto", "—")
        top = r.loc[r["monto"].idxmax()]
        return tarjeta("Mayor gasto", soles(top["monto"]), top["detalle"] or top["categoria"])

    @render_plotly
    def g_detalles():
        r = movimientos()
        req(not r.empty)
        r = r.assign(clave=r["detalle"].str.strip().str.capitalize().replace("", "(sin detalle)"))
        top = (r.groupby(["clave", "grupo"], as_index=False)
                .agg(monto=("monto", "sum"), veces=("monto", "size"))
                .sort_values("monto", ascending=False).head(12).sort_values("monto"))
        fig = figura_base(alto=max(260, 30 * len(top) + 60))
        for g in D.GRUPOS_GASTO:
            sub = top[top["grupo"] == g]
            if sub.empty:
                continue
            fig.add_bar(name=g, y=sub["clave"], x=sub["monto"], orientation="h",
                        marker_color=COLOR_GRUPO[g], marker_line_width=0,
                        customdata=sub["veces"], text=[soles(v, 0) for v in sub["monto"]],
                        textposition="outside", cliponaxis=False,
                        textfont=dict(color=TINTA_2, size=11),
                        hovertemplate="%{y}<br>S/ %{x:,.2f} en %{customdata} movimiento(s)<extra></extra>")
        fig.update_layout(barmode="overlay", margin=dict(r=56))
        fig.update_yaxes(tickfont=dict(size=11, color=TINTA))
        fig.update_yaxes(categoryorder="array", categoryarray=list(top["clave"]), tickprefix="",
                         gridcolor="rgba(0,0,0,0)")
        fig.update_xaxes(showgrid=False, showticklabels=False, showline=False, zeroline=True,
                         zerolinecolor="#c9c8c2")  # los montos ya van rotulados en cada barra
        return fig

    @render.data_frame
    def tabla_mov():
        r = movimientos().sort_values(["mes", "fila"], ascending=[False, False])
        vista = pd.DataFrame({
            "Periodo": [D.etiqueta_mes(m) if pd.notna(m) else p_ for m, p_ in zip(r["mes"], r["periodo"])],
            "Tipo": r["grupo"],
            "Categoría": r["categoria"],
            "Detalle": r["detalle"],
            "Monto (S/)": r["monto"].round(2),
        })
        return render.DataGrid(vista, filters=False, width="100%", height="420px")

    # ---------- Registrar ----------
    @render.ui
    def aviso_escritura():
        if not datos().puede_escribir:
            return ui.div("Estás viendo un archivo local de solo lectura. Para registrar gastos, "
                          "conecta la app a tu Google Sheet (ver README).", class_="aviso mb-3")

    @reactive.effect
    def _():
        d = datos()
        cats = [c for c in d.categorias.get(input.r_grupo(), []) if "Reembolso" not in c]
        ui.update_select("r_categoria", choices=cats)

    @reactive.effect
    @reactive.event(input.r_guardar)
    def _():
        d = datos()
        monto = input.r_monto()
        if not d.puede_escribir:
            ui.notification_show("Modo solo lectura: conecta Google Sheets para guardar.", type="warning")
            return
        if not input.r_categoria() or monto is None or monto == 0:
            ui.notification_show("Completa la categoría y el monto.", type="warning")
            return
        try:
            fila_n = FUENTE.agregar_gasto(input.r_grupo(), input.r_categoria(),
                                          (input.r_detalle() or "").strip(),
                                          pd.Timestamp(input.r_periodo() + "-01"), float(monto))
        except Exception as e:
            ui.notification_show(f"No se pudo guardar: {e}", type="error", duration=8)
            return
        ui.notification_show(f"Guardado ✓ ({soles(monto)} en {input.r_categoria()}, fila {fila_n})",
                             type="message", duration=4)
        ui.update_text("r_detalle", value="")
        ui.update_numeric("r_monto", value=None)
        version.set(version() + 1)

    @render.ui
    def ultimos():
        d = datos()
        req(input.r_periodo())
        m = pd.Timestamp(input.r_periodo() + "-01")
        r = d.registro[d.registro["mes"] == m].sort_values("fila", ascending=False)
        if r.empty:
            return ui.p("Todavía no hay gastos registrados en este periodo.", class_="text-muted")
        total = r["monto"].sum()
        return ui.div(
            ui.p(ui.strong(f"{len(r)} gastos · {soles(total)}"), class_="mb-2"),
            *[ui.div(ui.div(ui.strong(f.detalle or f.categoria), ui.br(),
                            ui.span(f"{f.categoria} · {f.grupo}", class_="text-muted small")),
                     ui.div(soles(f.monto), class_="monto"), class_="alerta")
              for f in r.head(8).itertuples()],
        )


app = App(app_ui, server)
