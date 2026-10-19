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
  cambió de firma, y el «Entendí: /alarma …» del texto libre y la nota de voz heredan los
  botones del comando que corrieron sin hacer nada.
- **Qué ofrece cada uno**: lo programado —`/timer`, `/alarma`, `/posponer`— trae «Cancelar
  #N», que es el deshacer que ya prometía el «Entendí:»; `/lista`, un «Cancelar #N» por
  cada uno; `/compras` y `/pendientes`, un «✓ ítem» por cada uno y «Vaciar».
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
  La respuesta arranca con `Entendí: /timer 10m sacá la pizza` para que una lectura errada se
  vea, y `/cancelar` es el deshacer. Lo único que se pregunta antes es un dato que falta —ver
  **Conversación**—, y eso no es confirmar: es no inventarlo.
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
- ⚠️ **«recordame comprar los pasajes de las vacaciones» acepta `recordar` o `agregar`.** El
  caso está para que no vaya a `vacaciones`. Con el ejemplo de `pantalla`, una de cada seis
  veces se va a pendientes, y sin hora es una lectura razonable. Un caso de la medición puede
  llevar una tupla de comandos válidos.
- ⚠️ **Un `Read timed out` de la API en la medición no es el prompt**: el router corta a los
  seis segundos y el caso sale como `RouteError`. Se vuelve a correr.
- ⚠️ **La medición usa el `LLM_MODEL` del env del CT.** Con un modelo que la API no acepta, las
  cuarenta y dos llamadas dan `400` y el resultado es cero: es el modelo, no el prompt.
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
  limpios; hoy son cuarenta y dos de cuarenta y dos con los comandos que se sumaron después. Si se toca el
  prompt, se vuelve a medir.
- 🔴 **El router usa el modelo barato y sin búsqueda.** Interpretar no es averiguar, y cada
  mensaje suelto paga esta llamada: medido, **un segundo y tres**. Con búsqueda serían treinta
  segundos delante de "bajá el volumen". El que sí busca es `ASK_MODEL`, y solo cuando la
  cosa terminó siendo una pregunta.
- 🔴 **Que el router falle no es una pregunta.** Mandar "apagá la tele" a buscar en internet
  contestaría algo que nadie pidió, lento y con seguridad. `RouteError` sale como texto y
  apunta a `/ayuda`; solo un "esto no era un comando" cae en `preguntar`.
- **Medido: el modelo rutea las preguntas a `preguntar`, no a "ninguno".** Los dos caminos
  terminan en `Commands.ask`, así que da igual, pero conviene saberlo antes de pelearse con
  el prompt por eso.
- **El `MessageHandler` se registra último y filtra `~filters.COMMAND`**, así un comando de
  verdad nunca llega al intérprete ni paga la llamada al modelo.
- **`Commands._dispatch()` vive con los comandos, no en el cableado de Telegram**: el router
  nombra un comando, y nombrar no es transporte. Hay test en las dos direcciones — que todo
  lo que el router puede pedir se pueda ejecutar, y que no haya nada ejecutable que el router
  nunca nombre. Sin eso, agregar un comando lo deja mudo al texto libre y nadie se entera.
- ⚠️ Sin `LLM_API_KEY` no hay intérprete: un mensaje suelto contesta que los comandos están
  en `/ayuda`.

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
- **El que escucha es el modelo barato**, `LLM_MODEL`, sin búsqueda, como el router.
- **Se contesta qué se escuchó y qué se entendió**: `🎤 «...»` y abajo el `Entendí: /...`. Con
  audio hay dos lugares donde se puede errar, no uno, así que los dos quedan a la vista.
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
- 🔴 **Las alarmas, los timers, el resumen de la mañana, el cierre del día y los avisos del
  monitor y de Seq siguen saliendo por el parlante**, siempre, más su copia al chat. Son lo que interrumpe a
  propósito: nadie pide a las tres de la mañana que la alerta suene.
- 🔴 **En vacaciones no sale nada por el parlante**, ni lo urgente: todo eso va solo al chat.
  `/decir`, `/llamar` y lo pedido «por el parlante» contestan el motivo con la pista
  `/vacaciones off`. Ver **Modo vacaciones**, en `.claude/rules/descanso-y-feriados.md`.
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
colgado. Ahora vuelve `🔴 No pude procesar la solicitud: <qué pasó>`, con el motivo adentro.
Pasó de verdad: un llamado a varios equipos reventó con "Address already in use" y el chat no
dijo nada por dos minutos.

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
  prompt del router **está medido** (cuarenta y dos de cuarenta y dos) y un segundo prompt es un segundo
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
- 🔴 **Las preguntas van al chat, nunca al parlante**, así que son la excepción a la regla de
  los dígitos: "¿Cuál cancelo? El número sale en /lista" se lee, no se dice.
- ⚠️ **La fidelidad de `decir` pasa a medirse contra el hilo entero.** La respuesta llega en el
  mensaje de después; comparando solo contra el último renglón, "que bajen a comer" no
  estaría y la casa se quedaría sin decir algo que la persona sí escribió.
- **Sin `Conversation` cableada, todo se comporta como antes**: un comando incompleto sale con
  el error del parser. La conversación es una pieza opcional del constructor, como el resto.

## Comandos y alias

`ALL_COMMANDS` tiene 40 nombres: 30 comandos y 10 **alias** (`help`, `tiempo`,
`donde`, `volume`, `stop`, `start`, `siesta`, `pregunta`, `llama`, `convertir`). Los alias
funcionan pero no van al menú de Telegram: verlos duplicados al escribir `/` no ayuda a nadie.

🔴 **El menú de Telegram tiene 10, no los 30.** `recordar` entró como el décimo, y es el
tope que fija el test. Con los 18, la lista que sale al escribir `/`
era un catálogo que nadie lee, y los que se perdían adentro eran justo los que llevan
argumento. Quedan los que se escriben a propósito; los otros —`timer`, `cancelar`, `volumen`,
`parar`, `apagar`, `clima`, `agenda`, `estado`, `usar`, `calcular`, `agregar`, `pendientes`,
`sacar`, `traducir`, `posponer`, `pastillas`, `vacaciones`, `turnos`, `pantalla`— **siguen andando escritos** y se alcanzan sin barra por el router.

- **`HELP` es el catálogo completo**, y por eso `/ayuda` está en el menú. Un comando que se
  va del menú tiene que seguir en la ayuda o queda invisible; `tests/bot/test_command_menu.py`
  ata las dos mitades.
- **`/lista` nombra a `/cancelar` y `/compras` nombra a `/sacar`.** Son las salidas del menú
  que dejan a otro comando sin puerta: quien ve la lista ahí mismo lee cómo borrar de ella.
- **`hecho`, `borrar`, `callar` y `confirmar` no están en `ALL_COMMANDS`**: son solo botones, en
  `Commands.press()`. Ni se escriben ni los nombra el router.
