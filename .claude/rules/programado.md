---
paths:
  - "src/homeauto/schedule/**"
  - "src/homeauto/timespec.py"
  - "src/homeauto/main.py"
  - "tests/schedule/**"
  - "tests/test_timespec.py"
  - "tests/bot/test_alarm_buttons.py"
  - "tests/bot/test_alarm_off.py"
  - "tests/bot/test_postpone_command.py"
  - "tests/bot/test_remind_command.py"
  - "tests/bot/test_rota_command.py"
  - "tests/bot/test_schedule_commands.py"
  - "tests/bot/test_stock_command.py"
---

# Alarmas, recordatorios y timers

## Alarma, recordatorio y timer

Tres tipos de programado, pedidos por el dueño el 2026-09-28: una medicación o salir al
colegio sonaban con los tres beeps de despertador y decían "(alarma de todos los días)".

| | Repite | Sonido | Botones | Si nadie responde |
| --- | --- | --- | --- | --- |
| `/alarma` | una vez, diaria, por días o mensual | el despertador, a 90 | «🔕 Apagar» y posponer | vuelve a sonar cada cinco minutos |
| `/recordar` | **siempre**, en los días marcados o un día de cada mes | un beep suave | «✅ Hecho» y posponer | re-avisa |
| `/timer` | nunca | un beep suave | «✅ Hecho» y posponer | re-avisa |

- 🔴 **El tipo es la columna `kind` de `jobs`** (`alarm` / `reminder`). Entra por
  `_add_missing_columns` con default `alarm`: lo agendado antes de existir sigue siendo
  alarma, incluidos los timers pendientes, que suenan con el despertador y repiten como una
  alarma.
- 🔴 **Un recordatorio sin días no se agenda.** Una sola vez es un timer, y `/timer` ya
  acepta una hora (`mañana 10:00`). Sin barra, la pregunta que falta es `slots.DAYS`, sin la
  opción «Una sola vez».
- **`/recordar` dejó de ser alias de `/timer`.** Es su propio comando, con la misma forma que
  `/alarma` (`Commands._repeating`).
- 🔴 **«Hecho» cierra por número de job, no por lo último que sonó.** La pastilla y el
  colegio suenan con minutos de diferencia; marcar el primero no puede depender del orden.
  El aviso manda `hecho <id>` y `AwaitingStore` guarda el mensaje de cada job que sonó hasta
  que alguien lo marca, así un timer ya borrado de `jobs` igual se puede cerrar.
- **«Hecho» se marca una sola vez, desde cualquier chat**, y avisa a los demás «✅ <nombre>
  marcó hecho». El aviso le llegó a todos, así que lo cierra cualquiera. El segundo toque
  contesta que ya estaba. También borra lo que sonó, así ya no se pospone.
- **En un recordatorio atado a un remedio, «Hecho» descuenta una dosis.** Ver **Pastillas que
  se acaban**.
- **Lo que espera un «Hecho» vence al día** (`awaiting.KEEP`): se poda cada vez que suena otro.
- 🔴 **Sin «Hecho», se vuelve a avisar** a los cinco, diez y quince minutos (`NAG_DELAY`,
  `NAG_LIMIT`): «🔔 Sigue pendiente: «…»». Un recordatorio que sonó una vez y nadie tocó
  quedaba olvidado, que es justo lo que no puede pasar con una medicación.
- **El re-aviso es solo chat y solo trae «Hecho».** No suena, no pasa por el pulidor y no
  ofrece posponer: es insistir, no un segundo aviso. Va a todos los chats y **sale también
  en descanso**, porque no despierta a nadie.
- **«Hecho», posponer y `/cancelar` lo cortan.** Los tres sacan el job de `awaiting_done` y
  desagendan su timer.
- 🔴 **El timer del re-aviso usa la clave `nag:<id>`, no la del job.** Un recordatorio diario
  se rearma con `str(id)` al sonar: con la misma clave, el rearme pisaría el re-aviso.
- **Sobrevive un reinicio**: `nags` y `next_nag` viven en `awaiting_done`. Al arrancar, un
  re-aviso atrasado sale **una vez** y retoma el ritmo; pasado `SNOOZE_WINDOW` desde que sonó
  ya no sale. Las columnas entran por `_add_missing_columns`, y lo que esperaba un «Hecho»
  antes de existir queda con `next_nag` vacío: **no re-avisa**.
- ⚠️ **`/cancelar` de un `/timer` que ya sonó contesta «No encontré»**: el job se borra al
  sonar. «Hecho» es la forma de cortarlo.
- ⚠️ **Con `ALLOWED_CHAT_IDS` vacío, el re-aviso de un timer se queda sin destino tras un
  reinicio.** El chat sale del job, que ya no existe; sin lista, no hay a quién escribir.
- 🔴 **`hecho` y `callar` son solo botones**, como `borrar`: están en `Commands.press()` y no en
  `_dispatch()`, así el router nunca los nombra y el test que ata las dos listas sigue en pie. El nombre de quien
  tocó sale de `main._who()` y entra a `press(who=...)`.
- 🔴 **Una alarma suena hasta que alguien la apague.** Vuelve a sonar cinco minutos después de que
  termina el anuncio anterior (`RING_DELAY`), con la clave de timer `ring:<id>`, por lo mismo
  que `nag:<id>`. Cada repetición sube el despertador (`wake1`, `wake2`, después `wake3`, que
  llega hacia el minuto diez) y suma uno a los re-avisos del historial.
- 🔴 **Tope de media hora desde que sonó** (`RING_LIMIT`): son cinco repeticiones, hacia los
  cinco, diez, quince, veinte y veinticinco minutos. Al llegar deja de sonar y escribe
  una sola vez «⏰ Dejé de sonar: «…», nadie la apagó» a todos los chats.
- **Cada repetición escribe al chat** «⏰ Sigue sonando», solo con «🔕 Apagar». En descanso no
  se habla, así que ese texto es todo lo que sale, y sale igual en cada repetición.
- 🔴 **«🔕 Apagar» manda `callar <id>`** y apaga desde cualquier chat, porque el aviso le llegó
  a todos. Corta el audio en curso (`Announcer.stop()`), olvida en `FiredStore` solo los chats
  cuyo último disparo fue esa alarma, cierra el historial como `off` con quién y avisa a los
  demás «🔕 <nombre> apagó la alarma». El segundo toque contesta que ya estaba apagada. El
  método es `Commands.alarm_off`: `silence` ya es `/silencio`.
- **Posponer, `/cancelar` y `borrar` cortan la repetición.** ⚠️ Posponer no corta el audio
  que esté sonando en ese momento; solo «Apagar» lo hace.
- ⚠️ **Una alarma de una sola vez se borra de `jobs` al sonar**: `/cancelar` contesta «No
  encontré» y lo que la corta es «Apagar». `RingingStore` guarda mensaje y equipos para
  seguir sonando sin el job.
- **La repetición sobrevive un reinicio**: `rings` y `next_ring` viven en `ringing`. Al
  arrancar, una atrasada suena una vez y retoma el ritmo; una que ya pasó el tope no suena y
  escribe «Dejé de sonar».
- **Posponer conserva el tipo**: `FiredStore` guarda `kind`, y un recordatorio pospuesto
  vuelve a sonar como recordatorio.
- **En vacaciones una alarma no suena: se escribe una sola vez**, no repite y sale sin
  «🔕 Apagar». Activarlas corta las que estaban sonando. Ver **Modo vacaciones**, en `.claude/rules/descanso-y-feriados.md`.
- **Una alarma en un equipo con pantalla prende su vista en la tele** durante un minuto
  después de cada sonido, pasa al kiosco hasta la próxima repetición y cierra la tele a los
  quince minutos de que deja de sonar. Solo `kind=alarm`; un recordatorio o un timer no. Ver **Pantalla en la TV**, en `.claude/rules/pantalla-tv.md`.
- ⚠️ **Se tocó el prompt del router** para sumar `recordar` y el ejemplo "recordame mañana a
  las diez" → `timer`. Medido el 2026-09-28: treinta y cuatro de treinta y cuatro, después
  de acotar la regla de las duraciones (ver **Texto libre**, en `.claude/rules/router-y-conversacion.md`).

## Alarmas y repetición

Una alarma o un recordatorio repite de cuatro formas: `once`, `daily`, `weekly` y `monthly`.
La semanal guarda los días en la columna `days` de `jobs`, como números ISO (1 = lunes), la
misma numeración que `datetime.isoweekday()`; la mensual, el día del mes en `monthday`.

- **Los días eligen la ocurrencia de la hora, no la hora.** Por eso `parse_weekdays()` está
  separado de `parse_schedule()`: primero se resuelve la hora — que ya rueda sola al día
  siguiente si pasó — y recién después `next_weekday()` la corre hasta el primer día pedido.
- **Con días, la hora es obligatoria.** `/alarma lun-vie 10m` se rechaza: una duración
  relativa cae en el día que caiga y no tiene nada que ver con los días pedidos.
- Un rango **da la vuelta**: `vie-lun` es viernes, sábado, domingo y lunes. Se cuenta hacia
  adelante en módulo siete en vez de rebanar una lista.
- `Store.add()` **rechaza una alarma semanal sin días**: no encontraría nunca un día para
  disparar y quedaría muerta en la base sin ruido.
- Al disparar, la próxima corrida se busca **desde el día siguiente**, o volvería a caer en
  el mismo día para siempre.
- La columna `days` entra por `_add_missing_columns`, como `device`: hay bases desplegadas
  de antes.
- ⚠️ **Los nombres de día son texto de chat, no de parlante.** `format_weekdays()` vive en
  `timespec.py` y no pasa por `verbalize.py` porque el parlante dice el mensaje de la alarma,
  nunca sus días. Si algún día se hablan, hay que verbalizarlos.
- El reloj acepta `5.30` además de `5:30`. Es como la gente escribe la hora; no cambia nada
  más del parser.
- 🔴 **`hábiles` no es `lun-vie`.** Los dos son de lunes a viernes, pero `hábiles` (o
  `habiles`, también dentro de una lista con comas) además prende `skip_holidays` y no suena
  en feriados. `lun-vie` y `semana` no lo prenden. Ver **Feriados**, en `.claude/rules/descanso-y-feriados.md`.

**La mensual** se escribe `mensual 10 9:00 pagar la luz`, en `/recordar` y en `/alarma`.
`parse_monthday()` lee el día y `spec.resolve()` busca la primera vez que cae.

- 🔴 **El día pedido se guarda aparte de la próxima fecha.** Un mes que no tiene ese día cae
  en su último día (`store.on_monthday()`), y el mes siguiente vuelve al pedido: 31/1 → 28/2
  → 31/3. Sacar el día de `fires_at` lo dejaría en 28 para siempre después de febrero.
- **Con un día mayor a veintiocho, al crear se avisa** «Los meses que no tienen N, el último
  día.» (`spec.short_month_note()`).
- **La hora es obligatoria**, como con días. Sin hora, `slots` pregunta «¿A qué hora?».
  ⚠️ **`mensual` sin día no pregunta**: no hay pregunta para el día, y el comando contesta con
  la forma (`Con mensual necesito el día del mes`).
- `Store.add()` **rechaza un mensual sin día o con un día fuera de uno a treinta y uno**, por
  lo mismo que un semanal sin días. `monthday` entra por `_add_missing_columns` y queda vacío
  en todo lo que no es mensual.
- **Los timers no aceptan mensual**: `/timer` no lo lee y `spec.classify()` lo rechaza desde
  la pantalla.
- 🔴 **La repetición se escribe en un solo lugar.** `spec.repetition_label()` («el 10 de cada
  mes», «lun, mar», «todos los días») la usan `/lista` y el aviso de la pantalla; estaba
  copiada en los dos. Al sonar, la línea del chat usa `spec.ringing_label()`, sin dígitos:
  «(recordatorio del diez de cada mes)».

## Posponer

`/posponer` repite la alarma, el recordatorio o el timer que acaba de sonar, y el aviso de Telegram trae dos
botones, «Posponer 10 min» y «Posponer 30 min», que hacen lo mismo.

- **Se pospone lo último que sonó en ese chat**, no un número de `/lista`. Quien acaba de
  escuchar el aviso no sabe qué número tenía.
- 🔴 **Cualquiera la pospone, una sola vez.** El aviso le llega a todos los chats, así que lo
  que sonó se guarda para todos, y posponer lo borra para todos: el botón del otro contesta
  que no hay nada que posponer. El job nuevo queda a nombre de quien tocó.
- **Posponer una alarma corta su repetición**, pero no el audio en curso.
- **Crea un job de una sola vez**, con el mismo mensaje y los mismos equipos. Una alarma que
  repite sigue su curso: posponer el lunes no mueve el martes.
- **Lo pospuesto de algo que se turna conserva a quién le tocaba**: el mensaje que se copia
  ya lleva «Le toca a <nombre>:». Ver **Tareas por turno**.
- 🔴 **Posponer cierra el «Hecho» del original.** `last_fired` guarda el `job_id` (por
  `_add_missing_columns`) y posponer saca ese job de la espera: si no, el original seguiría
  re-avisando mientras el pospuesto espera su turno.
- 🔴 **Posponer copia el `stock_id`.** `last_fired` lo guarda junto al `job_id`, así el «Hecho»
  del pospuesto descuenta del mismo remedio aunque el job original ya no exista.
- **Solo vale media hora** después de sonar (`SNOOZE_WINDOW`). Pasado eso contesta que no hay
  nada que posponer, en vez de agendar algo que nadie espera. Sin duración son diez minutos.
- 🔴 **Lo que sonó se guarda antes de anunciarlo.** El botón llega con el aviso y el anuncio
  bloquea hasta que termina de sonar: guardado después, un toque rápido no encontraba nada.
- 🔴 **Posponer olvida lo que sonó**, y el botón tocado se saca del mensaje. Dos toques no
  agendan dos veces: el segundo, aunque sea el otro botón, contesta que no hay nada que
  posponer. Lo pospuesto, cuando suena, se puede volver a posponer.
- **Se guarda en SQLite**, `schedule.FiredStore`, por lo mismo que el silencio: un reinicio
  justo después de la alarma no puede dejar el botón sin nada atrás.
- **El botón no sabe de Telegram hacia adentro.** `Announcer` recibe `actions` como pares
  (etiqueta, comando con argumento); `ChatNotifier` los dibuja y `Commands.press()` los
  ejecuta por `_dispatch()`, así que un botón solo puede correr un comando que ya existe.
  Sin botones, el notificador se sigue llamando con dos argumentos, como lo llama la API.
- **Se saca solo el botón tocado**, no todos: ver el estado no puede llevarse puesto el botón
  de silenciar.
- ⚠️ **`callback_data` tiene tope de 64 bytes** en Telegram. Hay test que lo verifica.
- **Se tocó el prompt del router** para sumar `posponer`, y se volvió a medir el 2026-09-25:
  treinta y uno de treinta y uno (la última medición, cuarenta y dos). Ver **Texto libre**, en `.claude/rules/router-y-conversacion.md`.

## Historial de lo que sonó

`schedule.HistoryStore` (`fired_history`) guarda una fila por cada vez que suena una alarma,
un recordatorio o un timer: si se dijo, cuántos re-avisos —en una alarma, cuántas veces
repitió—, «Hecho» y quién, apagada y quién (`off`, en `done_by`), pospuesto, cancelado o
salteado por feriado (`holiday`), con `closed_at`. `Reminders` es el único que escribe.

- 🔴 **La fila se graba antes de anunciar** y nace como no dicha; `mark_announced()` la da
  por dicha solo si el anuncio no levantó. Un parlante apagado deja la marca de que no sonó,
  en vez de no dejar nada.
- 🔴 **El historial no puede costar un aviso.** Toda escritura pasa por
  `Reminders._write_history()`, que loguea la falla y sigue.
- **Cada marca toca solo la última fila abierta del job** (`closed IS NULL`). Una alarma
  diaria tiene una fila por día; marcar la de hoy no reescribe la de ayer.
- 🔴 **Cancelar solo cierra lo que sigue pendiente**: lo que esperaba «Hecho» o una alarma que repite. `/cancelar` de algo que nunca sonó no
  escribe nada, y una alarma diaria cancelada no toca la fila de ayer: esa ya terminó como
  terminó. Una alarma cancelada o borrada mientras repite también se cierra como cancelada.
  ⚠️ La que llegó al tope deja su fila abierta: solo «Apagar» la cierra.
- **Doce meses** (`history.KEEP`), podados al insertar, como `awaiting.KEEP`. Sin job aparte.
- **En lo que se turna, la fila guarda el mensaje con el nombre**, así el pasado de la
  pantalla dice a quién le tocó esa vez. Ver **Tareas por turno**.

## Pastillas que se acaban

`schedule/stock.py` cuenta cuántas dosis quedan de cada remedio. `StockStore` es la tabla
`pill_stock`: `name`, `count`, `threshold` y `alerted`.

- **Un recordatorio se ata a un remedio por número de job**: `/pastillas 7 enalapril 30`.
  `stock_id` vive en `jobs`, `last_fired` y `awaiting_done`, y entra por
  `_add_missing_columns`: lo que ya existía queda sin remedio.
- 🔴 **Solo se ata a un recordatorio que repite.** La dosis se descuenta con «Hecho», que una
  alarma no tiene, y un timer o un recordatorio pospuesto suenan una sola vez.
- **El nombre es único sin importar mayúsculas** y se guarda en minúsculas con los espacios
  colapsados: «Enalapril» y «enalapril» son el mismo remedio. Así **dos tomas pueden compartir
  el stock**: la de la mañana y la de la noche se atan al mismo nombre.
- ⚠️ **Atar a un remedio que ya existe con una cantidad la fija**: `/pastillas 8 enalapril 30`
  deja treinta, no suma, y recalcula `alerted` como al reponer. Para sumar está
  `/pastillas enalapril +30`.
- **Sin cantidad, ata si el remedio existe**; si no, pregunta cuántas hay. No pasa por
  `slots`: es la respuesta del comando.
- 🔴 **Se descuenta solo si `take()` devolvió el mensaje**, o sea con el primer «Hecho». Un
  doble toque no descuenta dos veces. **Nunca baja de cero.**
- 🔴 **Una falla del stock no le cuesta el «Hecho».** `Reminders._take_dose()` loguea y sigue,
  como el historial.
- 🔴 **Avisa una sola vez**, cuando lo que queda llega al umbral (`count <= threshold`):
  «💊 Quedan N de X, comprar.», o «💊 No quedan de X, comprar.». Solo por chat y a todos; no
  suena ni pasa por el pulidor. Además suma el remedio a `/compras`, y `ListStore.add` no lo
  duplica si ya estaba.
- **El umbral por defecto es `STOCK_ALERT`, siete**, y se cambia por remedio con
  `/pastillas enalapril aviso 5`.
- **`alerted` se apaga al reponer o fijar la cantidad por encima del umbral**, o al cambiar el
  umbral a uno por debajo de lo que queda. ⚠️ Subir el umbral hasta lo que queda o más no avisa
  a todos en el acto: la respuesta lo dice («Ojo: ya quedan N, por debajo del aviso.») y el
  aviso sale con el próximo «Hecho».
- **Reponer no crea un remedio.** `/pastillas X +30` de uno que no se cuenta contesta cómo
  empezar.
- **Cualquier chat permitido ata cualquier job**, a diferencia de `/cancelar`: un remedio es de
  la casa, no de quien creó el recordatorio.
- **`/pastillas` no está en el menú**, sí en `HELP`. Ver **Comandos y alias**, en `.claude/rules/router-y-conversacion.md`.

## Tareas por turno

`/turnos 7 Cin, Die` hace que el #7 le toque a uno por semana: «Le toca a Cin: sacar la
basura». `schedule/rota.py` es la lógica; los nombres viven en dos columnas de `jobs`.

- 🔴 **`rota.turn_for(job, at)` es la única fuente de a quién le toca**, para lo que suena, la
  pantalla, `/turnos` y `/lista`. Es la misma regla que `next_run()`: con dos copias, la
  agenda diría un nombre y el parlante otro.
- **Rota por semana ISO, de lunes a domingo**, contando semanas desde `rota_from`, que es el
  lunes de la semana en que se corrió `/turnos`. Se cuentan lunes, no el número de semana del
  año, así cruza el fin de año sin saltos. Lo que suena varias veces en una semana le toca
  toda la semana a la misma persona.
- ⚠️ **Volver a correr `/turnos` reinicia la cuenta**: el primer nombre de la lista es el de
  esta semana.
- **`rota` (los nombres, separados por coma) y `rota_from` son columnas de `jobs`**, por
  `_add_missing_columns`. No hay tabla nueva. `Store.update()` no las toca: editar el aviso
  desde la pantalla conserva la rotación.
- 🔴 **El nombre entra en `Reminders._fire()`, antes que todo lo demás**: el job que se
  anuncia ya trae «Le toca a <nombre>: <mensaje>». Por eso lo llevan lo pospuesto, «Hecho»,
  el re-aviso, el historial, la repetición de una alarma (`ringing`) y el aviso de feriado.
  En `jobs` el mensaje queda sin el prefijo.
- 🔴 **El nombre va en el `must_keep` del pulidor.** `Announcer` lo lee del prefijo con
  `rota.turn_in()`, no del job, y así también lo protege en una alarma que repite o en un
  pospuesto, que ya no rotan pero llevan el nombre en el mensaje.
- 🔴 **Un nombre es letras y espacios, nada más** (`_SAYABLE_NAME`): se dice en voz alta, por
  lo mismo que el alias de un Seq. Se separa por comas y por «y», con `lists.split_items()`.
- **Solo se turna lo que repite.** Un timer, una alarma de una sola vez o un pospuesto se
  rechazan: sonar una vez no tiene turnos.
- **Un solo nombre se acepta.** No rota, pero el aviso dice a quién le toca.
- **Cualquier chat permitido turna cualquier job**, como `/pastillas`: la tarea es de la casa.
- `/turnos 7 off` lo corta y `/turnos` lista lo que se turna en toda la casa, con a quién le
  toca la próxima. `/lista` lo muestra como « · turnos Cin, Die».
- **No hay cambio de turno a mano ni salteo de una semana.** Quedaron fuera de alcance.
- **`/turnos` no está en el menú**, sí en `HELP`. Ver **Comandos y alias**, en `.claude/rules/router-y-conversacion.md`.

## Nombre entre corchetes

Un mensaje de alarma, recordatorio o timer que empieza con «[Nombre]» se dice y se escribe
como un llamado: «[Papá] tomar medicación» suena «Papá, tomar medicación».
`announcer._called()` lo resuelve antes del pulidor.

- 🔴 **El nombre va en el `must_keep` del pulidor**, junto al del turno si lo hay.
- **Convive con el turno**: «Le toca a Cin: [Papá] tomar» es «Le toca a Cin: Papá, tomar»;
  el corchete se busca después del prefijo de `rota.with_turn()`.
- **Solo letras y espacios, y pegado al principio.** Un corchete en el medio, con dígitos,
  vacío, sin cerrar, con un espacio adelante o con una coma adentro queda como se escribió.
- **En `jobs` el mensaje se guarda con los corchetes**; la transformación es solo al anunciar.
- ⚠️ **Fuera del aviso, todo lo escrito muestra el mensaje con los corchetes**: el chat de
  «⏰ Sigue sonando» (lo hablado de la repetición sí sale «Papá, …»), «🔔 Sigue pendiente»,
  «⏰ Dejé de sonar», `/lista`, `/turnos`, los avisos a los demás chats, el resumen semanal,
  `/control` y la pantalla, incluida la vista de alarma de la tele.
