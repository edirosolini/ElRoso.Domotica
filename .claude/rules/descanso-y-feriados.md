---
paths:
  - "src/homeauto/quiet.py"
  - "src/homeauto/holidays.py"
  - "src/homeauto/main.py"
  - "tests/test_quiet.py"
  - "tests/test_hush.py"
  - "tests/test_holidays.py"
  - "tests/schedule/test_holiday_skip.py"
  - "tests/bot/test_quiet_behaviour.py"
  - "tests/bot/test_silence_command.py"
  - "tests/bot/test_vacation_command.py"
---

# Descanso, vacaciones y feriados

## Horario de descanso

Entre `QUIET_FROM` y `QUIET_TO` **nada se dice en voz alta**: el aviso va solo a Telegram,
con el motivo. Aplica a las alarmas y también a `/decir` y `/clima` manuales. El default del
código es de 23:00 a 07:00; ⚠️ **el CT corre de 22:00 a 05:25**, y lo que manda es el env —
ver **Dónde corre**, en `CLAUDE.md`.

La decisión de incluir los comandos manuales es deliberada: la regla existe para no despertar
a nadie, y quien escribe a las 3 AM está despierto pero el resto de la casa no. Si alguna vez
hace falta una excepción por mensaje, cuidado con la palabra clave elegida: `en <equipo>` ya
enseñó que un prefijo que también puede ser texto real se come parte del mensaje.

`/silencio 2h` agrega una ventana **a pedido** encima de la fija, para una siesta o una
reunión. `quiet.Hush` la implementa.

- 🔴 **`Hush` tiene la misma forma que `QuietHours`.** Contesta `is_quiet()` y `reason()`, así
  que el anunciador, los comandos, la API y `HouseVoice` siguen consultando lo mismo sin
  enterarse de que ahora el silencio se puede mover. `main()` construye un solo `Hush` y lo
  pasa donde antes iban las `QuietHours` sueltas.
- **`reason()` es el único texto del motivo**: «Horario de descanso (22:00–05:25)» o «De
  vacaciones hasta el 25/10». `Announcer`, `Commands` y `HouseVoice` le suman su cola
  —«: no lo dije en voz alta.», «: no se dijo en voz alta.»— por `quiet.reason_of()`, que
  también acepta unas `QuietHours` sueltas.
- **El silencio se guarda en SQLite, no en memoria.** Un reinicio en medio de la siesta
  devolvería la casa hablando.
- **Vence solo**: al consultarlo pasada la hora, `until()` lo borra. Nadie aguas abajo tiene
  que chequear dos cosas.
- Los comandos verifican con `isinstance` que haya un `Hush` de verdad: con unas `QuietHours`
  sueltas no hay nada que mover y contestan que no está configurado, en vez de reventar.
- **En descanso la tele no se prende sola**: ni la vista de alarma ni el kiosco después de un
  anuncio. `/pantalla` a pedido sí, porque mostrar no hace ruido. Ver **Pantalla en la TV**, en `.claude/rules/pantalla-tv.md`.
- **En descanso, silencio o vacaciones el `poll` de la app de la tele no trae recordatorios**:
  `TeleService` le pregunta a `Hush.is_quiet()`. Ver **Registro en el CT**, en `.claude/rules/app-tele.md`.

### Modo vacaciones

`/vacaciones hasta 25/10` calla la casa hasta la vuelta: nada sale por los parlantes y todo
llega por el chat. `/vacaciones off` las corta; sin argumento, o sin una fecha que se pueda
leer, contesta cómo están y cómo se usa.

- 🔴 **Es la única excepción a «lo urgente pasa por encima».** En vacaciones también lo
  urgente queda solo escrito, con sus botones. Abarca `HouseVoice` —el monitor— y la API
  `/say` con `urgent`.
- 🔴 **Su propia tabla, `away` (`AwayStore`), separada de `hush`.** Compartida, `/hablar` —que
  borra el silencio pedido— cortaría las vacaciones sin que nadie lo pidiera.
- **`Hush.is_quiet()` da verdadero en vacaciones**, así que todo lo que ya consultaba el
  silencio se entera solo. `is_away()` **vence el modo al leerlo**, como `until()`.
- **La fecha es `dd/mm`, con hora opcional** (`timespec.parse_return_date`); sin hora es a
  las 00:00, y `/vacaciones 25/10` sin el «hasta» también sirve. Una fecha que ya pasó este
  año es la del siguiente. Hoy o antes se rechaza.
- **`quiet.Vacation` arranca, corta y avisa el final.** El timer `away-end` escribe a todos
  «🧳 Terminó el modo vacaciones, vuelvo a hablar.». `start()` lo rearma al arrancar y, si
  las vacaciones vencieron con el servicio caído, avisa ahí. Si se extendieron, el timer viejo
  no dice nada.
- **Activarlas o cortarlas avisa a los demás chats** con el nombre de quien lo hizo («🧳
  <nombre> activó vacaciones hasta el 25/10»). El nombre sale de `main._who()`, que ahora
  llega también a los comandos escritos y al texto libre; en una nota de voz queda «Alguien».
- 🔴 **Activarlas corta las alarmas que estén sonando** (`Reminders.stop_all_ringing`), con
  el historial abierto, como el tope. Durante las vacaciones **una alarma no repite** y sale
  sin «🔕 Apagar»: no hay nada que apagar.
- **`/decir`, `/llamar` y lo pedido «por el parlante» se niegan** con el motivo y la pista
  `/vacaciones off`. `/pantalla` tampoco prende la tele. `/apagar`, `/parar` y `/volumen` siguen andando: no hablan. El resumen,
  el cierre, el clima y la agenda salen solo por chat, como en descanso. El aviso del menú
  antes de cada comida no sale: ver **Menú semanal**, en `.claude/rules/consultas.md`.
- ⚠️ **Todo camino nuevo que castee tiene que preguntarle a `Hush`**, o se saltea las
  vacaciones sin que nada avise. Hoy se cumple: la pantalla en la tele le pregunta por
  `ScreenPages` y `/pantalla` por `away_of()`. Ver **Pantalla en la TV**, en `.claude/rules/pantalla-tv.md`.

## Feriados

`holidays.py` trae los feriados nacionales de argentinadatos (`/v1/feriados/{año}`) y los
guarda en la tabla `holidays`. Lo que repite por días de la semana puede no sonar ese día.

- **Se refresca a los quince segundos de arrancar y todos los días a las 04:00**
  (`main.schedule_holidays()`, fuera del event loop). Desde noviembre (`NEXT_YEAR_FROM`)
  trae también el año siguiente. Cada año se reemplaza entero, en una transacción.
- 🔴 **Un pedido que falla, o que vuelve vacío, deja la caché como estaba.** Sin datos nunca
  —un despliegue nuevo antes del primer refresco—, todo suena.
- 🔴 **Solo saltean `inamovible` y `trasladable`.** El `puente` suena: es no laborable, no
  feriado, y el resumen lo nombra «día no laborable».
- **`skip_holidays` es una columna de `jobs`** y solo vale con repetición `weekly`:
  `Store`, `spec.check_skip_holidays()` y la pantalla rechazan otra cosa. Se prende con
  `hábiles` en el chat o con la casilla «No suena en feriados» de la pantalla. Entra por
  `_add_missing_columns` en cero: ⚠️ **lo que ya existía no se migra**, una alarma `hábiles`
  de antes sigue sonando en feriados hasta que se la edite desde la pantalla o se vuelva a
  crear.
- **En el chat se nota en la repetición**: «días hábiles» si son de lunes a viernes, o los
  días con «, sin feriados» (`spec.weekdays_label()`).
- 🔴 **El salteo se decide al sonar, no en `next_run()`.** `spec.skips()` mira la fecha de la
  ocurrencia contra la caché. Así `next_run()` sigue siendo una sola función para el
  reagendado y para la pantalla, y un feriado cargado tarde igual se respeta.
- 🔴 **Un día salteado no anuncia ni deja nada para después**: no escribe en `fired`,
  `awaiting` ni `ringing`, así que no hay posponer, «Hecho» ni repetición. Deja la fila del
  historial cerrada como `holiday`, avisa a todos «🏖 Feriado (<nombre>): hoy no suena «…»»
  y reagenda a la próxima ocurrencia.
- 🔴 **Si la caché no se puede leer, suena** (`Reminders._holiday()` loguea y sigue).
- **El nombre escrito va como lo publica la API**, sin el paréntesis con la fecha
  (`clean_name()`). Lo hablado pasa por `spoken_name()`: `Gral.`, `Dr.`, `Sta.` y `Sto.` se
  dicen enteras, y un romano después de un nombre propio va en palabras («León XIV» →
  «León catorce», hasta `MAX_ROMAN`). ⚠️ Si aun así queda un dígito, se dice solo «Hoy es
  feriado.».
- **La pantalla los muestra**: el feriado como evento de día completo y la ocurrencia que
  no va a sonar, marcada. Ver **Pantalla de la casa**, en `.claude/rules/web.md`.
