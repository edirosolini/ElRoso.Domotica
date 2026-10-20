---
paths:
  - "src/homeauto/strangers.py"
  - "src/homeauto/config.py"
  - "src/homeauto/main.py"
  - "tests/test_strangers.py"
  - "tests/test_alert_chats.py"
  - "tests/test_config.py"
---

# Quién usa el bot y a quién le llega cada aviso

## Quién puede usar el bot

`ALLOWED_CHAT_IDS` es la lista blanca. `ALERT_CHAT_IDS`, un subconjunto, dice quién recibe
los avisos del monitor y de Seq; ver **A quién le llega cada aviso**. Un chat que no está recibe su ID y nada más, sea
por `/start`, cualquier comando, texto suelto, nota de voz o un botón.

- **El ID va solo en el último renglón**: un toque largo en Telegram copia el renglón
  entero, y así sale el número sin el texto.
- 🔴 **Los dueños se enteran solos.** `strangers.Strangers` les manda nombre, @usuario e ID
  de quien escribió, con la línea `ALLOWED_CHAT_IDS=…` ya armada para pegar. La persona no
  tiene que mandar el número por otro lado.
- **Una sola vez por chat**, guardado en `StrangerStore`: un desconocido insistente no puede
  llenar el chat del dueño. Un aviso que no llegó a ningún dueño no se marca y se reintenta
  con el mensaje siguiente, como en la agenda.
- **Sin lista blanca no hay a quién avisar**: el bot está abierto, todos entran, y
  `/start` ya le dice al primero que se cargue.
- **El aviso corre fuera del event loop y su falla no cuesta la respuesta.** El nombre sale
  del `update` en `main._who()`; `Strangers` no sabe de Telegram.
- ⚠️ Cargar el ID pide **reiniciar el servicio**: la config se lee una sola vez.

## A quién le llega cada aviso

Todos los chats de `ALLOWED_CHAT_IDS` son iguales salvo por una cosa: los avisos de
vigilancia van a `ALERT_CHAT_IDS`. Decisión del dueño.

| Aviso | Llega a |
| --- | --- |
| monitor y Seq, dichos o en descanso | `ALERT_CHAT_IDS` |
| re-aviso de una caída sin confirmar | `ALERT_CHAT_IDS`, con «✅ Confirmar»; en descanso o silencio, solo escrito |
| caída confirmada | los otros chats de alertas: «✅ <nombre> confirmó: X no responde» |
| resumen y cierre | todos; la línea de caídos y los errores de la noche, solo a alertas |
| resumen semanal | todos, solo escrito |
| alarmas, recordatorios y timers | todos, con posponer; la alarma también con «🔕 Apagar», recordatorios y timers con «Hecho» |
| repetición de una alarma sin apagar | todos, en cada repetición y solo con «🔕 Apagar», también en descanso; «Dejé de sonar» al tope |
| alarma apagada | los demás chats: «🔕 <nombre> apagó la alarma» |
| re-aviso de un recordatorio o timer sin «Hecho» | todos, solo por chat y solo con «Hecho» |
| remedio que se acaba | todos, solo escrito: «💊 Quedan N de X, comprar.» |
| algo programado que un feriado saltea | todos, solo escrito: «🏖 Feriado (<nombre>): hoy no suena «…»» |
| corte de internet | solo el parlante, sin chat; al volver, todos: «🌐 Internet se cortó de … a …» |
| plato del menú cambiado con `/menu otra` | los demás chats, solo escrito: «🍽 <nombre> cambió la cena del miércoles 21/10: …» |
| vacaciones activadas o cortadas | los demás chats: «🧳 <nombre> activó vacaciones hasta el …» / «… cortó las vacaciones» |
| fin de las vacaciones | todos: «🧳 Terminó el modo vacaciones, vuelvo a hablar.» |
| agenda, clima, lluvia, API | todos |
| alta, cambio o baja desde la pantalla | todos; el alta y el cambio, con «Cancelar #N» |
| borrado con ese «Cancelar #N» | los demás chats: «🗑 <nombre> borró #N» |
| lo hecho desde `/control` | lo mismo que el botón o el comando en Telegram: los demás chats, con «<nombre> (pantalla)» |
| respuesta de un comando | el chat que lo escribió |
| aviso de un desconocido | todos (`Strangers`) |

- **`ALERT_CHAT_IDS` vacía es todos**, que es como se comportaba antes de existir. Un
  despliegue viejo no cambia nada.
- 🔴 **Un ID de alertas fuera de `ALLOWED_CHAT_IDS` hace fallar el arranque.** El aviso le
  llegaría con botones que el bot le rechaza.
- **`HouseVoice.tell(text, others)`** es la única puerta: `text` va a los chats de alertas y
  `others` al resto. `SAME` repite el texto, `None` o vacío no escribe nada.
  `tell_everyone()` es `tell(text, SAME)`.
- **El parlante no sabe de chats.** Lo que suena, suena en toda la casa: separar los chats no
  hace privado un aviso dicho en voz alta.
- `/lista` y `/cancelar` siguen siendo de quien creó la alarma, aunque el aviso le llegue a
  todos. El «Cancelar #N» de un aviso de la pantalla no: borra desde cualquier chat. Ver
  **Pantalla de la casa**, en `.claude/rules/web.md`.
- **`/control` no tiene destinatarios propios.** Corre el comando a nombre del chat elegido,
  así que ese chat queda como «el que lo tocó» y no recibe el aviso a los demás. Ver
  **Control desde la web**, en `.claude/rules/web.md`.
