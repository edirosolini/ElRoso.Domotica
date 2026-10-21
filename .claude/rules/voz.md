---
paths:
  - "src/homeauto/verbalize.py"
  - "src/homeauto/polish.py"
  - "src/homeauto/claude.py"
  - "src/homeauto/correct.py"
  - "src/homeauto/summon.py"
  - "src/homeauto/voice/**"
  - "src/homeauto/schedule/announcer.py"
  - "src/homeauto/main.py"
  - "tests/voice/**"
  - "tests/test_verbalize.py"
  - "tests/test_polish.py"
  - "tests/test_claude.py"
  - "tests/test_correct.py"
  - "tests/test_summon.py"
  - "tests/bot/test_say_correction.py"
  - "tests/bot/test_call_command.py"
  - "tests/schedule/test_announcer.py"
---

# Voz y texto hablado

## Texto hablado

🔴 **Nada que vaya al sintetizador puede llevar un dígito.** Piper lee el número como
cardinal masculino suelto: `"tenés 1 cosa"` sonaba **"tenés uno cosa"**, `"a las 21"` sonaba
"a las veintiuno" y `"21 grados"`, "veintiuno grados". El bug estaba en los cuatro módulos que
generan texto, porque todos escribían el número con `f"{n}"`.

`verbalize.py` lo resuelve: `number(n, gender)` y `clock(hora, minuto)` devuelven palabras.

- **`number()` devuelve la forma que acompaña a un sustantivo**, que es el único caso que
  este proyecto tiene: `1` → `"un"` / `"una"`, `21` → `"veintiún"` / `"veintiuna"`. El cardinal
  suelto ("uno") no se usa nunca. Por eso el género es obligatorio de pensar en cada llamada:
  "cosa" es femenino, "minuto" y "grado" masculinos.
- **Las horas se dicen con franja**: `clock(21, 15)` → "las nueve y cuarto de la noche".
  Se soporta "y cuarto" y "y media"; **"menos cuarto" no**, a propósito — obligaría a correr la
  hora y con ella la franja, y "las nueve y cuarenta y cinco" ya se entiende.
- Vive en la **raíz del paquete**, no en `voice/`. Es una utilidad de idioma, no del parlante:
  `agenda/` y `weather.py` la usan, y `voice/` es el subpaquete de un dispositivo.
- ⚠️ **El título del evento va literal.** Solo se verbaliza lo que generamos nosotros. Un
  anuncio de agenda tiene que decir exactamente lo que dice el calendario; reescribirlo sería
  peor que leer mal un número.
- **El texto de `/decir` ya no va literal**: pasa por `correct.py`, que arregla cómo está
  escrito sin cambiar las palabras. Ver **Corrección de lo que escribe una persona**.

Hay test que verifica que **ningún dígito** sobrevive en el texto que arma la agenda, el clima,
el resumen de la mañana, el aviso del monitor ni el de Seq.

🔴 **Lo hablado y lo escrito no son lo mismo en los avisos de vigilancia.** El detalle de una
sonda (`HTTP 503 en 1.24s`) y la cita de un log de Seq son texto arbitrario: sirven leídos y
son ilegibles dichos, además de estar llenos de dígitos. El monitor y `SeqWatcher` mandan el
detalle aparte, y `HouseVoice.announce(written=...)` lo suma solo a la copia del chat.
`seq.Summary` existe para eso: `spoken` y `detail`.

### Pulido de la redacción

`polish.py` le pasa el texto **generado** al modelo de texto para que suene más natural antes
de sintetizarlo. El volumen real son decenas de llamadas por día: con Google, el free tier
alcanza y sobra.

- 🔴 **El original siempre gana.** Sin clave, sin red, con timeout o con una respuesta
  sospechosa, se dice el texto que ya había. Esto es decoración sobre un camino que tiene que
  funcionar: nadie puede quedarse sin aviso porque un modelo estaba lento.
- 🔴 **`/decir` es lo único que no pasa por el pulidor.** Todo lo demás que la casa dice sí:
  agenda, clima, avisos de evento, el mensaje de un timer o una alarma, los avisos del
  monitor, el resumen de Seq, el aviso de lluvia, la línea de servicios caídos del resumen y
  lo que entra por la API. Lo de `/decir` **no es que vaya literal**: va por `correct.py`,
  que es otra cosa —corrige la escritura, no puede cambiar una palabra—. Las dos decisiones
  son del dueño de la casa.
- ⚠️ Consecuencia de lo anterior: **el mensaje de un timer se reescribe.** "sacá la pizza"
  puede volver como "es hora de sacar la pizza". La validación protege los datos duros, no
  impide esa licencia. Si molesta, el cambio es sacar `polish` del `Announcer`.
- 🔴 **Lo que se pule tiene que estar limpio de dígitos primero, o el pulido es un adorno
  muerto.** La validación descarta cualquier respuesta con dígitos, así que un texto de
  entrada con "HTTP 503 en 1.24s" garantiza que toda reescritura se tire y se diga el
  original. Por eso el monitor y Seq separan lo hablado del detalle escrito.
- **La respuesta se valida antes de usarla.** Se descarta si trae dígitos, si crece o se
  encoge demasiado, si pierde un término que debía sobrevivir, o si cambia una
  **palabra-dato**. `verbalize.DATA_WORDS` define ese vocabulario: números, fracciones de hora
  y momentos del día. Cambiar "de la mañana" por "de la tarde" mueve una cita medio día.
- 🔴 **`un` y `una` quedan fuera de ese vocabulario a propósito.** También son el artículo
  indefinido, que un reescritor usa todo el tiempo: "con **una** máxima de veinte" se leía
  como dos números inventados y descartaba una reescritura correcta. No se pierde protección,
  porque un conteo que cambia de verdad hace entrar o salir otra palabra-número
  ("una cosa" → "dos cosas"), y eso se sigue viendo.
- ⚠️ `menos` sigue adentro y es el otro ambiguo: "más o menos" puede provocar un descarte.
  Es inocuo —se dice el texto original— y sacarlo dejaría pasar que a "menos tres grados" le
  coman el signo.
- **La respuesta se cachea por texto de entrada**, o se rompe el cache de síntesis: `VoiceSynth`
  cachea por frase y una redacción distinta cada vez significaría sintetizar siempre.
- La clave viaja en el header `x-goog-api-key`, **nunca en la query string**, que terminaría
  en cualquier log que registre la URL.
- `GoogleModel` acepta `system`: a Gemini le va como `systemInstruction`; a Gemma, que **no
  acepta system instruction**, pegado adelante del turno de usuario. Hoy ningún prompt lo usa:
  todos viajan enteros como turno de usuario.
- 🔴 **Gemma 4 no sirve acá, aunque sea el modelo obvio.** Razona antes de cada respuesta y
  **no se puede apagar**: la API rechaza `thinkingBudget` y `thinkingLevel` con un 400.
  Medido contra el endpoint real, tardó **entre 40 y 79 segundos** en reescribir una frase,
  gastando miles de tokens de razonamiento para emitir veinte. El default es
  `gemini-3.1-flash-lite` con el razonamiento apagado, que contesta lo mismo en **menos de
  dos segundos**. Si igual se configura un Gemma, se lo llama **sin** el switch: mandárselo
  haría fallar cada reescritura en silencio.
- 🔴 **Un modelo que razona devuelve el razonamiento en otra `part`, marcada `thought`.**
  Concatenar las partes le mandaba al parlante cientos de palabras de deliberación. Se filtran.
- **La comparación de `must_keep` ignora mayúsculas**: el modelo baja los títulos a minúscula
  y eso no pierde ningún dato.
- ⚠️ La validación protege los **datos duros** (números, horas, momentos del día, títulos), no
  impide una reinterpretación leve: a "Atención: Dentista, en diez minutos" le contestó
  "Tenés turno con el dentista en diez minutos", que agrega la palabra "turno". Es la licencia
  que se le pide; si algún día molesta, se endurece el prompt.
- El pulido hace una llamada HTTP bloqueante, pero cuelga de caminos que **ya** corren en
  `asyncio.to_thread` (los comandos, los watchers, el briefing y el disparo de una alarma).
  No agregar un llamador nuevo que lo invoque desde el event loop.
- ⚠️ La API también pule, así que un aviso urgente puede tardar hasta el timeout de seis
  segundos más de lo que tardaba. El original igual sale: es demora, no pérdida.

### Proveedor del texto

`LLM_PROVIDER` elige quién escribe el texto: `google` (default) o `anthropic`. Lo usan el
pulido, el router, la corrección, la traducción y el menú. `ASK_PROVIDER` elige el de `/preguntar`;
vacío o ausente, hereda `LLM_PROVIDER`. A todos los arma `main.build_model()`: sin `ask`, el
barato de `LLM_PROVIDER`; con `ask=True`, el que busca en la web, de `ASK_PROVIDER`.
`ClaudeModel` (`claude.py`) tiene la misma forma de llamarlo que `GoogleModel`, así que
ninguno de los seis sabe con cuál habla. El log de arranque nombra los dos: «texto con
google: gemini-3.1-flash-lite, y las preguntas con anthropic: claude-sonnet-5-5».

- 🔴 **En esta casa el texto va con Gemini y las preguntas con Claude Sonnet**
  (`ASK_PROVIDER=anthropic`), decisión del dueño del 2026-10-20. Con el prompt actual, Claude
  Haiku 5.5 dio treinta y nueve o cuarenta de cuarenta y dos en el router, contra cuarenta y
  dos de cuarenta y dos de Gemini; en el pulido, con doce textos reales, no mejoró y tardó de
  cero coma ocho a cuatro coma ocho segundos contra cerca de uno de Gemini. Sonnet contestó bien y con fuentes en unos diez
  segundos. `gemini-3.8-flash` y `gemini-3.7-flash` pulieron igual que `3.1-flash-lite` y
  tardaron el doble; `gemini-3.5-flash-lite` da 400. Lo que sonaba raro venía de las
  plantillas, no del modelo (PR #82): cambiar de modelo no lo arregla.

- ⚠️ **Las notas de voz van siempre a Gemini, con `LLM_API_KEY`**, aunque el proveedor sea
  `anthropic`: Claude no acepta audio. Por eso `transcribe_enabled` es aparte de
  `polish_enabled`. Ver **Notas de voz**, en `.claude/rules/router-y-conversacion.md`.
- **Un proveedor desconocido, o `anthropic` sin `ANTHROPIC_API_KEY`, frena el arranque** con
  `ConfigError`, en `LLM_PROVIDER` y en `ASK_PROVIDER` por igual. Con `google` sin
  `LLM_API_KEY`, se apaga lo de ese proveedor: con `LLM_PROVIDER` el texto, con
  `ASK_PROVIDER` solo las preguntas (`ask_enabled`, aparte de `polish_enabled`).
- ⚠️ **`ANTHROPIC_ASK_MODEL` nunca hereda de `ANTHROPIC_MODEL`**: Haiku no tiene la búsqueda
  web. El barato va con `effort` low; el que pregunta, Sonnet con `effort` medium y la
  herramienta de búsqueda, hasta tres búsquedas y con la ubicación en Argentina.
- **El cliente es el SDK oficial, sin reintentos** (`max_retries=0`): el timeout de quien lo
  usa es el único tope, igual que con Google. Un `pause_turn` se continúa hasta tres vueltas;
  una negativa, un error del SDK o una respuesta sin texto salen como `PolishError`, así que
  el original gana igual que con Google.
- **Los prompts son los mismos para los dos proveedores**, y están medidos con Gemini; ver la
  medición en `.claude/rules/router-y-conversacion.md`.

### Corrección de lo que escribe una persona

`correct.py` le arregla la ortografía a lo que alguien escribió en `/decir`, antes de
sintetizarlo. **No es el pulidor**: el pulidor reescribe lo que generamos nosotros; acá las
palabras son de una persona y tienen que seguir siendo suyas.

- 🔴 **Reemplaza la regla anterior de que `/decir` iba literal.** Es decisión del dueño de la
  casa, pedida con un ejemplo: "dile a Diego es hoa de comer" tiene que sonar "Diego, es hora
  de cenar". Lo que se conserva es *qué* dijo, no *cómo* lo tipeó.
- 🔴 **Tres licencias, y solo tres.** Un dígito puede crecer hasta las palabras que lo dicen
  (`1 minuto` → `un minuto`, que es el bug de Piper que originó todo); una palabra a una letra
  de la que volvió es la misma palabra; y una comida sigue al reloj. Cualquier otra cosa
  —una palabra que aparece, una que se va, una oración dada vuelta— es una reescritura, y se
  descarta.
- 🔴 **La comida es la única palabra que puede volver siendo otra.** `MEAL_WORDS` es el
  vocabulario cerrado, y por eso el corrector conoce la hora: "es hora de comer" a las nueve y
  media de la noche es "es hora de cenar". Todas significan lo mismo dicho a otra hora, así
  que lo que cambia es *cuándo*, y el cuándo la casa ya lo sabe.
- ⚠️ **Las palabras cortas no se corrigen por parecido.** `no` y `yo` están a una letra, igual
  que `sin` y `con`: ahí una corrección invierte el sentido. `RISKY` las deja afuera, y con
  ellas se dice lo que se escribió.
- **La hora entra en la clave del cache**, como el ritmo en el de la síntesis: la misma frase
  al mediodía y a la noche es otra corrección, y servir la de antes diría la comida
  equivocada.
- 🔴 **El original siempre gana**, igual que en el pulido: sin clave, sin red, con timeout o
  con una respuesta que no pasa la validación, se dice lo que la persona escribió.
- **En horario de descanso no se corrige.** No se habla, así que no hay nada que arreglar ni
  por qué esperar seis segundos.
- **La respuesta del chat muestra lo que salió por el parlante**, no lo que se tipeó:
  `Ya le avisé: «Diego, es hora de cenar»`. Una corrección rara se ve en el acto.
- ⚠️ `Router._faithful()` no cambia. La corrección es posterior al ruteo, así que la garantía
  de que lo dicho salió del mensaje de la persona sigue en pie: lo que cambia es la
  ortografía, no el origen.

### Llamar a la casa

`/llamar a cenar` es lo contrario de `/decir`, y nació de un mensaje que salía mal:
"llamar a todos a cenar" **no trae las palabras que hay que decir**, trae la intención. El
router tenía que sacar de ahí un texto que no estaba, y lo mejor que podía hacer era mandar
"a cenar" a secas al parlante.

- 🔴 **La frase la genera la casa**, así que es texto nuestro: pasa por el **pulidor**, no por
  el corrector, y `Router._faithful()` no le aplica porque no hay a qué serle fiel. Ese es
  todo el criterio: si las palabras son de una persona, se corrigen; si son nuestras, se pulen.
- **Un llamado es para toda la casa** salvo que alguien nombre un equipo. Llamar a cenar a un
  solo parlante no es lo que quiere decir "llamar".
- **La comida sale del reloj**, con el mismo `meal_verb()` que usa el corrector: "a comer" a
  la noche es "Vengan a cenar", al mediodía "Vengan a almorzar". Sin argumento, también.
- ⚠️ **Se tocó el prompt del router para agregarlo**, y el prompt es lo que sostiene el
  comportamiento medido. Un ejemplo nuevo puede correrle la atención al modelo en los otros
  comandos, así que se vuelve a medir: la última corrida dio cuarenta y dos de cuarenta y dos.
- ⚠️ El payload sale del mensaje de la persona, así que un llamado con un número adentro
  ("llamalos a comer en 5 minutos") se sintetiza con el dígito. El caso normal no los tiene.

## Sonido de alarma

Lo que interrumpe suena antes de hablar: `voice/chime.py` arma el sonido y lo pega adelante
del wav de Piper. Hay tres:

| | Sonido | Piso de volumen |
| --- | --- | --- |
| alarma (`kind=alarm`) | el despertador, `chime.WAKE` | 90 (`speaker.ALARM_MIN_VOLUME`) |
| recordatorio y timer | un beep suave, `chime.SOFT` | 60 |
| aviso urgente de `HouseVoice` | tres beeps, `chime.ALARM` | 60 |

- 🔴 **El despertador tiene tres niveles**, `WAKE_LEVELS` (`wake1` a `wake3`): dos coma ocho,
  cuatro y cinco coma tres segundos, cada uno más fuerte. Son ráfagas de mil y mil quinientos
  hertz con la amplitud subiendo ráfaga a ráfaga. La alarma arranca con `wake1`, la primera
  repetición suena `wake2` y de ahí en adelante `wake3` (`Announcer._sound(job, rings)`), que
  con una repetición cada cinco minutos llega hacia el minuto diez. El
  piso es 90 en todas. Ver **Alarma, recordatorio y timer**, en `.claude/rules/programado.md`.
- **Ningún tono pasa de `MAX_AMPLITUDE` (0.9)**: `frames()` recorta lo que lo supere. Cada
  tono lleva su amplitud en la tupla `(hertz, segundos, amplitud)`.

- 🔴 **Va en el mismo wav, no en un segundo cast.** Dos clips son dos conexiones, dos esperas
  y dos confirmaciones de que sonó, con la app ajena pudiendo meterse en el medio.
- **El sonido se genera, no se despliega.** `wave` de la stdlib, con el formato del wav de la
  voz: nada que copiar al CT y nada que resamplear, que ahí no hay ffmpeg.
- 🔴 **El chime va en la clave del cache**, como la voz y el ritmo. Sin eso, la primera alarma
  que dice una frase deja esa frase con beeps para siempre, también desde `/decir`.
- ⚠️ **La clave `chime` queda solo para los tres beeps del urgente**: el despertador usa
  `chime:wake1` y siguientes, y el beep suave `chime:soft`. `chime=True` sigue siendo los tres
  beeps.
- 🔴 **El piso de la alarma es por frase, no del equipo.** `Speaker.say(min_volume=...)` lo
  reemplaza para ese anuncio; con `None` queda el del equipo. `Announcer._floor()` pide 90 solo
  para `kind=alarm`. Ver el gotcha del piso de volumen.
- ⚠️ **Los timers agendados antes de la columna `kind` son alarmas**: suenan con el
  despertador, a 90, y repiten hasta que alguien los apague o pase la media hora.
- **Suena lo que interrumpe**: alarmas, recordatorios y timers (`Announcer`), todo
  `announce(urgent=True)` —monitor y API— y el re-aviso de una caída, que pide los tres beeps
  con `chime` sin ser urgente. El corte de internet y el re-aviso de un recordatorio
  (`Announcer.nag()`) suenan con el beep suave. El clima, la agenda, el resumen, `/decir` y `/llamar` no. En horario de
  descanso no se habla, así que tampoco suena.

## Cache de audio

- **Reusar un archivo le actualiza la fecha.** `VoiceSynth.say()` con el `.wav` y `Voicemail`
  con el `.ogg` pasan por `tts.reuse()`, que le pone la hora actual: así `/depurar audio` sabe
  qué no se usa hace treinta días. Ver **Audio**, en `.claude/rules/depurador.md`.
- **Si el archivo ya no está, se vuelve a hacer**: `reuse()` devuelve False, `VoiceSynth`
  sintetiza y `Voicemail` codifica de nuevo. Si no puede tocar la fecha por otro error, lo
  loguea y usa el archivo igual.

## Gotchas

- 🔴 **Piper no deja pausa entre oraciones si no se le pide.** Se lo llamaba sin un solo
  parámetro, así que el remate de un chiste salía pegado al setup y el dueño lo describió
  como "va a velocidad de dos". No estaba acelerado: los wav son 22050 Hz y la duración
  coincide con lo que tarda en sonar. Era el ritmo. `PiperRunner` ahora manda
  `--length-scale` y `--sentence-silence` con un default que respira, y las cuatro perillas
  se mueven por entorno (`DOMOTICA_LENGTH_SCALE`, `DOMOTICA_SENTENCE_SILENCE`,
  `DOMOTICA_NOISE_SCALE`, `DOMOTICA_NOISE_W`).
- **El primer arreglo del ritmo se quedó corto y el default subió otra vez**, a `1.40` y
  `1.10`, en dos pasos: primero a `1.30` y `0.90`, y de nuevo tras escuchar el resumen. El que lo destapó fue el resumen de la mañana, que es lo más largo que dice la
  casa: tres bloques seguidos sin respirar se escuchan como uno solo. Es **una sola
  velocidad para toda la casa**, por decisión del dueño, y se mueve por entorno sin
  desplegar. ⚠️ Cambiarla deja huérfano en `/var/lib/domotica/cache` lo sintetizado con
  el ritmo viejo: el ritmo es parte de la clave.
- 🔴 **El CT ya no corre con ese default: habla a `1.15` y `0.90`**
  (`DOMOTICA_LENGTH_SCALE` / `DOMOTICA_SENTENCE_SILENCE` en `/etc/domotica/domotica.env`,
  desde el 2026-09-23). Con el resumen partido en párrafos, `1.40` ya sobraba: el dueño
  escuchaba la nota de voz a 1,5x. Se probó un punto medio en vez del equivalente exacto
  (`0.93`), porque `1.30` ya había sonado apurado en el parlante. Como los horarios, **lo que
  manda es el env**; el default del código queda como estaba.
- 🔴 **Piper no deja pausa entre renglones**, solo entre oraciones de un mismo renglón: un
  `\n` pegaba los bloques todavía más que un espacio. Por eso `VoiceSynth` parte el texto por
  renglones, sintetiza cada uno aparte y los une con `DEFAULT_PARAGRAPH_SILENCE` (2 s, contra
  1,1 s entre oraciones). Cada párrafo es un arranque de Piper más: el resumen tarda unos
  segundos más en sintetizarse. La pausa entra en la clave del cache **solo si hay más de un
  renglón**, así lo ya sintetizado de una línea sigue sirviendo.
- 🔴 **El ritmo va en la clave del cache, igual que la voz, y por el mismo motivo.**
  `build_synth()` arma el runner y el `VoiceSynth` juntos para que los dos usen el mismo
  `pacing`: si se separan, se sintetiza con un ritmo y se reusa audio hecho con otro.
  Lo que no se configura **no se manda**, así que el modelo sigue decidiéndolo.
- 🔴 **La voz es parte de la clave del cache de audio.** `VoiceSynth` cachea por hash;
  cuando la clave era solo el texto, cambiar `DOMOTICA_VOICE` dejaba sonando la voz vieja en
  toda frase ya dicha, sin nada en el log que lo explicara. Cambiar de voz ya no pide vaciar
  `/var/lib/domotica/cache`, pero el cache queda duplicado por voz.
- 🔴 **Los dispositivos Google se resuelven por UUID, nunca por IP.** Son DHCP y se mueven:
  el Nest ya saltó de `.13` a `.20` solo. Los UUID están en `CAST_DEVICES`.
- 🔴 **Resolver por UUID no alcanza: el objeto resuelto se queda con la IP de ese momento.**
  `Caster` cachea el dispositivo —descubrir puede tardar hasta veinte segundos de mDNS— y el 2026-09-10
  se vio el precio: el servicio venía de un arranque del 4 de septiembre hablándole a
  `192.168.68.22` mientras el Nest ya estaba en `.20`, y el log solo decía
  `Chromecast 192.168.68.22:8009 is connecting...`. El aviso llegaba a Telegram y no salía
  por ningún parlante. Ahora un fallo manda a redescubrir y reintentar una vez
  (`Caster._perform`). ⚠️ Un reintento puede repetir un anuncio que sí sonó: es el mismo
  canje que hacen los watchers, un aviso dicho dos veces sale más barato que uno perdido.
- 🔴 **DHCP recicla direcciones, así que la IP vieja puede ser otro equipo.** El 2026-10-15
  el Nest pasó de `.22` a `.21` y la TV de la recámara tomó la `.22`; a las 04:49 pychromecast
  reconectó por heartbeat a la `.22` y los anuncios salieron por la TV **sin ningún error**:
  la conexión funcionaba, contra el equipo equivocado. Sin falla, `_perform` no redescubre.
  Por eso, **antes de cada acción**, `Caster._moved()` compara la IP del socket del equipo
  cacheado con la que el browser mDNS vivo anuncia para ese UUID (`_Discovery.host_of`). Si
  difieren, warning con las dos, `forget()` —que ahora desconecta el viejo con
  `disconnect(timeout=0)`— y se vuelve a resolver.
- ⚠️ **Eso no lo cubre todo.** Entre la reconexión por heartbeat y la próxima acción el
  equipo cacheado sigue apuntando al otro, y si mDNS no ve el UUID se sigue con el cacheado:
  sin anuncio no hay con qué comparar. La IP fija en el router sigue siendo lo recomendable.
- **Los equipos con pantalla solo aparecen en el descubrimiento si están encendidos.** Un
  Google TV apagado no existe para mDNS. No es un error: es que no está.
- 🔴 **La app que está corriendo es dueña de la sesión de medios.** Con YouTube abierto en
  un Chromecast, un `play_media` se lo come YouTube y el anuncio se pierde **en silencio**.
  Hay que desalojar la app ajena primero. El receptor propio (`CC1AD845`) se respeta:
  relanzarlo cortaría el audio en curso.
- **Los `Launching app CC1AD845` repetidos en el mismo milisegundo son normales.** Diagnosticado
  el 2026-09-01 y **no hay nada que arreglar**: `BaseController.send_message` de pychromecast
  "ensures app is loaded" y pide el lanzamiento en *cada* mensaje mientras la app activa no
  sea la nuestra. `_wait_until_playing` sondea con `update_status()` cada doscientos
  milisegundos, así que los primeros sondeos caen con el receptor todavía arrancando y cada
  uno vuelve a pedirlo. Son idempotentes y paran solos cuando el equipo reporta la app. **No
  tocar el sondeo para callar el log**: ese loop es lo que garantiza que un aviso se escuchó,
  y ya se rompió una vez por confiar de más. No es el retry de la librería —ese loguea
  "retrying once" y acá aparece cero veces.
- 🔴 **Confirmar que empezó a sonar, y que suena lo que se pidió.** Por un instante el
  dispositivo sigue reportando el clip anterior como `PLAYING`: aceptarlo es informar que la
  casa fue avisada cuando no salió nada por los parlantes.
- 🔴 **Un `content_id` vacío no es "nuestro audio", es "todavía no dijo nada".** Contarlo como
  cargado dejaba pasar el caso real: receptor recién lanzado, `BUFFERING` con nada adentro,
  el caster daba el anuncio por dicho y el Nest se quedaba mudo. Se veía como un aviso que
  llegaba a Telegram y no sonaba, **sin una sola línea de error en el log**. Ahora el equipo
  tiene que nombrar nuestra URL. Pasa seguido después de un rato sin usar el equipo: cuando
  ya hay un anuncio reciente, el estado viene lleno y el agujero no se nota.
- **Todo lo que se dice sube el volumen al piso y lo devuelve.** `speaker.MIN_VOLUME` (60):
  una casa que quedó en volumen bajo convierte cualquier anuncio en nada. El piso vive en
  `Speaker`, **no** en quien pide la frase: hay cinco llamadores de `say()` —comandos, API,
  `Announcer`, `HouseVoice`, difusión— y todos quieren lo mismo. Se restaura en un `finally`,
  así que un audio que falla tampoco deja los parlantes a todo volumen.
- **La alarma es la única que sube más**: `speaker.ALARM_MIN_VOLUME` (90), pasado por
  `say(min_volume=...)`. Lo decide quien sabe qué está sonando —`Announcer`, por el `kind`—,
  pero lo sigue aplicando y restaurando `Speaker`. Ver **Sonido de alarma**.
- 🔴 **Esperar el final es otro trabajo que esperar el arranque.** Devolver el volumen a mitad
  de frase es justo lo que el piso venía a evitar, y el resumen de la mañana dura mucho más
  que los veinte segundos de `PLAYBACK_TIMEOUT`. La cota real es la **duración del wav**
  (`tts.duration_seconds`) más un margen; `FINISH_TIMEOUT` (120 s) es solo el tope para cuando
  el archivo no se pudo leer, para que un equipo colgado no se quede con el hilo.
- ⚠️ Si el proceso muere en medio de un anuncio, el volumen queda arriba. Es el precio de
  restaurar recién al final; lo arregla el anuncio siguiente.
- ⚠️ Los dobles de los tests **también terminan el clip**. Uno que se queda en `PLAYING` para
  siempre hace esperar al test lo mismo que esperaría a un equipo colgado, y esconde el bug.
- **No existe apagar por Cast.** Lo máximo es `quit_app()`, que deja el equipo en reposo;
  el televisor se apaga solo si está configurado para dormirse al perder señal. El apagado
  real pide ADB, y las tres teles de la casa son Google TV, así que las tres podrían.
- 🔴 **El `model_name` de mDNS no dice si el equipo es Android TV.** Un **Chromecast con
  Google TV** se anuncia como `Chromecast`, igual que uno viejo sin sistema operativo. No
  deducir capacidades de ese string: preguntarle al equipo o al dueño.
- **Castear a un equipo con pantalla prende el televisor.** Con la vista de alarma es lo
  buscado: una alarma en el comedor prende la tele y muestra la hora un minuto por sonido. Ver
  **Pantalla en la TV**, en `.claude/rules/pantalla-tv.md`.
- **Un Speaker por equipo, pero síntesis y servidor HTTP compartidos.** Lo único distinto
  entre equipos es el Caster; duplicar lo demás sería sintetizar dos veces la misma frase.
  Los Speaker se construyen recién al usarse: al arrancar, casi todos los equipos están
  apagados.
- **En una tele de `SCREEN_DEVICES` el Caster es un `TeleCaster`**: con la app viva, el audio
  puede ir por la app y, si no confirma, por Cast. Ver **Órdenes**, en `.claude/rules/app-tele.md`.
- **El que castea sirve el audio por HTTP desde sí mismo**, y el parlante tiene que poder
  alcanzar ese puerto. No es "mandarle un archivo": es publicarlo y pasarle la URL.
- 🔴 **Un solo zeroconf y un solo browser mDNS para todo el proceso, y nunca se paran.**
  `pychromecast` necesita el zeroconf vivo para conectar y para reconectar: un equipo armado
  sobre un zeroconf cerrado no conecta nunca. El 2026-10-19, de 04:51 a 05:29, la TV
  `habitacion` metió un bucle de `AssertionError: Zeroconf instance loop must be running`
  a unas mil setecientas líneas por segundo; journald descartó ochocientos veintisiete mil
  mensajes y se perdió el journal anterior. La causa: `_Discovery` era compartido por todos
  los `Caster`, cada redescubrimiento hacía `stop_discovery()` sobre el browser anterior
  —que en pychromecast 14.0.10 cierra su zeroconf— y los equipos cacheados en los otros
  `Caster` quedaban colgados de ese zeroconf. Al reconectar con la TV en reposo,
  `SocketClient.run()` atrapa el error y reintenta sin pausa. Ahora `_Discovery` arranca
  zeroconf y `CastBrowser` la primera vez que se lo necesita, con candado, y no los para.
  Redescubrir es `find()`: espera a que el browser vea el UUID, sondeando cada
  `DISCOVERY_POLL`, y arma el equipo con `get_chromecast_from_cast_info(info, browser.zc)`.
  `host_of()` lee el mismo browser y, si todavía no arrancó, contesta `None`.
- ⚠️ **Un equipo apagado tarda hasta `DISCOVERY_TIMEOUT` (veinte segundos) en contestar «No
  encontré»**, y el error nombra lo que sí vio. Uno prendido contesta apenas aparece. Los
  hilos del browser viven lo que vive el proceso.
- 🔴 **Kokoro se midió y se descartó.** Es el candidato obvio para reemplazar a Piper y no
  entra: **612 MB de RSS contra los 512 del CT**. El int8 entra (439 MB) pero tarda
  **dieciséis segundos** en una frase de cuatro, y el fp16 es el peor de los dos mundos
  porque onnxruntime no tiene kernels de media precisión para CPU: ocupa más y va más lento
  que el modelo entero. Aparte, de sus cincuenta y cuatro voces **solo tres hablan español y
  las tres son peninsulares**; la casa habla rioplatense. Usarlo obligaría a subir el
  contenedor a 2 GB. El dueño escuchó las muestras y se quedó con `es_AR-daniela-high`.
- **`catt` no sirve** para archivos locales — falla siempre con "Playback of local file has
  failed". Se descartó a favor de `pychromecast` directo, que anda.
- **Audios de menos de ~1 s** terminan sin pasar nunca por estado `PLAYING`. Hay que padear
  silencio o no hay forma de confirmar que sonaron.
- **onnxruntime** tira `pthread_setaffinity_np failed` dentro del LXC. Es inocuo:
  se silencia con `OMP_NUM_THREADS=1`.
