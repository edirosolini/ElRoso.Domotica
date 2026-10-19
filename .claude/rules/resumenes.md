---
paths:
  - "src/homeauto/briefing.py"
  - "src/homeauto/closing.py"
  - "src/homeauto/weekly.py"
  - "src/homeauto/economy.py"
  - "src/homeauto/news.py"
  - "src/homeauto/bible.py"
  - "src/homeauto/main.py"
  - "tests/test_briefing.py"
  - "tests/test_briefing_seq.py"
  - "tests/test_closing.py"
  - "tests/test_weekly.py"
  - "tests/test_economy.py"
  - "tests/test_news.py"
  - "tests/test_config_news.py"
  - "tests/test_bible.py"
---

# Resumen, cierre y semanal

## Resumen de la mañana

`briefing.py` junta el feriado, agenda, clima, economía, servicios caídos, titulares y el
versículo del día en un solo texto hablado, a la hora de `BRIEFING_AT` (08:45 en el CT).

- **Las fuentes son independientes.** Una que falla deja un hueco, no cancela el
  resumen: un calendario que no contesta no te puede costar el clima. Es la misma postura
  que dentro de `agenda/`, donde un calendario roto no tapa a los otros.
- 🔴 **Desde las noticias, el resumen tiene dos mitades.** `speech()` devuelve `spoken` y
  `written`, la misma separación de `seq.Summary` y `ask.Answer`. Acá la diferencia son los
  titulares, que **solo van al chat**. `text()` sigue existiendo y es la mitad hablada, para
  no romper a quien solo quiere eso.
- 🔴 **La agenda del resumen no dice el lugar**, solo la hora y el título. Escuchado junto al
  clima, la economía y lo que esté caído, "en Sanatorio Colegiales" era lo que lo hacía
  arrastrarse. `/agenda`, que se pide a propósito, lo sigue diciendo: es el argumento `place`
  de `speech.describe()`.
- 🔴 **Los servicios caídos y los errores de la noche solo se escriben a los chats de
  alertas** (`ALERT_CHAT_IDS`). `Summary.public` es la copia del resto: sin esas dos
  fuentes y, si no queda nada, con el "No tengo nada" de siempre. ⚠️ **Lo hablado no cambia**:
  el parlante los dice igual y se escuchan en toda la casa.
- **Un párrafo por fuente, escrito y hablado.** En el chat es una línea en blanco; en el
  parlante, la pausa de punto y aparte de `VoiceSynth`. Pegado, el resumen era un bloque que
  no se podía leer de un vistazo ni seguir de oído.
- **No depende de la agenda.** El job del resumen se agenda aunque no haya ningún calendario
  configurado. Por eso está fuera de `schedule_calendar_jobs()`.
- **De los servicios solo se nombran los caídos.** Escuchar "todo en orden" cada mañana
  enseña a no escuchar; el estado completo está en `/estado`.
- 🔴 **Los errores de la noche se recuerdan acá**, y es la razón de que de madrugada no
  despierten a nadie. Se piden a los mismos clientes que vigilan de día, de las últimas doce
  horas (`NIGHT_HOURS`). Sin "Atención, producción" adelante: el fuego ya pasó, esto lo
  recuerda —para eso `summarize()` acepta `lead=False`—. Una noche tranquila no dice nada,
  igual que los servicios en orden.
- El texto se sintetiza, así que **no lleva dígitos**: las fuentes ya hablan en palabras y
  este módulo solo agrega nombres y conectores. Hay test que lo verifica.
- **Un feriado abre el resumen**: «Hoy es feriado: <motivo>.», escrito y hablado, también
  en la copia pública. Un puente dice «Hoy es día no laborable.». Sale de la caché local,
  sin pedido a la red; ver **Feriados**, en `.claude/rules/descanso-y-feriados.md`.

## Cierre del día

`closing.py` es el espejo del resumen a la hora de `CLOSING_AT` (20:00 en el CT, 22:00 por
defecto): lo agendado para **mañana**, el pronóstico de **mañana** y lo que sigue caído.

- 🔴 **Un cierre vacío no se dice.** Es la única diferencia de forma con el resumen, que
  contesta "No tengo nada para el resumen de hoy": a la mañana ese texto avisa que la casa
  está viva, a las diez de la noche es hablar por hablar. `text()` devuelve `""` y `main()`
  no anuncia nada.
- 🔴 **Mira para adelante, no para atrás.** Por eso no lleva economía, titulares ni los
  errores de Seq: el día ya pasó y esas tres son noticias de la mañana. Lo que entra es lo
  que cambia un plan antes de dormir, y por eso se sumó **cuánto falta comprar**.
- 🔴 **La línea de los servicios caídos solo se escribe a los chats de alertas**, igual que
  en el resumen: `speech()` devuelve la copia del resto en `public`. Si lo único que había
  era un servicio caído, al resto no le llega nada, por la misma regla del cierre vacío.
- ⚠️ **De la lista de compras solo se dice el conteo**, en palabras. Los ítems se leen en
  `/compras`: dictar quince productos es exactamente el error que se evitó con los titulares.
- **La agenda se pide con `place=False`**, igual que en el resumen y por lo mismo: escuchado
  de corrido, "en Sanatorio Colegiales" lo hace arrastrarse. `AgendaService.spoken()` ahora
  acepta ese argumento; `/agenda` lo sigue diciendo.
- **El clima de mañana sale del índice uno de `daily`**, que ya viajaba en el mismo pedido
  desde que `RainWatcher` pidió `forecast_days=2`. No cambia ningún parámetro de la API; sí
  es un pedido más por día, igual que cada watcher.
- 🔴 **La línea de los servicios caídos es una sola**, `watch.monitor.down_line()`, y la usan
  el resumen y el cierre. Estaba escrita dos veces por un rato y esa es exactamente la forma
  en que las dos redacciones se separan sin que nadie lo note.
- 🔴 **La hora se elige mirando `QUIET_FROM`, no el default.** El default son las 22:00, que
  es la hora exacta en que empieza el descanso de esta casa: el cierre habría salido mudo
  todas las noches. En el CT quedó a las 20:00. Pasado `QUIET_FROM` el aviso solo se escribe,
  que es la regla de siempre y no una falla.
- Fuentes independientes y nada de dígitos, como el resumen. Hay test de las dos cosas.

## Resumen semanal

`weekly.py` lee siete días de `fired_history` y arma un balance a la hora de `WEEKLY_AT`
(por defecto `dom 19:00`; acepta días como una alarma, `lun-vie 9:00`, y `off` lo apaga).

- 🔴 **Solo se escribe, a todos** (`tell_everyone`). No pasa por el parlante ni por el
  pulidor, así que es la excepción a la regla de los dígitos: "5 de 7" se lee de un vistazo.
- **Una semana vacía no manda nada**, por la misma regla del cierre vacío.
- **Tres bloques, cada uno solo si tiene algo**: cuántos días se marcó «Hecho» cada
  recordatorio (`mensaje: 5 de 7`), las alarmas que nadie apagó y lo que no salió por el
  parlante (`announced = 0`).
- 🔴 **Un recordatorio se cuenta por mensaje y por día.** El día es hecho si alguna de sus
  filas cerró en `done`. Lo pospuesto vuelve como `reminder` de una sola vez, y suma al
  recordatorio que repite con el mismo mensaje: si no, posponer y después marcar «Hecho»
  contaría ese día como olvidado.
- **Los timers quedan afuera**, de los tres bloques. ⚠️ Un timer con el mismo mensaje que un
  recordatorio que repite no se distingue de un pospuesto y entra.
- **Alarma que nadie apagó** es la que repitió (`nags >= 1`), sigue sin cerrar y ya pasó
  `RING_LIMIT`: es la fila que deja abierta el tope. Ver **Historial de lo que sonó**, en `.claude/rules/programado.md`.
- **Las alarmas sin apagar y lo no dicho llevan tope de diez renglones** (`MAX_LINES`, con
  "… y N más"); los recordatorios, uno por mensaje y sin tope. Todo mensaje se corta a
  cuarenta caracteres (`MAX_MESSAGE`).
- 🔴 **PTB numera los días de 0 = domingo a 6 = sábado**, no ISO. `schedule_weekly()`
  convierte con `iso % 7`: de lunes a sábado coinciden y el domingo es 7 de un lado y 0 del
  otro, así que el error solo aparece con un domingo, que es el default.
- **Las 19:00 del default quedan fuera del cierre del CT (20:00) y del descanso (22:00).**
- **Lo salteado por feriado no cuenta** (`closed = holiday`): no sonó a propósito, y contado
  sería un recordatorio olvidado o algo que no salió por el parlante.

## Economía

`economy.py` dice tres números a la mañana: dólar oficial, riesgo país e inflación del último
mes publicado. Salen de dolarapi y argentinadatos, gratis y sin cuenta, la misma postura que
Open-Meteo: nada de lo que la casa dice todos los días depende de la clave de alguien.

- 🔴 **Los tres son independientes entre sí**, no solo del resto del resumen. El dólar caído
  no cuesta la inflación.
- 🔴 **Un número que no se puede decir en palabras se calla.** `verbalize` levanta `ValueError`
  pasado su rango y esa negativa termina acá: dejarla pasar pondría un dígito frente a Piper,
  que es exactamente lo que este módulo viene a evitar. Si algún día el dólar pasa el millón,
  la casa se queda callada en vez de leer mal.
- **Se pule**, como el clima y la agenda, con el nombre de cada cifra en `must_keep`.
- ⚠️ El dólar se dice al precio de **venta**, que es lo que cuesta comprar uno.

**`verbalize` llegó hasta acá por esto.** Antes cortaba en novecientos noventa y nueve, así
que ninguna cifra de plata podía sonar: `number(1545)` era un `ValueError`. Ahora llega al
millón y hay `decimal()` para la inflación —"dos coma uno"—, porque escrito con coma el
sintetizador dice dos números sueltos y se come el signo.

- **`mil` y `coma` son palabras-dato.** Entraron a `DATA_WORDS` con las cifras: perder un
  "mil" mueve un precio tres órdenes de magnitud, y perder la coma lo convierte en otro
  número. Es la misma protección que ya tenían los momentos del día.
- ⚠️ **En un decimal ninguna mitad se apocopa**: es "uno coma cuatro por ciento", nunca "un
  coma cuatro". El sustantivo va después de toda la cifra, no pegado al primer número.

## Noticias

`news.py` lee el RSS de los medios configurados (`NEWS_RSS_<MEDIO>`, una clave por medio,
como los calendarios y los Seq) y arma los titulares del resumen.

- 🔴 **RSS y no un modelo contestando "qué pasó hoy".** De cada línea se sabe qué medio la
  publicó, y eso es lo que la hace verificable. El modelo entra después y solo para cambiar
  cómo suena, nunca para decidir qué pasó.
- 🔴 **Los titulares no se dicen nunca: van solo al chat.** Decisión del dueño, tomada
  después de escucharlos: son lo más largo del resumen y lo único que no se puede accionar,
  y están hechos de precios, años y porcentajes. Por eso este módulo **no habla con ningún
  modelo**: poner un titular en palabras era un prompt, una validación y un timeout enteros
  para decir en voz alta algo que se lee mejor.
- **Los medios toman turnos.** Los cinco primeros de un solo diario son su portada, no las
  noticias del día. Un medio caído deja su turno vacío y los otros siguen.
- 🔴 **Se leen los bytes, nunca `response.text`.** Ámbito contesta sin charset en el header:
  requests adivina latin-1 y "Envíos" llega al chat como "EnvÃ­os". El XML declara su
  encoding, y entregarle los bytes al parser es lo que permite creerle.
- ⚠️ **Algunos medios contestan 403 sin `User-Agent`.** Clarín es uno. Verificado el
  2026-09-10: Infobae (`arc/outboundfeeds/rss/`), Ámbito y La Nación andan; los RSS de
  Página 12, Perfil y Télam están muertos.

## Versículo del día

`bible.py` trae el versículo del día de YouVersion en la **Nueva Traducción Viviente**
(versión `127`) y lo pone **al final** del resumen hablado. Decisión del dueño: se dice y se
escribe, y cierra el resumen.

- 🔴 **`bible.com` no se puede leer.** La página contesta un "Client Challenge" que pide
  JavaScript, y la API oficial de YouVersion pide una app key. Se usan dos endpoints internos
  de `nodejs.bible.com`, sin clave: `moments/votd` da las referencias de los 366 días y
  `bible/verse` da el texto limpio de una referencia en una versión. ⚠️ **No tienen
  contrato**: el día que cambien, el versículo deja un hueco en el resumen y nada más.
- **El día se busca por `tm_yday`.** Verificado el 2026-09-23: el día doscientos sesenta y
  seis es `PSA.19.14`.
- **El texto va literal**, como el título de un evento: no pasa por el pulidor. Solo la
  referencia se pone en palabras: "de Salmos, capítulo diecinueve, versículo catorce". Para
  eso existe `verbalize.cardinal()`, porque "capítulo un" es lo que diría `number()`.
- ⚠️ **Lo único que se toca del texto es la caja.** "SEÑOR" en mayúsculas se deletrearía, así
  que lo hablado dice "Señor"; en el chat queda como lo publicó la NTV.
- **Los libros numerados se dicen con ordinal**: las cartas en femenino ("Primera de Juan",
  "Segunda de Corintios") y el resto en masculino ("Primero de Samuel", "Segundo de
  Crónicas").
- **Un rango es de como mucho tres versículos seguidos del mismo capítulo**, verificado
  contra la lista del año entero. Se pide uno por uno y se dice "versículos dieciocho al
  diecinueve".
- 🔴 **Un versículo con un dígito no se dice: queda escrito**, con su referencia y `(NTV)`.
  Los setenta y cinco días con rango o libro numerado se probaron contra el endpoint real y
  se pueden decir todos.
- **Hablado, no se repite en el chat**: la copia escrita del resumen ya lo lleva.
- `VERSE=off` lo apaga, como `ECONOMY`.
