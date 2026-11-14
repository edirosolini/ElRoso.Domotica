---
paths:
  - "src/homeauto/route.py"
  - "src/homeauto/slots.py"
  - "src/homeauto/pending.py"
  - "src/homeauto/listen.py"
  - "src/homeauto/aloud.py"
  - "src/homeauto/bot/**"
  - "src/homeauto/main.py"
  - "deploy/measure_router.py"
  - "tests/test_route.py"
  - "tests/test_slots.py"
  - "tests/test_pending.py"
  - "tests/test_listen.py"
  - "tests/test_aloud.py"
  - "tests/bot/**"
---

# Router y conversación

## Botones en las respuestas

Además de los avisos, la respuesta de un comando puede traer botones. Los comandos siguen
devolviendo un string: los botones van aparte.

- 🔴 **Un comando ofrece botones con `offer()`, y `with_actions()` los junta con la
  respuesta** en un `Reply`. Van en un `contextvars.ContextVar`, como la coletilla del
  parlante, porque son del pedido y dos mensajes se atienden a la vez. Así ningún comando
  cambió de firma, y la respuesta del texto libre y de la nota de voz heredan los botones
  del comando que corrieron sin hacer nada.
- **Qué ofrece cada uno**: lo programado —`/timer`, `/alarma`, `/recordar`, `/posponer`—
  trae «🗑 Borrar este aviso» (`cancelar <id>`), que es el deshacer de lo que se agendó, y ni
  el botón ni la respuesta muestran el número; `/lista`, un «🗑 <cuándo> <mensaje>» por cada
  uno; `/compras` y `/pendientes`, un «✓ ítem» por cada uno y «Vaciar»; `/menu`, «🛒 Pasar a
  compras» y «🔄 Otra idea»; `/silencio` con un silencio puesto, «Volver a hablar»
  (`TALK_ACTION`); `/vacaciones` y todo lo que se niega por vacaciones, «Volví de vacaciones»
  (`BACK_ACTION`); `/pantalla`, «Sacar la pantalla».
- **`/lista` es «Mis avisos»**: el encabezado, un renglón por aviso con su `#N` y el pie
  «Tocá uno para borrarlo.». El botón dice cuándo suena y qué dice (`format_when()`), cortado
  a cuarenta caracteres como toda etiqueta.
- **El número queda donde se elige por él**: `/lista`, `/cancelar`, `/pastillas`, `/turnos`,
  el 404 de la API y `/depurar`. `/cancelar` contesta «🗑 Borrado: «…»», con el mensaje y sin
  el número; uno que no existe, «No encontré ese aviso. Fijate con /lista».
- 🔴 **Tachar va por id, no por posición.** Con `sacar 1`, tachar el primero corría los
  demás y el botón siguiente sacaba otro ítem. El botón manda `sacar id:17`, que
  `ListStore.remove_id()` borra solo si sigue en esa lista. Escrito a mano, `/sacar 2` sigue
  siendo la posición.
- ⚠️ **«Vaciar» es un toque sin deshacer**, igual que `/sacar todo` escrito.
- 🔴 **La pregunta de la repetición de una alarma trae sus respuestas**: «Una sola vez»,
  «Todos los días», «De lunes a viernes». Son las `choices` de `slots.REPEAT`. El botón no
  corre un comando: manda `» todos los días` y `Commands.press()` lo entrega a
  `free_text()` como si se hubiera escrito, así sigue el mismo hilo y el mismo prompt medido.
- **Como mucho veinte botones** (`MAX_BUTTONS`) y etiquetas de cuarenta caracteres: una
  lista larga no puede volverse una pared. `callback_data` lleva el id, no el texto, así que
  un ítem largo entra igual en los 64 bytes.
- **En las respuestas va un botón por renglón**; en los avisos, todos en uno.
- ⚠️ **`press()`, `free_text()` y `with_actions()` también los llama `/control`**, el segundo
  transporte de `Commands`. Cambiarles la firma o lo que devuelven rompe la web. Ver **Control
  desde la web**, en `.claude/rules/web.md`.

## Texto libre

`route.py` interpreta un mensaje **sin barra adelante**: decide qué comando quiso la persona
y con qué argumento. No ejecuta nada — `Commands` ya sabe hacerlo y los parsers que ya
existen ya saben rechazar un argumento malo.

- **Ejecuta y avisa qué entendió; no pide confirmación.** Es decisión del dueño de la casa.
  La respuesta arranca con `Entendí: /clima` para que una lectura errada se vea. Lo único que
  se pregunta antes es un dato que falta —ver **Conversación**—, y eso no es confirmar: es no
  inventarlo.
- 🔴 **Lo que se agenda confirma en castellano, sin «Entendí:».** `/timer`, `/alarma`,
  `/recordar` y `/posponer` contestan «Listo: te aviso hoy a las 21:10 en Parlante: «…»»,
  «Listo: la alarma suena todos los días a las 7:30 …» o «Listo: te vuelvo a avisar …»
  (`_confirm_when()`), y eso ya dice qué se entendió; el deshacer es «🗑 Borrar este aviso».
  El comando marca `_CONFIRMED` solo si agendó, y `_route_and_run()` saca el «Entendí:» solo
  con esa marca: un argumento que no parsea sigue saliendo `Entendí: /timer 25:99 …` con el
  error, que es donde más importa ver la lectura.
- **Un llamado es la excepción, y por eso es un comando aparte.** "llamar a todos a cenar" no
  contiene la frase a decir; `llamar` la genera. Ver **Llamar a la casa**, en `.claude/rules/voz.md`.
- 🔴 **Lo que la casa va a decir con voz propia tiene que salir del mensaje.** Un modelo al
  que se le pide extraer un texto lo mejora de paso. `Router._faithful()` compara el payload
  de `decir` contra el mensaje original —normalizado, y sacándole el `en <equipo>` que arma
  el propio router— y si no está, se trata como pregunta. Un mensaje inventado en boca de la
  casa es peor que no entender.
- 🔴 **Medido el 2026-10-15 contra el endpoint real: cuarenta y dos de cuarenta y dos
  comandos y treinta y uno de treinta y uno payloads**, con `gemini-3.1-flash-lite`. Es la
  corrida de después de sumar `pantalla`, con el ejemplo «poné la pantalla en la tele de la
  recámara» → `en recamara` y el caso negativo «mostrame la agenda» → `agenda`: ver la agenda
  no es pedir la pantalla. La anterior, con `turnos`, había dado cuarenta de cuarenta.
  `deploy/measure_router.py` es esa corrida: vive en el repo porque la regla de volver a medir
  no sirve si medir es un trabajo. Corre **adentro del CT**, que es donde está la clave.
- 🔴 **Medido el 2026-10-20, después de sumar `menu`: cuarenta y seis de cuarenta y seis
  comandos y treinta y cuatro de treinta y cuatro payloads**, con `gemini-3.1-flash-lite`. Se
  sumaron cuatro ejemplos —tres de `menu` y el negativo «agregá milanesas a compras» →
  `agregar`: un ítem suelto no es el menú— y los mismos cuatro casos a la medición. Seis
  paráfrasis que no están en el prompt también salieron bien.
- 🔴 **Con `depurar` la medición pasó a cuarenta y siete casos** («limpiá las teles viejas» →
  `depurar teles`), y con «para <persona>» a cincuenta y uno: «recordale a China…» →
  `recordar para China`, «recordale a Papá en media hora…» → `timer para Papá`, «recordales
  a todos…» → `recordar para todos`, y el negativo «recordame para mañana comprar pan», que
  no puede llevar «para mañana» adelante. Medido el 2026-10-21: **cincuenta y uno de
  cincuenta y uno comandos y treinta y nueve de treinta y nueve payloads**.
- **Un fragmento con «!» adelante es un payload que no tiene que aparecer** (`payload_ok()`):
  `"!para mañana"` falla si el argumento lo trae, y la línea dice «sobra» en vez de «falta».
- ⚠️ **`measure_router.py` agrega `/opt/domotica/src` adelante de `sys.path`**, y eso le gana a
  `PYTHONPATH`: corrido tal cual mide el prompt **desplegado**. Para medir una rama, la copia
  del script tiene que apuntar a la copia del src.
- ⚠️ **«recordame comprar los pasajes de las vacaciones» acepta `recordar` o `agregar`.** El
  caso está para que no vaya a `vacaciones`. Con el ejemplo de `pantalla`, una de cada seis
  veces se va a pendientes, y sin hora es una lectura razonable. Un caso de la medición puede
  llevar una tupla de comandos válidos.
- ⚠️ **Un `Read timed out` de la API en la medición no es el prompt**: el router corta a los
  seis segundos y el caso sale como `RouteError`. Se vuelve a correr.
- ⚠️ **La medición usa el proveedor y el modelo barato del env del CT**, por `build_model`, y
  los imprime al empezar. Con un modelo que la API no acepta, las cincuenta y una llamadas
  fallan y el resultado es cero: es el modelo, no el prompt. Con `LLM_PROVIDER=anthropic` y
  Claude Haiku 5.5, el mismo prompt dio treinta y nueve o cuarenta de cuarenta y dos
  (2026-10-20): por eso el router sigue en Gemini. Ver **Proveedor del texto**, en
  `.claude/rules/voz.md`.
- 🔴 **La medición encontró lo que los tests no podían.** El router contesta
  `traducir → "hola al inglés"`, con el idioma **atrás**, y `split_language()` solo lo leía
  adelante: "traducí hola al francés" iba a traducir el texto *"hola al francés"* al inglés.
  Ningún test lo veía porque todos usan dobles, y el doble contestaba lo que esperábamos.
  Ver **Traducir**, en `.claude/rules/consultas.md`.
- 🔴 **La regla de convertir duraciones no aplica a `decir` ni a `llamar`.** Al sumar los
  ejemplos de `recordar`, "avisá en el comedor que salgo en cinco minutos" empezó a volver
  como `decir → "... salgo en 5m"` seis de seis veces: `_faithful()` lo descartaba y el
  mensaje terminaba en `preguntar`. La regla decía "las duraciones y horas" sin nombrar
  comandos; ahora los nombra y excluye a los dos que llevan palabras de una persona. Un
  ejemplo nuevo mueve comportamientos que no toca: por eso se mide todo, no solo lo nuevo.
- 🔴 **Los ejemplos del prompt sostienen el comportamiento, no lo decoran.** Sin ellos el
  modelo dejaba el verbo adentro del payload: "decí que ya llegué" volvía como
  `decir → "decí que ya llegué"` y la casa se decía a sí misma la orden. Con cinco ejemplos,
  medido contra el endpoint real: **dieciséis de dieciséis comandos** y los tres payloads
  limpios; la última corrida dio cincuenta y uno de cincuenta y uno con los comandos que se sumaron después. Si se toca el
  prompt, se vuelve a medir.
- 🔴 **«para <persona>» lo pone el router adelante del argumento**, después del equipo si lo
  hay, en `timer`, `alarma` y `recordar`: «recordale a China…» es `para China diaria 8:00 …`.
  La regla del prompt aclara que «para mañana» y «para las ocho» no son una persona: el
  comando solo consume el «para» si lo que sigue es del padrón, pero un «para mañana» delante
  de la hora deja una orden que no parsea. Ver **Para quién suena**, en
  `.claude/rules/programado.md`.
- 🔴 **El router usa el modelo barato y sin búsqueda.** Interpretar no es averiguar, y cada
  mensaje suelto paga esta llamada: medido, **un segundo y tres**. Con búsqueda serían treinta
  segundos delante de "bajá el volumen". El que sí busca es `ASK_MODEL`, y solo cuando la
  cosa terminó siendo una pregunta.
- 🔴 **Que el router falle no es una pregunta.** Mandar "apagá la tele" a buscar en internet
  contestaría algo que nadie pidió, lento y con seguridad. Un `RouteError` sin hilo contesta
  `NOT_UNDERSTOOD` («No te entendí. Elegí un tema o escribilo de otra forma.») con los botones
  de los temas, no el texto del error; solo un "esto no era un comando" cae en `preguntar`.
  Una respuesta que no sirve al hilo contesta lo mismo.
- **Medido: el modelo rutea las preguntas a `preguntar`, no a "ninguno".** Los dos caminos
  terminan en `Commands.ask`, así que da igual, pero conviene saberlo antes de pelearse con
  el prompt por eso.
- **El `MessageHandler` se registra último y filtra `~filters.COMMAND`**, así un comando de
  verdad nunca llega al intérprete ni paga la llamada al modelo.
- **`Commands._dispatch()` vive con los comandos, no en el cableado de Telegram**: el router
  nombra un comando, y nombrar no es transporte. Hay test en las dos direcciones — que todo
  lo que el router puede pedir se pueda ejecutar, y que no haya nada ejecutable que el router
  nunca nombre. Sin eso, agregar un comando lo deja mudo al texto libre y nadie se entera.
- ⚠️ Sin la clave del proveedor de texto no hay intérprete: un mensaje suelto contesta
  `NO_ROUTER` («Así escrito no te entiendo. Elegí un tema.») con los temas.

## Notas de voz

Una nota de voz se transcribe y entra por `Commands.free_text()`, el mismo camino del texto
suelto: router, dato que falta, ejecución. `listen.py` es lo único nuevo.

- 🔴 **Transcribir no es interpretar.** El modelo devuelve las palabras dichas y nada más; qué
  comando son lo sigue decidiendo el router, con el prompt que ya está medido. Un segundo
  modelo decidiendo sería un segundo comportamiento que nadie midió.
- 🔴 **El audio sale de la casa.** Es la primera vez: Piper es offline y a Google solo le
  viajaba texto generado. Decisión del dueño, tomada contra la alternativa local —
  faster-whisper entra por poco en los 512 MB del CT y tarda entre cinco y quince segundos
  en un vCPU, con riesgo de OOM justo cuando alguien habla.
- **El que escucha es el modelo barato de Google**, `LLM_MODEL`, sin búsqueda, como el router.
- ⚠️ **Las notas de voz necesitan `LLM_API_KEY` aunque `LLM_PROVIDER` sea `anthropic`**: Claude
  no acepta audio. Sin esa clave el texto anda con Claude, una nota de voz contesta `NO_AUDIO`
  («No escucho audios. Escribime o elegí un tema.») con los temas, y el arranque lo deja en el log.
- **Se contesta qué se escuchó y qué se entendió**: `🎤 «...»` y abajo el `Entendí: /...`, o
  el «Listo:» de lo que se agendó. Con audio hay dos lugares donde se puede errar, no uno, así
  que los dos quedan a la vista.
- **Un audio de más de un minuto se rechaza sin bajarlo** (`MAX_VOICE_SECONDS`). Un comando
  dicho es una oración.
- **Lo que no se entiende no se adivina**: el modelo contesta `NADA` y el chat dice que no se
  entendió. Nunca se rutea una transcripción vacía.
- ⚠️ **El modelo escribe los números con dígitos.** Medido contra el endpoint real: "a las
  siete y media" vuelve como "7:30" y "cuarenta" como "40". Al router le viene bien, y en
  `/decir` lo arregla `correct.py`, que ya tiene la licencia de expandir un dígito a las
  palabras que lo dicen.
- ⚠️ El audio viaja en `inline_data` dentro del mismo POST que el prompt, en base64.

## Por dónde sale la respuesta

🔴 **El parlante dejó de ser el destino por defecto: se pide.** Una consulta contesta por
donde entró y nada más.

| Entra | Sale |
| --- | --- |
| texto | texto en el chat |
| nota de voz | nota de voz, y nada más |
| cualquiera de los dos, con «por el parlante» al final | además por los equipos |

- **`/decir` y `/llamar` no consultan la regla.** Pedirles que hablen *es* el comando; un
  `/decir` que no suena no es nada. Los que sí la consultan son los tres que antes hablaban
  sin que nadie se lo pidiera: `/clima`, `/agenda` y `/preguntar`.
- 🔴 **Las alarmas, los timers, el resumen de la mañana, el cierre del día y lo `urgent` del
  monitor siguen saliendo por el parlante**, siempre, más su copia al chat. Son lo que interrumpe a
  propósito: nadie pide a las tres de la mañana que la alerta suene. Lo demás del monitor y
  Seq solo se escribe a alertas: ver **Vigilancia**, en `.claude/rules/vigilancia.md`.
- 🔴 **En vacaciones no sale nada por el parlante**, ni lo urgente: todo eso va solo al chat.
  `/decir`, `/llamar` y lo pedido «por el parlante» contestan el motivo con el botón
  «Volví de vacaciones». Ver **Modo vacaciones**, en `.claude/rules/descanso-y-feriados.md`.
- 🔴 **La coletilla se saca antes de rutear.** El router arma el argumento del comando y se la
  comería, así que `free_text()` la detecta sobre el mensaje entero, la quita y deja puesto un
  `contextvars.ContextVar`. Va en un contextvar y no en el objeto porque es del pedido: dos
  mensajes se atienden a la vez. De paso, al modelo le llega el mensaje limpio.
- ⚠️ **La frase está anclada al final** (`aloud.py`). "El parlante del comedor anda mal" no es
  un pedido, y por eso no alcanza con buscar la palabra suelta. Se aceptan «por/en el
  parlante», «los parlantes», «el altavoz» y «en voz alta», con un conector opcional adelante
  («y decilo», «, reproducilo»).
- **Un audio se contesta con audio aunque además suene el parlante.** Vuelve por donde entró;
  que encima se escuche en casa no cambia eso.
- 🔴 **Se graba la mitad hablada, no la escrita.** Una receta pedida por audio volvió diciendo
  "quinientos ge de carne" y "un un medio morrón": se estaba grabando `answer.written`, que
  conserva todos los dígitos a propósito. `ask()` deja su `spoken` —ya validado— para el que
  grabe, y lo genérico solo se usa si el comando no dejó nada.
- 🔴 **Un texto con dígitos no se graba: vuelve escrito.** Es la misma regla de siempre, ahora
  en el segundo camino que llega a Piper. Tampoco se graba el "te lo dejé escrito en el chat"
  de `ask`: mandar ese audio sin mandar el chat sería una burla.
- 🔴 **La nota de voz no lee el «Entendí: /clima».** Grabar la respuesta entera le devolvía a
  la persona su propio pedido leído en voz alta. `_route_and_run()` deja en un contextvar lo
  que contestó el comando, y eso es lo único que se graba; qué entendió sigue escrito en el
  chat, que es donde se lee de un vistazo.
- **`opusenc` es un requisito del contenedor**, no de Python: Telegram solo muestra la burbuja
  de nota de voz para OGG/Opus. `deploy.sh` instala `opus-tools` si falta. Medido contra la
  API real: un wav de ochenta kilobytes queda en seis.
- **El mismo `VoiceSynth` para el parlante y para la nota de voz**, así una frase ya dicha no
  se sintetiza de nuevo para grabarla.
- 🔴 **A un audio le vuelve solo el audio.** Decisión del dueño: mandar además el texto era
  leer dos veces lo mismo. La burbuja de «procesando» se borra al mandar la nota de voz, así
  que el chat queda con el pedido y la respuesta hablada. Si no se pudo grabar —sin encoder,
  sin clave— vuelve el texto: la respuesta no se pierde, cambia de forma.
- ⚠️ **La presencia por WiFi se evaluó y se descartó.** Llegó a estar hecha —`presence.py`,
  ARP contra la IP del teléfono— y quedó sin función el día que el parlante pasó a pedirse:
  si solo suena cuando se lo piden, da igual dónde esté el dueño. Si algún día vuelve a hacer
  falta, el camino es ese y el router de casa es un TP-Link sin SSH.

## Que se note que está trabajando

Un mensaje que tarda —Piper, el modelo, el cast— parecía ignorado. Ahora el bot contesta
`⏳ Procesando…` apenas llega, y **edita esa misma burbuja** con la respuesta.

- 🔴 **El indicador de Telegram («escribiendo…») no sirve acá.** Fue el primer intento y se
  midió contra el chat real: ni mandando `sendChatAction` a mano, con `ok: true` de la API, se
  vio nada en el cliente del dueño. Un mensaje se ve siempre.
- **Se edita, no se suma.** Una burbuja por pedido: la de espera se convierte en la respuesta.
  Si editar falla, se manda la respuesta aparte — contestar no es negociable.
- **La señal no puede costar la respuesta**: si no se pudo avisar, el comando corre igual.

🔴 **Un error se contesta, no se calla.** Una excepción moría en el log como "No error handlers
are registered" y el mensaje quedaba sin respuesta: desde el teléfono se ve igual que un bot
colgado. Pasó de verdad: un llamado a varios equipos reventó con "Address already in use" y el
chat no dijo nada por dos minutos.

- 🔴 **El motivo técnico lo leen solo los chats de `alert_recipients`.** `commands.broken(exc,
  detail)` es la única forma del error genérico: con el motivo, «🔴 No pude procesar la
  solicitud: <qué pasó>»; sin él, «No me salió. Probá de nuevo en un rato.». La usan el
  comando, la nota de voz y el botón en `main.register()`, y `/control`. El motivo va
  siempre al log. Con `ALERT_CHAT_IDS` vacía, alertas son todos y todos lo leen.
- **Un equipo que falla dice «<Equipo>: no responde» a la familia**; el motivo, a alertas
  (`Commands._summary()`). Clima, traducir, preguntar y la nota de voz contestan una frase
  llana a todos y dejan el motivo en el log. La agenda, llana a la familia y con el motivo
  a alertas.
- 🔴 **Lo que falta configurar no le muestra la clave a la familia.**
  `Commands._unconfigured(chat_id, detail)`: alertas leen el detalle con la clave de
  entorno; los demás, «Esto todavía no está configurado. Avisale a <nombre>.», con los
  nombres del padrón de los chats de alertas unidos por «o a», o «quien maneja la casa» si
  no hay ninguno. Lo usan preguntar, traducir, menú, agenda, estado y `/pantalla` sin
  `API_TOKEN`.

- 🔴 **`MediaServer.start()` se llama desde un hilo por equipo.** `_broadcast` habla en
  paralelo y cada `Speaker` tiene su propio `_serving`, así que en el primer anuncio tras un
  reinicio los dos veían el servidor apagado, los dos bindeaban el puerto y el segundo moría.
  Lleva candado con doble chequeo, como el cache de síntesis.

## Conversación

Un mensaje al que le falta un dato obligatorio **no es un error, es media orden**: el bot
pregunta la otra mitad y se acuerda de lo que ya le dijeron. `slots.py` dice qué falta,
`pending.py` guarda el hilo, `Commands.free_text()` los junta.

- **Solo se pregunta lo que falta.** Un mensaje completo se ejecuta de una y avisa qué
  entendió, igual que antes: la decisión de no pedir confirmación sigue en pie. Es decisión
  del dueño de la casa, tomada junto con la de preguntar.
- 🔴 **El hilo se vuelve a rutear entero, con el mismo prompt.** La alternativa era un segundo
  prompt que fusionara la respuesta con el argumento a medio armar; se descartó porque el
  prompt del router **está medido** (la última corrida, cincuenta y uno de cincuenta y uno) y un segundo prompt es un segundo
  comportamiento que nadie midió. El precio es **una llamada más por turno**: un mensaje
  contestando una pregunta paga dos, la que decide si es un comando nuevo y la del hilo.
- 🔴 **Un dato no se pregunta dos veces.** Si la respuesta no lo trajo, se sigue de largo y el
  comando contesta con el error de su parser. Volver a preguntar lo mismo es un loop, y el
  parser lo explica mejor que la segunda pregunta.
- **Interrumpe un comando completo, no uno a medias.** "dame el clima" en medio de una alarma
  es un comando nuevo; algo dicho a medias es casi siempre el dato que faltaba. Se avisa que
  lo que estaba a medio armar se dejó.
- **`olvidalo` y sus variantes cortan sin pagar el modelo.** ⚠️ **`cancelá` no está en esa
  lista** a propósito: `/cancelar` lleva un número y usar la misma palabra para tirar un
  borrador se leería como cancelar una alarma ya puesta.
- **Vence a los diez minutos** (`pending.TTL`). Sin vencimiento, un "sí" de la nada contesta
  una pregunta de hace media hora y la alarma que sale de ahí no es de nadie.
- **Se guarda en SQLite, no en memoria**, por lo mismo que el silencio a pedido: un reinicio
  en medio de "¿a qué hora?" dejaría la respuesta sin a dónde volver.
- 🔴 **La repetición de una alarma se pregunta aunque el parser no la exija.** `/alarma 7:30
  arriba` es válido y agenda una sola vez; el pedido del dueño es que pregunte los días en vez
  de elegirlos en silencio. Es la única pregunta que no sale de una validación.
- ⚠️ **La forma de una alarma se mira en dos lados**, `slots._alarm()` y `Commands.alarm()`.
  Si se separan, el bot pregunta por algo que ya tenía o ejecuta algo que no puede.
  `tests/bot/test_conversation.py` los ata: lo que `slots` llama incompleto, el comando de
  verdad tiene que rechazarlo.
- **La persona nunca se pregunta.** `slots.missing()` recibe `unassign`
  (`Commands._without_assignee()`) y en `timer`, `alarma` y `recordar` (`slots.ASSIGNABLE`)
  mira el argumento sin el «para X»: si no, «para China» se leería como la hora o el mensaje
  que falta. Con un nombre fuera del padrón saca igual las palabras del nombre, y el comando
  contesta el error.
- 🔴 **Las preguntas van al chat, nunca al parlante**, así que son la excepción a la regla de
  los dígitos: "¿Cuál borro? El número sale en /lista, Mis avisos." se lee, no se dice.
- ⚠️ **La fidelidad de `decir` pasa a medirse contra el hilo entero.** La respuesta llega en el
  mensaje de después; comparando solo contra el último renglón, "que bajen a comer" no
  estaría y la casa se quedaría sin decir algo que la persona sí escribió.
- **Sin `Conversation` cableada, todo se comporta como antes**: un comando incompleto sale con
  el error del parser. La conversación es una pieza opcional del constructor, como el resto.

## Inicio y temas

`/inicio` y `/start` contestan `home()`: «¿Qué querés hacer? …» y un botón por tema de
`TOPICS`. Un tema (`tema <clave>`) muestra sus botones y «⬅ Temas», que vuelve al inicio.

- **Siete temas**: ⏰ Avisos, 🗣 Hablar en la casa, 🛒 Compras y comida, 📅 Hoy, ❓ Preguntar,
  🤫 Silencio y ⚙️ Ajustes. **«Ajustes» solo lo ven los chats de `alert_recipients`**
  (`_topics()`); a otro chat, `tema ajustes` contesta «No conozco ese tema.». ⚠️ Con el bot
  abierto `alert_recipients` está vacía y nadie ve «Ajustes».
- 🔴 **`Commands.topics_for(chat_id)` son los mismos temas para `/control`**: la web los
  muestra como tarjetas con estos botones, así que un botón que se suma o se saca de `TOPICS`
  cambia los dos transportes. Ver **Control desde la web**, en `.claude/rules/web.md`.
- **«🗣 Hablar en la casa» tiene «Apagar la tele o el parlante»** (`apagar`), al lado de
  «Callar el parlante» (`parar`): callar corta lo que suena, apagar cierra la app y deja el equipo en reposo.
- **Un botón de tema corre un comando o lo deja armado.** «Mis avisos» manda `lista`; «Avisame
  en…» manda `armar timer`. `arrange()` guarda el pendiente con la pregunta del dato que falta
  (`slots.missing()`, o `slots.QUESTION` para `preguntar`, que escrito no tiene dato
  obligatorio) y la devuelve. Sin `Conversation`, corre el comando vacío.
- 🔴 **Dos formas de armar** (`ARRANGEABLE`). `timer`, `alarma` y `recordar` siembran el hilo
  con una frase («poneme un timer», «creá una alarma», «creá un recordatorio que se repite»)
  y la respuesta pasa por el router con el mismo prompt, como cualquier hilo. Los demás
  —`decir`, `volumen`, `agregar`, `preguntar`, `calcular`, `traducir`, `usar`— guardan el hilo
  vacío, y `_run_arranged()` corre el comando con la respuesta tal cual, sin el modelo y sin
  «Entendí:».
- ⚠️ **Las tres frases semilla no están medidas en el CT.** El prompt no cambió, pero el hilo
  que ve el router arranca con una frase que ninguna corrida de `measure_router.py` incluye.
  Si el router lee mal la respuesta de un botón de Avisos, el primer sospechoso es la semilla.
- ⚠️ **Un hilo vacío no se interrumpe**: lo que se escriba después del botón es el argumento,
  aunque sea otro comando completo. Solo `olvidalo` y sus variantes lo cortan.
- **`/ayuda` es la ayuda corta** (`HELP_SHORT`): ejemplos escritos como se le habla a alguien
  y los temas abajo. `/ayuda completa` devuelve `HELP`, el catálogo entero.
- **Las respuestas de «no entendí» ofrecen los temas** y no nombran `/ayuda`:
  `NOT_UNDERSTOOD`, `NO_ROUTER` y `NO_AUDIO`.

## Comandos y alias

`ALL_COMMANDS` tiene 48 nombres: 33 comandos, 5 temas que no son comando propio
(`TOPIC_COMMANDS`: `avisos`, `parlante`, `comida`, `hoy`, `ajustes`) y 10 **alias** (`help`,
`tiempo`, `donde`, `volume`, `stop`, `start`, `siesta`, `pregunta`, `llama`, `convertir`). Los
alias funcionan pero no van al menú de Telegram: verlos duplicados al escribir `/` no ayuda a
nadie.

🔴 **El menú de Telegram es un comando por tema**, ocho (`COMMAND_MENU`): `inicio`, `avisos`,
`parlante`, `comida`, `hoy`, `preguntar`, `silencio` y `ayuda`. Una lista de comandos sueltos
era un catálogo que nadie lee; los temas llevan a los botones. Lo demás —`OUT_OF_MENU` en
`tests/bot/test_command_menu.py`— **sigue andando escrito**, se alcanza sin barra por el
router y casi todo está en los botones de su tema.

- **Los chats de alertas ven `MENU_ALERTS`**: el mismo menú más `ajustes`. `build_post_init()`
  lo publica chat por chat con `BotCommandScopeChat`; un chat que falla queda en el log y no
  frena el arranque ni a los otros. ⚠️ Nada borra ese menú: un chat que deja de ser de
  alertas lo conserva hasta que se le publique otro.
- **`preguntar` y `silencio` son comando y tema a la vez.** Vacíos, contestan lo suyo y suman
  los botones del tema (`_offer_topic()`). Eso vive en `Commands`, así que vale también en
  `/control`.
- **`HELP` es el catálogo completo**, y sale con `/ayuda completa`. Un comando que no está en
  el menú tiene que seguir en la ayuda o queda invisible; el test ata `OUT_OF_MENU` con `HELP`.
- **`/compras` nombra a `/sacar`**: quien ve la lista ahí mismo lee cómo sacar de ella.
  `/lista` ya no nombra a `/cancelar`: borra con sus botones.
- **`depurar` está en `HELP` y en «Ajustes», no en el menú**: es solo para los chats de
  alertas. Sus botones `depurar ok <token>` y `depurar no <token>` los desvía `press()` a
  `purge_confirm()` y `purge_drop()`. Ver `.claude/rules/depurador.md`.
- **`hecho`, `borrar`, `callar` y `confirmar` no están en `ALL_COMMANDS`**: son solo botones, en
  `Commands.press()`. Ni se escriben ni los nombra el router. Lo mismo `tema` y `armar`.
- **`ayuda` e `inicio` son comandos de Telegram y además botones** (`HELP_BUTTON`,
  `HOME_BUTTON`): en `press()` corren `help()` y `home()`, y una clave de `TOPICS` corre
  `topic()`. En Telegram los cablea `main.py` y no están en `_dispatch()`. No son de
  `CHATLESS_BUTTONS`: sin Telegram, `press_without_chat()` contesta `CHATLESS_ONLY`.
- **`Commands.typed(name)` dice qué se puede escribir con barra fuera de Telegram**: `ayuda`,
  `inicio`, una clave de `TOPICS` o un nombre de `_dispatch()`. Los botones de solo-botón y los
  alias de `main.py` quedan afuera. Lo usa `/control`; ver **Control desde la web**, en
  `.claude/rules/web.md`.
