---
paths:
  - "src/homeauto/api.py"
  - "src/homeauto/web/**"
  - "src/homeauto/people.py"
  - "src/homeauto/main.py"
  - "deploy/domotica-say"
  - "deploy/push-apk.sh"
  - "deploy/tele-version.sh"
  - "deploy/capture-ui.sh"
  - "tests/web/**"
  - "tests/test_api_server.py"
  - "tests/test_api_service.py"
  - "tests/test_people.py"
  - "tests/test_persons.py"
---

# API y pantalla de la casa

## API

`homeauto/api.py` expone un servidor HTTP **solo para la LAN**: `POST /say`, con token
compartido, para que otros sistemas anuncien cosas, y `GET /health`. Todo lo demás lo
delega a `web.WebApp`, la **Pantalla de la casa**. La lógica (`ApiService`, `WebApp`) está
separada del transporte HTTP y se prueba sin red.

- **Sin `API_TOKEN` la API no arranca**, y con ella tampoco la pantalla. Apagada es el estado
  seguro; un endpoint que hace hablar la casa no puede quedar abierto por olvido.
- El token se compara con `hmac.compare_digest`, no con `==`.
- 🔴 **El token es de `/say`, no del servidor.** `/health` y las rutas de la pantalla no lo
  piden. La ruta se compara sin la query, así que `/health?x=1` sigue siendo `/health`.
- `api._Handler` también atiende `PUT` y `DELETE`, y le pasa a `WebApp` los headers y el
  cuerpo. **Un cuerpo de más de ocho kilobytes (`MAX_BODY`) es un 413** antes de leerse.
- **`urgent` es la única forma de saltear el horario de descanso.** Producción caída a las
  3 AM lo amerita; un backup terminado, no. ⚠️ **No saltea el modo vacaciones**: ahí `/say`
  urgente también queda solo escrito.
- El CLI `domotica-say` lee el token del archivo de configuración: pasarlo por línea de
  comandos lo dejaría en el historial del shell.

## Pantalla de la casa

`homeauto/web/` sirve cuatro páginas y sus datos en el mismo `ApiServer` de la API (puerto
`API_PORT`, 8099), y **existe solo si la API arrancó**, o sea con `API_TOKEN`.

- 🔴 **El CSS de cada página va bajo la clase de su `body`**: `.kiosk` en `/pantalla`,
  `.kiosk.alarm-view` en `/alarma`, `.agenda` y `.control`. Suelto queda solo lo compartido
  (tokens, tarjetas, botones, barra) y la piel de FullCalendar bajo `.fc`.
  Una regla suelta pisa las clases que `/api/events` les pone a los eventos de FullCalendar
  (`casa`, `alarm`, `reminder`, `timer`, `past`, `google`, `feriado`, `ev`): el `.alarm` de la
  vista de alarma estiraba cada alarma del calendario a `100vh` y la agenda las escondía detrás
  de «+N más». `tests/web/test_app.py` lo sostiene.

| Ruta | Qué es |
| --- | --- |
| `/agenda` | FullCalendar con lo de la casa y lo de Google, en mes, semana, día y lista. `?m=AAAA-MM` abre en ese mes; `?nuevo=1`, si la pantalla escribe, abre el formulario de un aviso nuevo (`opensNew()`) |
| `/pantalla` | el kiosco en tarjetas: reloj, clima, lo próximo, lo de hoy, la idea del menú y las dos listas. `?ver=1` es solo lectura |
| `/alarma?job=<id>` | la vista de una alarma que suena, para la tele. Ver **Pantalla en la TV**, en `.claude/rules/pantalla-tv.md` |
| `/` | un 302 a `/control`; otro método es 405 |
| `/control` | manejar la casa sin Telegram: lo urgente arriba, texto libre, «A mano» y los comandos en paneles. `?soy=<id>` elige a esa persona del padrón y la guarda. Ver **Control desde la web** |
| `/api/events?start=…&end=…` | lo de un rango, como `{events, calendars, problems}` |
| `/api/ringing/<id>` | si esa alarma sigue sonando, su mensaje, para quién (`for`) y la hora del servidor |
| `/api/board` | el estado del kiosco: hora, descanso, vacaciones, hoy, lo próximo, clima, `meal` y listas como `[{id, text}]` |
| `GET /api/people` | si la pantalla escribe, los chats de la casa con su nombre, los equipos, el padrón (`persons`) y los chats con el nombre visto en Telegram (`chats`, `seen`) |
| `POST /api/persons` | suma una persona al padrón. Ver **Padrón de la casa** |
| `PUT`/`DELETE /api/persons/<id>` | cambia el nombre o el chat de una persona, o la saca del padrón |
| `POST /api/jobs` | crea un aviso de la casa |
| `GET`/`PUT`/`DELETE /api/jobs/<id>` | lee, edita o borra un aviso |
| `POST /api/lists/<lista>` | suma a compras o pendientes lo escrito, partido como en el chat |
| `POST /api/lists/<lista>/<id>/done` | tacha un ítem de compras o pendientes |
| `GET /api/live?chat=<id>` o `?person=<id>` | lo que pide atención ahora, con los botones que le tocan a ese chat o esa persona, y si puede mandar comandos (`can_command`) |
| `POST /api/command` | corre un botón (`data`) o un mensaje suelto (`text`) a nombre de `chat_id` o de `person_id` |
| `/static/manifest.webmanifest`, `/static/icon-192.png`, `/static/icon-512.png` | el manifest y los íconos del acceso directo a `/control` |
| `GET /app/tele.apk` | el APK de la app de la tele, para bajarlo con Downloader o con un explorador de archivos con acceso a la red. Ver **App de la tele** |
| `GET /app/tele.json` | la versión del APK publicado, para que la app de la tele sepa si hay una nueva. Ver **App de la tele** |
| `GET /api/tele/setup` | las teles con pantalla, el padrón (`persons`) y los chats de la casa (`people`), para configurar la app de la tele |
| `POST /api/tele/hello` | registra una tele con su versión y capacidades |
| `GET /api/tele/<alias>/poll` | el latido de una tele, la alarma que suena en ella, los recordatorios que esperan «Hecho», sus órdenes pendientes y si la casa calla. Ver **Registro en el CT**, en `.claude/rules/app-tele.md` |
| `POST /api/tele/<alias>/ack` | lo que la app dice de una orden: recibida, hecha o fallida. Ver **Órdenes**, en `.claude/rules/app-tele.md` |

`Board` arma los datos y `WebApp.handle(Request) -> Response` rutea; ninguno de los dos
conoce `http.server`, que solo traduce en `api._Handler`. Es la regla de **Arquitectura**, en `CLAUDE.md`.

- 🔴 **Abierta en la LAN, sin login ni token, también para escribir.** Decisión del dueño:
  la red de la casa es de confianza —cable y un WiFi oculto— y la pantalla la tiene que poder
  usar cualquiera de la casa. ⚠️ La ve y la escribe **cualquiera que alcance el CT**: los
  mensajes de las alarmas y los títulos de Google quedan a la vista, y un aviso se puede
  crear o borrar sin decir quién es.
- 🔴 **Las URLs privadas de iCal nunca llegan al navegador.** `problems` dice solo el alias
  ("No pude leer el calendario X."). El texto de la excepción no se reenvía porque requests
  mete la URL adentro (`404 for url: …`), y la URL es una credencial. Hay test con una URL
  secreta que no puede aparecer en ninguna respuesta.
- 🔴 **La CSP es la defensa, y cada excepción tiene su motivo.** `script-src 'self'`, sin
  `unsafe-inline` ni `unsafe-eval`, y ningún script inline en las páginas.
  `style-src 'unsafe-inline'` porque FullCalendar inyecta su CSS en un `<style>`.
  `font-src 'self' data:` porque los íconos de FullCalendar son una fuente embebida como
  `data:` URI: sin eso **se ven rotos**, y pasó con las flechas (#30). Las flechas de la
  barra ya son botones propios; la fuente sigue en el bundle para los íconos que FullCalendar
  dibuja solo. Hay test del script y de la fuente.
- 🔴 **Nada de `style=` ni `<style>` en las páginas, y desde el JS solo
  `style.setProperty()`**, para pasar un color como variable (`--c`, `--ev`). Lo que se
  escribe por CSSOM no depende de `unsafe-inline`; un atributo en el HTML sí. Hay test de
  las dos cosas.
- 🔴 **Un título va siempre como texto.** `textContent`, nunca `innerHTML` ni un
  `eventContent` que devuelva HTML: un título de Google o el mensaje de una alarma es texto
  de una persona.
- 🔴 **Lo que va a sonar sale de `store.next_run(job, after)`, la misma función que usa
  `Reminders` para reagendar.** Con dos copias, la agenda podía mostrar un día en que la
  alarma no suena. Es la misma regla que `down_line()`. `schedule/month.py` expande los jobs
  y traduce el historial; `Board` los pasa al formato de FullCalendar.
- **Para quién es cada aviso viaja en el evento**: `extendedProps` trae `assignee`,
  `assignee_id` y `for`, el nombre a mostrar, y el título suma «· para <nombre>» o «· para
  todos». `board.for_name()` decide, con el padrón leído una vez por pedido
  (`person_names()`): «nadie», una persona que ya no está o un padrón que falla dan `None`, y
  el aviso se ve como antes. Lo futuro trae la asignación del job; lo pasado, la foto de lo
  que sonó. ⚠️ **El turno no cuenta hasta que suena**: una ocurrencia futura de un turno de
  alguien del padrón se muestra con la asignación del job, no con la de esa persona.
- **A quién le toca se ve en la agenda y en el kiosco.** `month.occurrences_between()` le
  pone el prefijo de `with_turn()` a cada ocurrencia futura y el historial ya lo trae, así
  que viaja en el mensaje: los scripts no cambiaron.
- **Lo pasado sale del historial, lo futuro de los jobs**, cortados en el mismo `now`: el día
  de hoy no muestra dos veces lo que ya sonó. Lo que sonó lleva cómo terminó en el título
  (`board.marks()`): una alarma apagada dice «🔕 apagada <nombre>» y sus repeticiones, «🔔×N».
- **Un rango es de como mucho sesenta y dos días** (`MAX_RANGE`); invertido o más largo es un
  400. Las fechas de FullCalendar llegan con offset y se llevan a hora local sin zona, como
  guarda la casa sus jobs.
- **Google se cachea cinco minutos por rango** (`CALENDAR_TTL`), con tope de treinta y dos
  rangos (`MAX_CACHED_RANGES`): navegar meses no le pega a Google en cada clic. ⚠️ Un
  calendario caído también queda cacheado: el aviso dura hasta cinco minutos.
- **El clima se cachea quince minutos** (`WEATHER_TTL`) y **una falla no se cachea**: se
  vuelve a pedir en el polling siguiente.
- Un error al armar un feed devuelve 500 y se loguea; no tumba el servidor de `/say`.
- **En pantalla ancha (≥720 px) el calendario ocupa el alto de la ventana**: `fitHeight()`
  le da el alto que queda debajo de la barra y `dayMaxEvents: true`, así cada día muestra lo
  que entra y el resto va a «+N más», sin scroll de página. Se recalcula al cambiar el
  tamaño. En angosta, `height: auto` y como mucho cinco por día.
- **Semana y día abren una hora antes de la actual** (`nowScroll()`), al cargar y al cambiar
  de vista. ⚠️ **No hay `slotMinTime`**: escondería lo que suena antes de las seis, y en el CT
  el descanso termina a las 05:25.
- **«Ver» filtra la agenda por persona**, con «Toda la casa» y cada persona del padrón; sin
  padrón no aparece. Con una persona elegida, de lo de la casa se ve lo suyo y lo de todos,
  y se esconde lo de nadie y lo de otro; Google y los feriados se ven siempre
  (`visibleFor()`). Se oculta con `display: none`, igual que lo plegado, sin pedir el feed de
  nuevo. La elección queda en el `localStorage` del dispositivo (`casa.agenda.ver`); una
  persona que ya no está vuelve a «Toda la casa».
- **Hoy, lo que ya pasó queda plegado bajo un «…»** que lo despliega. `isPastToday()` decide:
  lo de la casa que ya sonó, o lo que terminó antes de ahora; lo de todo el día nunca. Se
  oculta con `display: none` desde que llega el feed, así no cuenta en el «+N más». Solo en
  la vista de mes, y se recalcula cada minuto.
- **La agenda vuelve a pedir sus eventos cada minuto** (`refresh()`, con el mismo `TICK_MS`):
  lo agregado desde Telegram o desde otra pantalla aparece solo. ⚠️ Lo de Google sigue
  atado a `CALENDAR_TTL`, así que un evento nuevo ahí tarda hasta cinco minutos más.

**Cómo se ve la agenda.** Barra propia (`headerToolbar: false`): título del período,
anterior, «Hoy», siguiente, Mes/Semana/Día/Lista (`listWeek`) y enlaces a `/pantalla` y
`/control`.

- **La vista con que abre la decide `startView()`**: con `?m=` siempre el mes; si no, la
  última que se tocó en ese dispositivo (`localStorage`, `casa.agenda.vista`); sin guardada,
  mes en ancho (≥720 px) y «Lista» en angosto.
- **En el celular (≤640 px) la barra va en grilla**: título y enlaces, después flechas y
  vistas, y «Ver» en una tercera fila si hay padrón. En tablet (641 a 1100 px), una fila con
  el título más chico.
- **En el celular «Nuevo aviso» queda en un círculo con el «+»**: el texto se esconde y el
  botón conserva el nombre por `aria-label`.
- **Un calendario que no se pudo leer queda marcado en la leyenda** con «⚠» y fondo de
  error (`brokenCalendars()`). ⚠️ **Depende del texto exacto «No pude leer el calendario
  X.»** que arma `board.py`: si cambia, la marca desaparece sin que nada falle.

- **Cada evento es un bloque** (`display: "block"`, también los de hora) con la clase `ev`
  y su color en `--ev`, que `eventDidMount` le pasa: fondo suave con `color-mix()` y un
  borde del color pleno. ⚠️ Sin `color-mix()` el fondo cae a `--card-2` y el color queda
  solo en el borde: es el respaldo de `@supports`, no una falla.
- **«Nuevo aviso» es un botón flotante**, que aparece solo si la pantalla escribe. El
  formulario y el detalle abren en un panel desde abajo (centrado en pantalla ancha) y se
  cierran tocando afuera.
- **Lo que pasó se avisa con un toast** que se va solo, no con `alert()`. ⚠️ **Borrar sigue
  pidiendo `confirm()`**: es un toque sin deshacer y borra la serie entera.

**Temas.** Los colores son variables en `:root` de `app.css`, una sola hoja para todas las
páginas. Los tres temas —claro, oscuro y noche— declaran los mismos tokens, y `test_app.py`
lo sostiene.

- **Tokens compartidos**: `--space-1` a `--space-5` (cuatro a veinticuatro píxeles), `--tap`
  (44 px, el mínimo táctil de botones, campos y selects), `--on-accent` (el texto sobre el
  acento lleno), `--accent-ink` (el texto sobre el acento suave), `--faint` (lo vacío y lo
  tachado) y `--danger`.
- 🔴 **Contraste medido**: en claro y oscuro, `--on-accent` sobre `--accent` y `--accent-ink`
  sobre `--accent-soft` dan al menos 4,5; en los tres temas, `--faint` sobre `--card` da al
  menos 3. Hay test que lo calcula. ⚠️ En el tema noche `--on-accent` sobre `--accent` da 3,9:
  ese tema es el del kiosco de noche, sin botones que se usen.
- **El foco siempre se ve**: `:focus-visible` con borde de tres píxeles y `:focus` de
  respaldo para el navegador que no conoce `:focus-visible`. Hace falta en la tele, donde se
  navega con el control remoto.
- **Tres niveles de botón**: `.btn.primary` (acento lleno, `--on-accent`), `.btn.secondary`
  (acento suave, `--accent-ink`) y `.btn.danger` (texto rojo, sin fondo). `.ghost`, la
  píldora, es solo para los enlaces de la barra; un enlace que hace de acción va como
  `.btn.secondary`.
- **El kiosco y la alarma miden en `vh`; el control y la agenda, en píxeles.** Lo primero se
  mira de lejos y escala con la pantalla; lo segundo se lee de cerca y no cambia de tamaño
  con el alto de la ventana. Hay test de las dos cosas.
- ⚠️ **Sin `:has()`, `aspect-ratio`, `subgrid` ni container queries**: no andan en el
  navegador viejo de un dispositivo reciclado ni en el receptor de Cast. `min()` se usa solo
  con un valor de respaldo antes, como la hora de la alarma.

- **Claro u oscuro según el dispositivo**, con `prefers-color-scheme`. Las páginas declaran
  `<meta name="color-scheme" content="light dark">` para que los controles del formulario
  cambien también, y **FullCalendar recibe los colores por sus `--fc-*`**: con sus defaults
  sería un calendario claro adentro de una página oscura.
- 🔴 **El descanso del kiosco va por encima del tema del dispositivo**: `kiosk.js` pone
  `data-theme="night"` en `<html>` y `:root[data-theme="night"]` gana sobre los dos: en
  descanso se oscurece aunque el dispositivo esté en tema claro.

**El kiosco** (`kiosk.js`) pide `/api/board` cada sesenta segundos y lo arma en tarjetas:
reloj, clima, «Lo próximo», «Hoy», la idea del menú y las dos listas. Apaisado en tres
columnas; vertical, en dos.

- **En tablet o tele de 720 líneas** (apaisado de hasta 1100 px de ancho u 800 de alto) las
  dos listas van lado a lado debajo de la fila de arriba, para que no se corten abajo. Las
  listas se reparten el alto que queda con `minmax(0, 1fr)`.
- **Por debajo de 600 px el kiosco se desplaza** en una sola columna en vez de apretar las
  tarjetas, y el enlace de la esquina deja de ser fijo.

- 🔴 **El reloj corre con la hora del servidor.** Calcula el offset entre `now` y el punto
  medio de la ida y vuelta, así un dispositivo con la hora mal igual muestra la de la casa.
- **Se pone en tema nocturno en descanso**, con `quiet`, que es `Hush.is_quiet()`: el
  horario fijo, el silencio pedido y las vacaciones.
- **En vacaciones, el reloj lleva la leyenda «De vacaciones hasta el 25/10»**, con la hora si
  no es medianoche. `/api/board` trae `away`, la vuelta en ISO sin zona, o `null`.
- **El clima trae un ícono por código WMO** (`board.sky_icon`); lo que no figura en
  `SKY_ICONS` es cielo variable.
- **«Lo próximo» es lo primero con hora que todavía no empezó, de hoy o de mañana**
  (`Board._next`). Lo de todo el día nunca entra: no tiene un «en cuánto». Sin nada, dice
  «Nada más por hoy». Cuánto falta se recalcula con el reloj, no con el polling.
- 🔴 **«Hoy» es una línea de tiempo con una marca «ahora», y de lo pasado quedan solo los
  dos últimos** (`KEEP_PAST`). La tarjeta no scrollea: con todo lo pasado a la vista, lo
  que viene, que es lo que se mira, quedaría afuera. Cada entrada de `today` trae
  `label` —el ícono del tipo y el mensaje—, `mark`, cómo terminó, que se muestra solo si
  ya pasó, y `for`, que suma «· para <nombre>» (`todayLabel()`). «Lo próximo» lo trae en el
  título del evento.
- **Cada tarjeta de lista lleva un contador** de lo que tiene; **el de «Hoy» cuenta lo que
  queda**, sin lo que ya pasó (`leftToday()`).
- **La tarjeta «🍽 Idea para hoy» (o «para mañana») muestra los platos del día de la próxima
  comida** (`#meal-card`). `/api/board` trae `meal` como `{day, tomorrow, items}`, cada ítem
  `{meal, label, dish, state}`, armado por `Board._meal()` sobre `meals.upcoming()`: hasta
  las quince es hoy con el almuerzo `next` y la cena `later`; de quince a veintidós, hoy con
  el almuerzo `past` y la cena `next`; desde las veintidós, mañana. La fila `next` va en
  negrita y la `past`, atenuada. Ver **Menú semanal**, en `.claude/rules/consultas.md`.
  - **Solo las comidas servidas**: `Board` recibe `served`, las de `MENU_LUNCH_AT` y
    `MENU_DINNER_AT` que no están en `off`. Una comida sin plato guardado no aparece.
  - **Sin menú, sin `MealStore` o sin platos, `meal` es `null`** y la tarjeta queda oculta
    con la grilla de siempre: la grilla con la tarjeta vive en `.board.has-meal`, que
    `kiosk.js` pone y saca. Apaisada va a la derecha, arriba de las listas; vertical, abajo
    del clima y «Lo próximo».
  - **Es solo lectura**: `mealView()` es pura, todo va por `textContent` y no hay botones,
    así que `?ver=1` la muestra igual.
  - ⚠️ **La grilla con la tarjeta se probó en Chromium headless**, apaisada y vertical, no en
    las teles.
- ⚠️ **`app.js`, `kiosk.js`, `alarm.js` y `control.js` van en ES5** —`var` y `function`, sin flechas, `const`,
  template strings ni `?.`— para andar en el navegador viejo de un dispositivo reciclado. Sí
  necesitan `fetch`. Hay test que busca esa sintaxis, y `innerHTML`, en los cuatro.
- **La lógica pura de los scripts se prueba con node.** Cada uno exporta sus funciones
  sin DOM por `module.exports` cuando corre fuera del navegador; `tests/web/agenda_logic.js`,
  `kiosk_logic.js`, `alarm_logic.js` y `control_logic.js` las ejercitan y `test_agenda_js.py` los corre. ⚠️ **Sin `node` en la
  máquina, ese test se saltea**: no falla.
- **Pantalla completa al primer toque**: el navegador solo la concede desde un gesto. Que la
  pantalla no se apague y el cargador son cosa del dispositivo.
- Sin conexión dice "Sin conexión con la casa." y deja lo último que mostró.
- **Cada ítem de las listas trae un círculo para tacharlo**, solo si `/api/people` dice que la
  pantalla escribe. Tacha por id, como el botón del chat, así que un toque no se lleva otro
  ítem. Tachar no avisa a los chats.
- **Cada tarjeta de lista trae un campo para agregar**, con la misma condición. Se parte por
  comas y por «y», como `/agregar`, y un repetido no entra. Agregar tampoco avisa a los
  chats, decisión del dueño: es una lista, no un aviso. ⚠️ El campo lleva el teclado del
  dispositivo: en uno sin teclado en pantalla no sirve.
- 🔴 **Con `?ver=1` el kiosco es solo lectura**: `kiosk.js` le pone la clase `read-only` al
  `body`, que esconde los campos, los círculos y el enlace a `/control` de la esquina, y no
  consulta `/api/people`. Es lo único que se castea: en la tele no hay con qué tocar.

**Escribir desde la pantalla.** `/agenda` crea, edita y borra avisos de la casa con un
formulario; `JobsService` (`web/jobs.py`) es la lógica y no sabe de HTTP.

- **Se crea tocando un día o con «Nuevo aviso».** Un día del mes abre a las ocho; una hora
  que ya pasó se corre a la próxima hora en punto.
- **Solo se edita o borra lo de la casa que todavía no sonó.** Lo que sonó sale del
  historial y no trae `job`; **Google es solo lectura**.
- **Editar un aviso que repite edita la serie**, y borrarlo la borra entera. No hay "solo
  esta vez".
- **«Todos los meses» toma el día de la fecha elegida**: el formulario no tiene un campo para
  el día del mes. Qué repetición admite cada tipo lo decide `repeatRule()` de `app.js`, que se
  prueba con node. **Editar un mensual conserva su día** si la fecha es justo donde ese día
  cae en el mes: un 31 que se muestra el 28 de febrero sigue siendo 31 (`jobs._monthday()`).
- **El autor se elige en «A nombre de»**: las personas del padrón, con «(sin Telegram)» a la
  que no tiene chat, y con el padrón vacío, los chats de `ALLOWED_CHAT_IDS`. El POST manda
  `author_id` (persona) o `author` (chat); los dos juntos son un 400. Un chat de la casa
  guarda también su persona, si tiene. **No cambia al editar**: `Store.update` conserva el id
  y el dueño. El chat es a nombre de quien queda en `/lista` y de quien puede `/cancelar`
  escrito.
- ⚠️ **Una persona sin Telegram deja el aviso en el chat `NO_CHAT`** (cero, que ningún chat
  real es) con su `author_id`. Suena igual, porque los destinatarios salen de
  `ALLOWED_CHAT_IDS` y de la asignación, pero no está en el `/lista` de nadie ni se cancela
  escribiendo: se borra desde la pantalla o con el «Cancelar #N» del aviso.
- **«Para» asigna el aviso**: «Nadie», «Todos» y cada persona del padrón; nuevo, arranca en
  «Nadie». Viaja como `assignee` (`none`, `all`, `person`) y `assignee_id`
  (`JobsService._assignee()`): un valor que no existe, un id con algo que no sea `person` o
  una persona que no está en el padrón son un 400. **Un PUT sin `assignee` no la toca.** Qué
  hace al sonar está en **Para quién suena**, en `.claude/rules/programado.md`.
- **`/api/jobs` devuelve `author`, `author_id`, `author_name`, `assignee`, `assignee_id` y
  `assignee_name`.** El nombre del autor es el de la persona, o el que el chat muestra en
  Telegram si no tiene; `assignee_name` es `None` salvo para una persona que sigue en el
  padrón.
- 🔴 **Sin `ALLOWED_CHAT_IDS` la pantalla no escribe**: no hay a nombre de quién poner un
  aviso. Las escrituras contestan 403, y el formulario y los ✓ no aparecen.
- **El nombre de cada chat sale de `PeopleStore`**: `main._meet()`, después de `_knock()`,
  anota el nombre visible de quien le escribe al bot (nombre y apellido, o el @usuario).
  Solo de chats permitidos, y uno vacío no pisa al que había. Hasta que escribe, es
  «Chat <id>». Anotarlo no puede costar la respuesta.
- 🔴 **`schedule/spec.py` es la única fuente de las reglas de lo programado**, para Telegram y
  para la web: qué tipo y repetición es cada cosa (un timer suena una vez, un recordatorio
  repite, uno semanal necesita días y uno mensual, el día del mes) y cuándo suena por primera vez. Es la misma lección que
  `next_run()` y `down_line()`: con dos copias, la pantalla acepta lo que el chat rechaza.
- **`Reminders.update` guarda antes de desagendar.** Una edición inválida levanta en el
  `Store` y el aviso sigue con su timer. No toca lo que ya sonó y espera su «Hecho», ni su
  re-aviso.
- **Cada alta, cambio o baja se avisa a todos los chats** con «🖥️ … desde la pantalla» y el
  aviso en una línea, que suma «· para <nombre>» si es de alguien o de todos; el alta lleva
  el nombre del autor. Va en un hilo aparte: un chat que
  falla no frena a los otros ni a la respuesta.
- 🔴 **El «Cancelar #N» de ese aviso manda `borrar <id>`, no `cancelar`.** `borrar` es solo un
  botón, en `Commands.press()` y no en `_dispatch()`, así el router no lo nombra. Borra
  desde **cualquier** chat, porque el aviso le llegó a todos, y avisa a los demás «🗑 <nombre>
  borró #N». `/cancelar` escrito y el «Cancelar #N» de `/timer` y `/alarma` siguen siendo
  del dueño.
- 🔴 **Una escritura exige `application/json` y, si trae `Origin`, que coincida con `Host`**
  (`_refuse_write`); si no, 415 o 403. Ese content-type obliga al navegador a un preflight
  CORS, y la casa no contesta CORS: un sitio externo abierto en un navegador de la casa no
  puede escribir. ⚠️ **Aceptar otro content-type (un form, `text/plain`) saca esa protección
  sin que nada avise.** No cubre DNS rebinding ni un `curl` desde la LAN: la LAN es de
  confianza. `/api/command` pasa por la misma guarda.
- Un método que la ruta no acepta es un 405 con `Allow`. El mensaje tiene tope de quinientos
  caracteres, como `/say`.

**FullCalendar 6.1.21 va vendorizado** en `static/fullcalendar-6.1.21/`, licencia MIT con su
`LICENSE.md` al lado, **sin CDN**: la pantalla no depende de internet ni de un tercero. La
ruta lleva la versión y el bundle sale con `Cache-Control: immutable`; lo propio, con
`no-cache`. Solo se sirve lo que está en `app.STATIC`. Para re-vendorizar, verificar el
sha512 de cada paquete contra `dist.integrity` antes de copiar:

```bash
npm pack fullcalendar@6.1.21 @fullcalendar/core@6.1.21
npm view fullcalendar@6.1.21 dist.integrity          # = sha512 del .tgz
openssl dgst -sha512 -binary fullcalendar-6.1.21.tgz | base64 -w0
# fullcalendar: index.global.min.js y LICENSE.md
# @fullcalendar/core: locales/es.global.min.js → es.global.min.js
```

Otra versión cambia el nombre de la carpeta, `FULLCALENDAR` en `app.py` y los `<script>` de
`agenda.html`.

- ⚠️ **Un job vencido mientras el servicio estaba caído no aparece hasta que suena.** La
  expansión arranca en `now`, y ese job tiene la hora en el pasado.
- ⚠️ **Un recordatorio pospuesto se ve como timer**: posponer crea un job de una sola vez
  con `kind=reminder`, y uno de una sola vez es un timer para la pantalla.
- ⚠️ **Lo que sonó antes del historial no está.** Lo anterior al 2026-10-05 se ve vacío de
  pasado.
- **Los feriados son eventos de día completo**, de solo lectura, con `source: "feriado"` y
  su color; el detalle dice «Feriado nacional» y el «Hoy» del kiosco lo muestra. Salen de la caché local, no de la red, y una
  caché que no contesta deja la agenda sin feriados, no en error.
- **Lo que un feriado va a saltear se marca «🏖 feriado, no suena»**, con el mismo
  `spec.skips()` que decide al sonar; ya pasado, «🏖 feriado», y no cuenta como «no sonó».
  «Lo próximo» del kiosco lo saltea.
- **La casilla «No suena en feriados» aparece solo con «Algunos días»**, y el formulario
  manda `skip_holidays` en falso con cualquier otra repetición (`skipsHolidays()`).

## App de la tele

`WebApp._app()` sirve el APK de la tele en `GET /app/tele.apk` y su versión en
`GET /app/tele.json`, con `AppShelf` (`web/apk.py`) leyendo de `$STATE_DIRECTORY/app`
(`/var/lib/domotica/app/`). Vive en
`WebApp`, así que **existe solo si la API arrancó**, o sea con `API_TOKEN`.

- 🔴 **Nombres fijos y lista cerrada**: `apk.FILES` tiene `tele.apk` y `tele.json`, y cada uno
  tiene en `APP_FILES` (`web/app.py`) su tipo, si es descarga y su 404. Un nombre fuera de la
  lista es un 404 «no existe» **sin tocar el disco**: no hay listado del directorio ni path
  traversal. Un archivo nuevo en `/app/` se suma a las dos.
- **Se lee del disco en cada pedido**: un APK nuevo se baja sin reiniciar el servicio.
- Los dos salen con `Cache-Control: no-store`. El APK, como descarga
  (`Content-Disposition: attachment`); `tele.json`, como `application/json` y sin attachment.
- Sin el archivo, 404 con su mensaje: «Todavía no hay app de la tele en la casa.» o «Todavía no
  hay versión de la app de la tele en la casa.». Otro método que no sea `GET` es un 405 con
  `Allow: GET`; un error al leer que no sea «no existe» es un 500 y se loguea.
- **`tele.json` es el contrato con la app**: `{"version_code", "version_name", "sha256",
  "size"}`, del APK publicado. Lo arma `deploy/tele-version.sh` leyendo el APK con `aapt2` en la
  imagen `domotica-tele-build`, sin red; sin esa imagen falla y pide correr antes
  `android/tele/build.sh`. Rechaza un `versionName` fuera de `^[A-Za-z0-9._+-]{1,40}$` y un
  `versionCode` que no sea un entero: el JSON se escribe sin escapar.
- ⚠️ **No hay `HEAD`**: `api._Handler` no lo atiende y `http.server` contesta 501. Se agrega
  solo si Downloader lo necesita.
- **Los archivos son `root:root` 644 y `deploy/deploy.sh` no los toca.** Los sube
  `deploy/push-apk.sh`, que genera `tele.json` antes de copiar nada, instala los dos como
  `.tmp` y los reemplaza con un `mv` atómico cada uno, sin reiniciar: una descarga en curso
  nunca ve un APK a medias.
- 🔴 **Primero el APK y después `tele.json`.** Es orden obligatorio: la versión anunciada nunca
  apunta a un APK viejo. Al revés, una tele que pregunta entre los dos `mv` ve una versión
  que el APK servido todavía no es.
- La app se firma con una clave de release fija, así que una versión nueva instala encima. Ver
  **La app Android**, en `.claude/rules/app-tele.md`.
- El registro y el latido de la app están en **Registro en el CT**, y las órdenes en **Órdenes**,
  los dos en `.claude/rules/app-tele.md`.

## Control desde la web

`/control` maneja la casa sin Telegram: apagar una alarma, marcar «Hecho», posponer,
confirmar una caída y cualquier comando. `ControlService` (`web/control.py`) es la lógica y no
sabe de HTTP; `WebApp._control()` la rutea.

- 🔴 **Es un segundo transporte de `Commands`, no una copia.** Un botón va por
  `Commands.press()` y lo escrito por `Commands.free_text()`, los dos con `with_actions()`:
  las reglas de cada comando, del router y de los botones siguen siendo las de
  `.claude/rules/router-y-conversacion.md`. Lo que no existe en Telegram no existe acá.
- **Todo `_dispatch()` y los botones de solo-botón (`hecho`, `callar`, `confirmar`, `borrar`)
  desde el día uno**, decisión del dueño. La respuesta vuelve con sus botones como
  `[{label, data}]`, y tocarlos vuelve a `/api/command`.
- 🔴 **Un texto que arranca con «/» va a `press()` sin la barra solo si `Commands.typed()` lo
  acepta**: `ayuda` o un comando de `_dispatch()`, con el nombre pasado a minúsculas
  (`ControlService._typed()`). Lo demás sigue en `free_text()`: los de solo-botón escritos
  (`/hecho 3`, `/callar`, `/borrar`, `/confirmar`), los nombres que no existen y los alias que
  viven en `main.py` y no en `_dispatch()` (`/tiempo`, `/llama`, `/siesta`, `/stop`,
  `/volume`, `/pregunta`, `/convertir`, `/donde`, `/start`, `/help`), que los toma el router.
- **Se elige quién sos en la tarjeta «¿Quién sos?»**, un botón por opción de `/api/people`:
  las personas del padrón, y con el padrón vacío, los chats de `ALLOWED_CHAT_IDS`. Una persona
  sin chat sale «(sin Telegram)». La elección queda en el `localStorage` del dispositivo como
  `p:<id>` o `c:<chat>`; una vieja, solo el número de chat, pasa a la persona de ese chat.
- 🔴 **Sin elección guardada que siga valiendo, la página no elige por nadie**: `pickWho()`
  devuelve `null` y se ve solo «¿Quién sos?». Antes caía en la primera opción, y un
  dispositivo nuevo manejaba la casa a nombre de quien encabezara la lista. Elegido, arriba
  dice «<nombre> · cambiar», y «cambiar» vuelve a preguntar.
- **`?soy=<id>` elige a esa persona y la guarda** (`whoFromQuery()`), y pisa lo guardado: es
  el enlace de cada persona. Un id que no está en el padrón, o un chat, no elige nada.
- **`/api/live` trae `can_command`**: si quien llama tiene chat. Con `false` la página esconde
  todo lo `.needs-chat` —texto libre, ejemplos, «A mano», paneles, «Más» y «Ajustes»— y
  muestra «Ahora» con «Desde acá podés apagar una alarma y marcar «Hecho». Para lo demás,
  pedíselo a Papá o Mamá.». 🔴 **Esconder no es la defensa**: el 403 de `/api/command` sigue
  siéndolo.
- **`ControlService._caller()` resuelve a nombre de quién se corre.** `chat_id` y `person_id`
  juntos es un 400. Sin `ALLOWED_CHAT_IDS`, con un chat fuera de la lista o con una persona que
  no existe, `/api/live` y `/api/command` contestan 403 «Elegí quién sos.». Una persona con
  chat corre como ese chat.
- 🔴 **El `who` es «<persona> (pantalla)»**, decisión del dueño: los avisos a los demás chats
  dicen que vino de la web. Un chat sin persona en el padrón firma con el nombre visto en
  Telegram (`PeopleStore`).
- 🔴 **Una persona sin Telegram solo apaga una alarma o marca «Hecho»**
  (`Commands.press_without_chat()`, `CHATLESS_BUTTONS`). Cualquier otro botón o texto es un
  403 que lo explica. Como no hay chat que lo tocó, **el aviso de que apagó o marcó hecho
  llega a todos los chats del aviso**. Su `/api/live` no trae posponer, ni «Confirmar», ni el botón de
  silencio.
- **Comparte el estado con Telegram por `chat_id`**: el `PendingStore` —una pregunta hecha en
  el chat se puede contestar desde la web y al revés— y el equipo de `usar`. Una persona sin
  chat no tiene ninguno de los dos.
- 🔴 **Un error del comando se contesta con el motivo**, como en Telegram:
  «🔴 No pude procesar la solicitud: <qué pasó>», con 200 y sin botones. Un error de la
  pantalla misma es un 500 genérico.
- 🔴 **El `fetch` de `/api/command` no se corta por tiempo.** Un comando puede tardar un minuto
  —una pregunta con búsqueda, un anuncio largo—, y cortarlo antes mostraría un error de algo
  que sí corrió. Mientras espera muestra «⏳ Procesando…» y deshabilita los botones.
- **`/api/live` se pide cada cinco segundos** y después de cada comando. Trae lo que suena
  (`RingingStore`), lo que espera «Hecho» (`AwaitingStore.all()`), lo que se puede posponer,
  las caídas sin confirmar, el silencio y el estado de cada chequeo. Lo que suena, lo que
  espera y lo que se puede posponer traen `for`, de la foto de lo que sonó, y lo urgente lo
  muestra como «· para <nombre>».
- **Lo que espera «Hecho» se filtra a un día** (`awaiting.KEEP`), igual que se poda al sonar
  otro: si no, un recordatorio de hace una semana seguiría pidiendo atención.
- 🔴 **Posponer aparece solo pegado a lo último que sonó en ese chat**, dentro de
  `SNOOZE_WINDOW`. `/posponer` pospone por chat, no por id: un botón al lado de otra cosa
  pospondría lo que no es.
- **«Confirmar» solo si el chat elegido es de `ALERT_CHAT_IDS`**, que es a quien
  `Monitor.acknowledge()` deja confirmar. La caída se ve igual para todos.
- **La respuesta se lleva a la vista** (`scrollIntoView`) al mandar y al contestar: en el
  celular quedaba abajo de los paneles, fuera de la pantalla.
- **El texto libre tiene ejemplos tocables** (`data-example`) y la ayuda «Escribilo como se lo
  dirías a alguien.». Tocar un ejemplo lo copia al campo **sin mandarlo**.
- **«A mano» (`#quick`) junta lo de todos los días**: «Compras», «➕ Nuevo aviso» (un enlace
  a `/agenda?nuevo=1`), Timer, «Agregar a compras», «🤫 Silencio» y «Decir» con los chips de
  equipos. El timer arma `timer <N>m <qué>` (`timerCommand()`): sin minutos enteros mayores a
  cero no se manda. «Silencio» vacío dice cómo está la casa.
- **El panel «🛒 Listas» tiene «Menú»** al lado de «Compras» y «Pendientes»: corre `menu`
  como `/menu` en Telegram, con sus botones. Ver **Menú semanal**, en `.claude/rules/consultas.md`.
- **Los paneles van en tres columnas armadas a mano** (`.panel-col`): Casa y Programado;
  Consultas; Listas. Cada columna apila sus tarjetas sin estirarlas al alto de la vecina. Cada
  fila campo y botón es una grilla, y por debajo de 400 px el botón baja a lo ancho.
- **Lo de menos uso va plegado en `<details>`**: «Más» —Equipo de siempre, Equipos, Volumen,
  Pantalla, Turnos, Pastillas, Calcular y Traducir— y, al final, «⚙️ Ajustes de la casa» con
  «🧹 Depurar» y «👪 Personas». Las etiquetas dicen qué hacen: «Cortar lo que suena»
  (`parar`), «Apagar el equipo» (`apagar`), «Equipo de siempre» (`usar`).
- 🔴 **«Pastillas» y «Turnos» son un solo formulario cada uno, sin `data-need`**: vacío
  consulta (`pastillas`, `turnos`), con texto carga. `formCommand()` decide; sin dato
  obligatorio vacío devuelve `null` y no se manda nada.
- **Lo que explica un campo va en un `.hint` visible abajo**, no en `title`: en el celular y
  en la tele un `title` no se ve nunca. El placeholder queda corto.
- **«Ahora» se compacta en calma** (`isCalm()`): si lo único es el silencio, la tarjeta pasa
  a una fila y el título dice «Todo en orden» (`calmTitle()`). El estado de los chequeos va
  plegado en «Chequeos de la casa», y sin chequeos no se muestra.
- **El orden de «Ahora» es por tipo**: sonando, espera «Hecho», posponer, caídas y silencio.
  Dentro de cada tipo, lo que es para la persona elegida va primero (`mineFirst()`, por el
  `for`); el orden de los tipos no cambia.
- **Los equipos de «A mano» son chips con estado**: el tildado se marca con la clase `on`, y
  valen para todo comando con `data-target`, también los de «Casa» y «Más».
- **En «👪 Personas», un chat que todavía no le escribió al bot se lista «Todavía no escribió
  (·NNNN)»**, con los últimos cuatro dígitos (`chatLabel()`). Borrar es un botón de peligro.
- **«⚙️ Ajustes de la casa» tiene «🧹 Depurar»**: corre `depurar`, el mismo comando, con sus
  botones. Se ve para todo el que tiene chat; quién puede usarlo lo decide `Commands`, no la
  página. Ver `.claude/rules/depurador.md`.
- **Un solo botón de silencio, según el estado**: «Cortar vacaciones» en vacaciones, «Hablar
  ya» con un silencio pedido y si no «Silenciar 1 h».
- 🔴 **`/api/live` no manda el `detail` de los chequeos**, solo nombre y si está arriba: el
  detalle puede traer URLs. `estado` corrido por `/api/command` sí lo trae, como en Telegram.
- ⚠️ **No hay chequeo de `Host` contra DNS rebinding**, decisión del dueño. Un sitio externo
  que lo consiga en un navegador de la casa puede hacer hablar la casa, activar vacaciones o
  correr cualquier comando a nombre de cualquier chat. Es el mismo agujero de las escrituras
  de la agenda, con más alcance.
- **Manifest e íconos para «Agregar a pantalla de inicio»**, sobre http y **sin service
  worker**: una PWA instalable de verdad y el micrófono piden HTTPS, y la casa sirve http.
  Después de elegir, al pie, la página dice cómo: «⋮ → Agregar a pantalla principal».
- **Se llega desde `/agenda` y `/pantalla`, o por `/` a secas**, que redirige; el enlace del kiosco se esconde con `?ver=1`, y
  lo que se castea sigue siendo `/pantalla?ver=1`.
- ⚠️ **La parte DOM de `control.js` no tiene test automático.** `control_logic.js` cubre la
  lógica pura —el comando con los equipos, a quién elegir y `?soy=`, el timer, el cuerpo del
  POST, el orden de lo urgente y su título—; lo demás se prueba a mano en el navegador, o con las capturas.

**Capturas de la web.** `deploy/capture-ui.sh` saca las páginas con un Chrome o Chromium
headless, en cinco tamaños (celular, tablet, PC, tele 1080p y tele 720p), en tema claro y
oscuro, y las largas enteras. Solo hace GET: no escribe nada en la casa. Uso y variables en
**Desarrollo**, en el `README.md`.

## Padrón de la casa

`people.Household` sobre `PersonStore` (tabla `persons`) es quién vive en la casa, tenga o no
Telegram. `PeopleStore` (`people`) sigue siendo otra cosa: el nombre que el chat muestra en
Telegram. Se carga desde la tarjeta «👪 Personas», en «⚙️ Ajustes de la casa» de `/control`.

- **Escribir exige pantalla escribible**: `POST /api/persons` y `PUT`/`DELETE
  /api/persons/<id>` pasan por `_refuse_write` y sin `ALLOWED_CHAT_IDS` son 403. Otro método es
  405; un nombre o chat que no vale, 400 con el motivo; una persona que no existe, 404. Sin
  `JobsService`, `/api/persons` es 404. La tarjeta aparece solo si la pantalla escribe.
- 🔴 **El nombre se tiene que poder decir**: `SAYABLE_NAME`, ahora en `people.py` y compartido
  con `/turnos` —letras y espacios, sin dígitos ni guiones—, hasta cuarenta caracteres
  (`MAX_NAME`) y con los espacios ordenados.
- **Único sin distinguir mayúsculas**: se compara con `casefold()`. ⚠️ Los acentos sí
  distinguen: «José» y «Jose» entran los dos. «todos» y «nadie» están reservados (`RESERVED`).
- **El chat tiene que ser de `ALLOWED_CHAT_IDS` y no de otra persona.** Sin chat es «sin
  Telegram». El desplegable ofrece solo los chats libres y el propio.
- **Un chat que salió de `ALLOWED_CHAT_IDS` cuenta como sin Telegram** (`Household._live()`):
  la fila lo guarda, pero no se usa.
- **El id es estable**: renombrar o cambiar el chat no lo cambia, así que lo guardado en un
  dispositivo sigue apuntando a la misma persona.
- **Con el padrón vacío, todo cae a los chats**, como antes de que existiera.
- **Altas, cambios y bajas no avisan a los chats.**
- 🔴 **La baja pasa los avisos asignados a esa persona a «nadie»** antes de borrarla
  (`before_remove` → `Store.reassign()`); si eso falla, no se borra. Ver **Para quién suena**,
  en `.claude/rules/programado.md`.
- **La pantalla asigna y muestra para quién es cada aviso**: ver **Escribir desde la
  pantalla**.
