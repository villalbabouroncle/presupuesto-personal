# Mi presupuesto — Dashboard en Shiny para Python

Dashboard interactivo conectado a tu hoja **Presupuesto Personal** (pestañas *Presupuesto Mensual* y *Registro*).

**Pestañas de la app**

- **Resumen:** ingresos, gastos, saldo y tasa de ahorro del mes (con variación vs. el mes anterior), gráficos de ingresos vs. gastos y saldo mensual, gasto por categoría comparado con tu promedio, alertas de categorías que se salieron de lo habitual, acumulado del año, ahorros y fondo de emergencia.
- **Categorías:** gasto mensual por tipo, evolución de cualquier categoría y mapa de calor categoría × mes.
- **Movimientos:** buscador y filtros sobre todo tu registro, y en qué se va el dinero según el detalle.
- **Registrar:** formulario para anotar un gasto o un ingreso desde el celular. Los gastos se escriben directo en tu pestaña *Registro*, en el bloque que corresponde, con el periodo en el mismo formato que usas (`octubre 2026`), así tus fórmulas `SUMIFS` los suman solas. Los ingresos se escriben en la celda del concepto y mes en *Presupuesto Mensual*: puedes sumar a lo que ya hay (se agrega `+monto` a tu fórmula, p. ej. `=1041,65+856,8+500`) o reemplazar el monto.

Archivos: `app.py` (la app), `datos.py` (lectura y escritura de la hoja), `requirements.txt`.

---

## 1. Probarlo en tu computadora (5 minutos, sin credenciales)

1. Instala Python 3.10 o superior.
2. En una terminal, dentro de esta carpeta:
   ```bash
   pip install -r requirements.txt
   ```
3. En Google Sheets: **Archivo → Descargar → Microsoft Excel (.xlsx)**. Guarda el archivo en esta carpeta con el nombre `presupuesto.xlsx`.
4. Ejecuta:
   ```bash
   shiny run --reload app.py
   ```
5. Abre http://127.0.0.1:8000

En este modo es **solo lectura** (el formulario de registro queda desactivado).

## 2. Conectarlo a tu Google Sheet (lectura y escritura)

Se usa una *cuenta de servicio* de Google: un "usuario robot" al que le compartes tu hoja.

1. Entra a https://console.cloud.google.com y crea un proyecto (gratis).
2. En **APIs y servicios → Biblioteca**, activa **Google Sheets API** y **Google Drive API**.
3. En **APIs y servicios → Credenciales → Crear credenciales → Cuenta de servicio**. Ponle un nombre y créala.
4. Entra a la cuenta de servicio → pestaña **Claves → Agregar clave → JSON**. Se descarga un archivo `.json`. Renómbralo `credenciales.json` y ponlo en esta carpeta.
5. Abre el `.json`, copia el `client_email` (algo como `presupuesto@tu-proyecto.iam.gserviceaccount.com`) y **comparte tu Google Sheet con ese correo como Editor**.
6. Define el ID de tu hoja y ejecuta:
   ```bash
   # Mac / Linux
   export SHEET_ID=1LcolgSH3Dikqs9zQ3LzgZzw3LpbGgo_q4pBWWplYBOE
   # Windows (PowerShell)
   $env:SHEET_ID="1LcolgSH3Dikqs9zQ3LzgZzw3LpbGgo_q4pBWWplYBOE"

   shiny run --reload app.py
   ```

Arriba de la app verás "Google Sheets: …" en lugar de "Archivo local".

## 3. Publicarlo gratis para verlo desde el iPhone (Posit Connect Cloud)

1. Crea un repositorio **privado** en GitHub y sube `app.py`, `datos.py`, `requirements.txt` y `.gitignore`.
   **No subas `credenciales.json` ni tu `.xlsx`** (el `.gitignore` ya los excluye).
2. Crea una cuenta gratis en https://connect.posit.cloud, conecta tu GitHub y elige **Publish → Shiny** con el repositorio y `app.py`.
3. En la configuración del contenido agrega estas **variables secretas**:
   | Variable | Valor |
   |---|---|
   | `SHEET_ID` | el ID de tu hoja |
   | `GOOGLE_CREDENTIALS` | el contenido completo del archivo `credenciales.json` (pégalo tal cual) |
   | `APP_PASSWORD` | una contraseña para entrar a la app |
4. Publica. Abre el enlace en Safari del iPhone → botón Compartir → **Agregar a pantalla de inicio**. Queda como un ícono de app.

`APP_PASSWORD` es importante: el enlace de la app puede ser público y contiene tus finanzas. Con esa variable, la app pide contraseña antes de mostrar o cargar cualquier dato.

Cada vez que hagas *push* a GitHub, Connect Cloud vuelve a publicar la app automáticamente. En el plan gratuito, si nadie la usa un rato se "duerme" y tarda unos segundos en abrir la siguiente vez.

---

## Cómo funciona con tu hoja

- **Ingresos y totales mensuales** salen de *Presupuesto Mensual* (filas de cada sección; las filas `TOTAL…` se recalculan en la app, no se leen).
- **Meses que se muestran:** solo los que tienen gastos. Noviembre y diciembre, que hoy solo tienen ingresos proyectados, aparecerán cuando registres gastos en ellos.
- **Movimientos** salen de *Registro*, uniendo los tres bloques (Necesarios A:D, Discrecionales F:I, Situacionales K:N).
- **Al registrar un gasto**, se escribe en la primera fila libre del bloque correspondiente (nunca sobre una celda con contenido).
- Si agregas una categoría nueva en *Presupuesto Mensual*, aparece sola en la app y en el formulario.
- Si cambias nombres de pestañas, de secciones (`GASTOS NECESARIOS`, etc.) o mueves los bloques de *Registro*, ajusta las constantes al inicio de `datos.py`.
