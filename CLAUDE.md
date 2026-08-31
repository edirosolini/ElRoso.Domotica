# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Domótica — El Roso

Automatización de la casa, manejada por **Telegram**. Hoy hace hablar al parlante;
está pensado para sumar dispositivos (luces) sin rediseñar nada.

**No es un producto de El Roso, es laboratorio.** Corre en la red de casa, no en el VPS.

## Estructura

```
Domotica/
├── src/homeauto/
│   ├── config.py        # carga y validación del archivo de entorno
│   ├── quiet.py         # horario de descanso
│   ├── timespec.py      # parser de "10m", "7:30", "mañana 8:00"
│   ├── verbalize.py     # números y horas a palabras, para el sintetizador
│   ├── polish.py        # reescribe la redacción con un LLM, sin tocar los datos
│   ├── weather.py       # clima por Open-Meteo
│   ├── api.py           # endpoint HTTP para otros sistemas
│   ├── bot/             # comandos, sin nada de Telegram adentro
│   ├── schedule/        # timers, alarmas, preferencias por chat
│   ├── agenda/          # Google Calendar: lectura, avisos, resumen
│   ├── voice/           # equipos cast: tts, cast, registro, difusión
│   ├── watch/           # vigilancia de servicios externos y de Seq
│   └── main.py          # cableado y ciclo de vida del proceso
├── deploy/              # unit de systemd, script de despliegue y CLI
├── tests/
└── requirements*.txt
```

Carpeta del proyecto en español (convención de `~/Proyectos/ElRoso`), **código en inglés**:
el paquete es `homeauto`, no `domotica`.

## Arquitectura

Una sola regla explica el resto del código: **la lógica no conoce su transporte**.

- `bot/commands.py` no importa nada de `telegram`. Cada método recibe `(chat_id, texto)` y
  devuelve el string de respuesta. Quien lo conecta a Telegram es `main.register()`.
- `ApiService` no conoce HTTP; `ApiServer` es el `http.server` que lo envuelve.
- Los colaboradores entran por constructor (`notify`, `clock`, `discover`, `build`, `announce`),
  así que los tests inyectan dobles sin parchear módulos.
- `main.py` es el **composition root**: es lo único que arma objetos reales y lo único que
  toca `telegram`, `systemd` y el sistema de archivos del contenedor.

Consecuencia práctica: si una feature necesita mockear algo con `patch()`, casi siempre está
en el lado equivocado de esa línea.

### Camino de un anuncio

Todo lo que la casa dice pasa por el mismo lugar, venga de donde venga:

```
/decir · API HTTP · alarma · evento de agenda · monitor
                    ↓
        HouseVoice.announce()      ← horario de descanso + a qué equipos
                    ↓
        SpeakerRegistry.get(alias) ← un Speaker por equipo, perezoso
                    ↓
        Speaker.say()  =  VoiceSynth (Piper) → MediaServer (HTTP) → Caster (Cast)
```

`HouseVoice` decide si se habla o solo se escribe, y siempre deja el texto en el chat.
Las alarmas son la excepción: pasan por `Announcer`, que aplica la misma regla de descanso
pero avisa al chat que las pidió, no a todos.

`Speaker` es la unidad de "decir algo en un equipo": sintetiza, publica el wav por HTTP y le
pasa la URL al dispositivo. El parlante descarga el audio del CT; no se le manda un archivo.

### Estado

Un solo SQLite, `$STATE_DIRECTORY/jobs.db` (`/var/lib/domotica/jobs.db`), con seis tablas
independientes y una clase por tabla, cada una dueña de su `SCHEMA`:

| Clase | Para qué |
| --- | --- |
| `schedule.Store` | timers y alarmas |
| `schedule.Preferences` | equipo por defecto de cada chat |
| `agenda.SeenStore` | ocurrencias ya avisadas |
| `watch.StatusStore` | último estado de cada chequeo |
| `watch.Marks` | marcas de tiempo de los watchers |
| `quiet.HushStore` | hasta cuándo dura el silencio pedido a mano |

Comparten archivo pero no se conocen entre sí. Cada una crea su tabla al construirse, así que
un despliegue nuevo no necesita migración.

## Stack

- **Python 3.13** en el contenedor, 3.12 en la notebook. Nada específico de versión.
- **piper-tts** — síntesis de voz **offline**, voz `es_AR-daniela-high`. No sale a internet.
- **Open-Meteo** para el clima: sin cuenta, sin API key.
- **icalendar** y **recurring-ical-events** para leer Google Calendar.
- Servicios externos consultados: Telegram, Open-Meteo, Google Calendar (iCal) y **Seq**
  (este último por el túnel WireGuard, no por internet).
- **pychromecast** — control del parlante.
- **python-telegram-bot** en modo *long polling*.
- **APScheduler** + SQLite para timers y alarmas que sobreviven un reinicio.

## Desarrollo

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

.venv/bin/python -m pytest                      # toda la suite, con cobertura
.venv/bin/python -m pytest tests/test_quiet.py  # un archivo
.venv/bin/python -m pytest tests/voice -k takeover
.venv/bin/python -m pytest tests/test_quiet.py --no-cov   # sin el reporte de cobertura
```

`pytest.ini` fija `pythonpath = src .` y `asyncio_mode = auto`: no hay que instalar el paquete
ni decorar los tests async. La cobertura sale en cada corrida por `addopts`.

No hay linter ni formateador configurados en el repo.

Los tests **no tocan hardware ni red**: `pychromecast`, el subproceso de Piper y las llamadas
HTTP están mockeados. `tests/conftest.py` tiene lo compartido — `make_config()`, `FakeSpeaker`
y `StubRegistry`; agregar un campo a `Config` se arregla en un solo lugar.

Despliegue al contenedor (empaqueta, instala dependencias, reinstala el unit y **reinicia**):

```bash
deploy/deploy.sh              # 192.168.68.60, CT 300
deploy/deploy.sh <pve> <ctid>
```

Para correrlo fuera del contenedor hay que apuntar las rutas por entorno:
`DOMOTICA_CONFIG`, `DOMOTICA_PYTHON`, `DOMOTICA_VOICE`, `DOMOTICA_CACHE`,
`DOMOTICA_MEDIA_PORT`, `STATE_DIRECTORY`.

## Dónde corre

**CT 300 `domotica`** del Proxmox de casa (`192.168.68.60`), en `192.168.68.10`.
El servicio vive en `/opt/domotica`, la config en `/etc/domotica/domotica.env` (chmod 600).

## Sobre el Asistente de Google

**No se puede tocar.** El Asistente del Nest corre en la nube de Google; desde acá solo se
le manda audio para reproducir. Si contesta "no entiendo", eso se arregla en la app Google
Home (dirección del hogar, idioma, Voice Match), no en este código.

Por eso `/clima` **no** usa el Asistente: consulta Open-Meteo y lo dice con la voz del bot.
Cualquier "inteligencia" que se le quiera agregar al parlante va por este camino — un
comando propio que consulta y habla — nunca intentando engancharse al Asistente.

Al 2026-08-30 el Nest está en `locale es-419` y zona horaria de Buenos Aires, o sea que su
configuración regional es correcta y no es la causa de las fallas del Asistente.

## Aviso de lluvia

`weather.RainWatcher` mira el pronóstico **por hora** y avisa que se viene el agua.

- **Una sola vez por día.** Es el diseño, no una limitación: un segundo aviso el mismo día
  es ruido, y el ruido es cómo un aviso deja de escucharse. La marca vive en `watch.Marks`.
- **Un aviso que falla no se marca**, igual que en la agenda: se reintenta en la vuelta
  siguiente.
- El pronóstico se pide con `forecast_days=2`: a las 22:00 las próximas seis horas caen casi
  todas en el día siguiente. Las listas `daily` siguen empezando por hoy, así que el índice
  cero no cambia de significado.
- ⚠️ **Open-Meteo contesta en hora local y sin offset** (`timezone=auto`). El reloj puede
  venir con zona; se compara naive porque el offset ya está aplicado del otro lado.
- Los umbrales son constantes del módulo, no config: `RAIN_WINDOW_HOURS` y
  `RAIN_ALERT_CHANCE`. Si algún día hay que tocarlos desde el contenedor, ahí sí van a
  `Config`.

## Resumen de la mañana

`briefing.py` junta agenda, clima y servicios caídos en un solo texto hablado, a la hora de
`BRIEFING_AT`.

- **Las tres fuentes son independientes.** Una que falla deja un hueco, no cancela el
  resumen: un calendario que no contesta no te puede costar el clima. Es la misma postura
  que dentro de `agenda/`, donde un calendario roto no tapa a los otros.
- **No depende de la agenda.** El job del resumen se agenda aunque no haya ningún calendario
  configurado. Por eso está fuera de `schedule_calendar_jobs()`.
- **De los servicios solo se nombran los caídos.** Escuchar "todo en orden" cada mañana
  enseña a no escuchar; el estado completo está en `/estado`.
- El texto se sintetiza, así que **no lleva dígitos**: las fuentes ya hablan en palabras y
  este módulo solo agrega nombres y conectores. Hay test que lo verifica.

## Agenda

`homeauto/agenda/` lee Google Calendar por la **dirección privada en formato iCal**, elegida
sobre la API de Calendar porque esto es solo lectura: sin proyecto en Google Cloud, sin OAuth
y sin refresh tokens. El precio es que **Google cachea esa URL** y un evento nuevo tarda en
aparecer; si algún día hace falta que sea inmediato, ahí sí hay que migrar a OAuth.

- 🔴 **La URL privada es una credencial.** Trato igual que el token de Telegram: archivo con
  permisos 600, jamás en el repo.
- **Una clave de config por calendario** (`CALENDAR_URL_<ALIAS>`). Una lista separada por
  comas sería ambigua: las URLs llevan `:` y `/` propios.
- **Las recurrencias no se parsean a mano.** `recurring-ical-events` expande RRULE y respeta
  EXDATE; hay test con un semanal que tiene una ocurrencia excluida.
- **`Event.key` identifica la ocurrencia, no el evento.** Un semanal dispara muchas veces y
  cada una se avisa una sola vez.
- **Un aviso que falla no se marca como hecho**, para que se reintente en la vuelta siguiente.
- **Nunca se anuncian eventos que ya empezaron.** Tras un reinicio eso sería ruido.
- Un calendario roto no tapa a los otros: se registra en `last_problems` y sigue.

## Vigilancia

`homeauto/watch/` mira servicios externos. El diseño lo definió el dueño de la infra y es
mejor que un ping desde afuera: **Seq dice por qué se rompió algo**, no solo que no contesta.

- 🔴 **Seq no puede avisar de que el VPS se cayó**: muere con él. Por eso el túnel se vigila
  aparte, con un TCP simple. Son dos señales que cubren agujeros distintos.
- **Se consulta desde casa, no al revés.** Seq tiene alertas por webhook, pero saldrían del
  VPS hacia la casa y ese sentido del túnel no está verificado. El de ida sí.
- **El monitor solo habla cuando algo cambia**, y aguanta dos rondas antes de declarar una
  caída. Un monitor que llora en cada timeout enseña a ignorarlo, que es peor que no tenerlo.
- **La recuperación nunca es urgente.** Nadie se despierta por una buena noticia.
- Un campo desconocido en `checks.json` **hace fallar el arranque**. Un typo silencioso en
  `urgent` significaría que nunca te despierta.
- ⚠️ Los nombres de campo que devuelve la API de Seq se verificaron contra la instancia real
  recién al cargar la clave; el parser acepta variantes igual, por las dudas.

La topología, que no es obvia: el CT de domótica manda `172.68.0.0/23` al router `.1`, que
tiene una ruta estática al CT 202, que hace MASQUERADE sobre `wg0`. El túnel del VPS es
**WireGuard**, no OpenVPN como los otros.

## API

`homeauto/api.py` expone un endpoint HTTP **solo para la LAN**, con token compartido, para que
otros sistemas anuncien cosas. La lógica (`ApiService`) está separada del transporte HTTP y se
prueba sin red.

- **Sin `API_TOKEN` la API no arranca.** Apagada es el estado seguro; un endpoint que hace
  hablar la casa no puede quedar abierto por olvido.
- El token se compara con `hmac.compare_digest`, no con `==`.
- **`urgent` es la única forma de saltear el horario de descanso.** Producción caída a las
  3 AM lo amerita; un backup terminado, no.
- El CLI `domotica-say` lee el token del archivo de configuración: pasarlo por línea de
  comandos lo dejaría en el historial del shell.

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
- ⚠️ **El título del evento y el texto de `/decir` van literales.** Solo se verbaliza lo que
  generamos nosotros. Un anuncio de agenda tiene que decir exactamente lo que dice el
  calendario; reescribirlo sería peor que leer mal un número.

Hay test que verifica que **ningún dígito** sobrevive en el texto que arma la agenda, el clima,
el resumen de la mañana, el aviso del monitor ni el de Seq.

🔴 **Lo hablado y lo escrito no son lo mismo en los avisos de vigilancia.** El detalle de una
sonda (`HTTP 503 en 1.24s`) y la cita de un log de Seq son texto arbitrario: sirven leídos y
son ilegibles dichos, además de estar llenos de dígitos. El monitor y `SeqWatcher` mandan el
detalle aparte, y `HouseVoice.announce(written=...)` lo suma solo a la copia del chat.
`seq.Summary` existe para eso: `spoken` y `detail`.

### Pulido de la redacción

`polish.py` le pasa el texto **generado** a la API de Google para que suene más natural antes
de sintetizarlo. El free tier alcanza y sobra: el volumen real son decenas de llamadas por día.

- 🔴 **El original siempre gana.** Sin clave, sin red, con timeout o con una respuesta
  sospechosa, se dice el texto que ya había. Esto es decoración sobre un camino que tiene que
  funcionar: nadie puede quedarse sin aviso porque un modelo estaba lento.
- 🔴 **`/decir` es lo único que va literal.** Todo lo demás que la casa dice pasa por el
  pulidor: agenda, clima, avisos de evento, el mensaje de un timer o una alarma, los avisos
  del monitor, el resumen de Seq, el aviso de lluvia, la línea de servicios caídos del
  resumen y lo que entra por la API. La decisión es del dueño de la casa y reemplaza la
  regla anterior, que dejaba afuera todo lo escrito por una persona.
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
- Los modelos Gemma **no aceptan system instruction**: el prompt entero va como turno de
  usuario.
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

## Horario de descanso

De 23:00 a 07:00 (`QUIET_FROM`/`QUIET_TO`) **nada se dice en voz alta**: el aviso va solo a
Telegram, con el motivo. Aplica a las alarmas y también a `/decir` y `/clima` manuales.

La decisión de incluir los comandos manuales es deliberada: la regla existe para no despertar
a nadie, y quien escribe a las 3 AM está despierto pero el resto de la casa no. Si alguna vez
hace falta una excepción por mensaje, cuidado con la palabra clave elegida: `en <equipo>` ya
enseñó que un prefijo que también puede ser texto real se come parte del mensaje.

`/silencio 2h` agrega una ventana **a pedido** encima de la fija, para una siesta o una
reunión. `quiet.Hush` la implementa.

- 🔴 **`Hush` tiene la misma forma que `QuietHours`.** Contesta `is_quiet()` y `label`, así
  que el anunciador, los comandos, la API y `HouseVoice` siguen consultando lo mismo sin
  enterarse de que ahora el silencio se puede mover. `main()` construye un solo `Hush` y lo
  pasa donde antes iban las `QuietHours` sueltas.
- **El silencio se guarda en SQLite, no en memoria.** Un reinicio en medio de la siesta
  devolvería la casa hablando.
- **Vence solo**: al consultarlo pasada la hora, `until()` lo borra. Nadie aguas abajo tiene
  que chequear dos cosas.
- Los comandos verifican con `isinstance` que haya un `Hush` de verdad: con unas `QuietHours`
  sueltas no hay nada que mover y contestan que no está configurado, en vez de reventar.

## Alarmas y repetición

Una alarma repite de tres formas: `once`, `daily` y `weekly`. La semanal guarda los días en
la columna `days` de `jobs`, como números ISO (1 = lunes), la misma numeración que
`datetime.isoweekday()`.

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

## Comandos y alias

`ALL_COMMANDS` tiene 24 nombres y `COMMAND_MENU` solo 16: la diferencia son **alias**
(`ayuda`, `recordar`, `tiempo`, `donde`, `volume`, `stop`, `start`, `siesta`). Funcionan, pero no van
al menú de Telegram: verlos duplicados al escribir `/` no ayuda a nadie. Hay test que impide
que la ayuda ofrezca un comando que no existe.

## Cableado

`main()` arma todo y es la parte sin tests unitarios, así que **tres bugs llegaron al
contenedor por ahí**: una función renombrada, una variable usada antes de existir, y
`build_polisher` devolviendo el objeto `Polisher` donde el resto esperaba algo llamable — el
servicio arrancaba perfecto y reventaba con `TypeError` recién cuando alguien pedía `/clima`.
`tests/test_main_wiring.py` ejecuta el cableado completo con dobles. Si se agrega una pieza
nueva al arranque, va también un caso ahí.

🔴 **Un doble que no se parece a lo real no prueba nada.** El caso del pulido existía y pasaba:
inyectaba un `object()` como centinela y verificaba que llegara a destino. Como el centinela
tampoco era llamable, el test tenía exactamente el mismo bug que el código. **Los dobles del
cableado tienen que poder usarse como lo que reemplazan**, no solo viajar hasta su lugar.

Las dependencias se construyen antes que quienes las usan; el archivo se lee de arriba hacia
abajo en ese orden a propósito.

## Gotchas

- 🔴 **La voz es parte de la clave del cache de audio.** `VoiceSynth` cachea por hash;
  cuando la clave era solo el texto, cambiar `DOMOTICA_VOICE` dejaba sonando la voz vieja en
  toda frase ya dicha, sin nada en el log que lo explicara. Cambiar de voz ya no pide vaciar
  `/var/lib/domotica/cache`, pero el cache queda duplicado por voz.
- 🔴 **httpx loguea la URL completa en INFO, y el token de Telegram va en el path.**
  A nivel INFO el token queda en el journal, en claro y para siempre. `main()` baja
  `httpx`, `httpcore` y `telegram.ext.Updater` a WARNING; `tests/bot/test_logging_hygiene.py`
  lo sostiene.
- 🔴 **Los dispositivos Google se resuelven por UUID, nunca por IP.** Son DHCP y se mueven:
  el Nest ya saltó de `.13` a `.20` solo. Los UUID están en `CAST_DEVICES`.
- **Los equipos con pantalla solo aparecen en el descubrimiento si están encendidos.** Un
  Google TV apagado no existe para mDNS. No es un error: es que no está.
- 🔴 **La app que está corriendo es dueña de la sesión de medios.** Con YouTube abierto en
  un Chromecast, un `play_media` se lo come YouTube y el anuncio se pierde **en silencio**.
  Hay que desalojar la app ajena primero. El receptor propio (`CC1AD845`) se respeta:
  relanzarlo cortaría el audio en curso.
- 🔴 **Confirmar que empezó a sonar, y que suena lo que se pidió.** Por un instante el
  dispositivo sigue reportando el clip anterior como `PLAYING`: aceptarlo es informar que la
  casa fue avisada cuando no salió nada por los parlantes.
- **No existe apagar por Cast.** Lo máximo es `quit_app()`, que deja el equipo en reposo;
  el televisor se apaga solo si está configurado para dormirse al perder señal. El apagado
  real pide ADB, y los dos equipos de la casa son Google TV, así que los dos podrían.
- 🔴 **El `model_name` de mDNS no dice si el equipo es Android TV.** Un **Chromecast con
  Google TV** se anuncia como `Chromecast`, igual que uno viejo sin sistema operativo. No
  deducir capacidades de ese string: preguntarle al equipo o al dueño.
- **Castear a un equipo con pantalla prende el televisor.** Tenerlo en cuenta antes de
  mandar una alarma de las 7 AM al comedor.
- **Un Speaker por equipo, pero síntesis y servidor HTTP compartidos.** Lo único distinto
  entre equipos es el Caster; duplicar lo demás sería sintetizar dos veces la misma frase.
  Los Speaker se construyen recién al usarse: al arrancar, casi todos los equipos están
  apagados.
- 🔴 **IPv6 roto en los contenedores.** Solo tienen link-local `fe80::`, sin IPv6 global.
  Como el DNS devuelve el AAAA y glibc prefiere IPv6, cualquier cliente HTTP se cuelga
  20 s contra hosts doble stack (`api.telegram.org`). Se arregla con
  `precedence ::ffff:0:0/96  100` en `/etc/gai.conf`. **Aplicarlo en todo CT nuevo.**
- **El que castea sirve el audio por HTTP desde sí mismo**, y el parlante tiene que poder
  alcanzar ese puerto. No es "mandarle un archivo": es publicarlo y pasarle la URL.
- 🔴 **No parar el browser de zeroconf antes de conectar.** `pychromecast` lo necesita vivo
  para abrir la conexión: si se llama `stop_discovery()` antes de `wait()`, el dispositivo
  aparece en el descubrimiento pero la conexión muere con un timeout de 20 s sin explicación.
  Por eso `_Discovery` guarda el browser.
- **`catt` no sirve** para archivos locales — falla siempre con "Playback of local file has
  failed". Se descartó a favor de `pychromecast` directo, que anda.
- **Audios de menos de ~1 s** terminan sin pasar nunca por estado `PLAYING`. Hay que padear
  silencio o no hay forma de confirmar que sonaron.
- **onnxruntime** tira `pthread_setaffinity_np failed` dentro del LXC. Es inocuo:
  se silencia con `OMP_NUM_THREADS=1`.
- **Telegram por long polling**: no expone ningún puerto a internet. No abrir nada en el router.
- 🔴 **APScheduler lee un datetime naive como UTC.** Todo el proyecto trabaja en hora local
  (el CT está en `America/Argentina/Buenos_Aires`). Un naive `23:14` se agendaba a las 23:14
  UTC — tres horas en el pasado — y el timer disparaba al instante. `JobQueueTimer` le pega
  `astimezone()` antes de agendar. En los logs se veía como `Run time of job was missed by
  2:59:00`, que parece un problema de carga y no de husos.
- 🔴 **Nada bloqueante en el event loop.** Los handlers de Telegram son async, pero el
  descubrimiento (zeroconf) y la síntesis (Piper) son bloqueantes. Llamados desde dentro del
  loop, zeroconf **no descubre nada** y todos los comandos responden "no encontré el
  dispositivo", con un warning suelto de `unregister_all_services skipped as it does blocking
  i/o` como única pista. Todo comando va por `asyncio.to_thread`; hay test que lo verifica.
- **La config se lee una sola vez, al arrancar.** Cambiar el token o `ALLOWED_CHAT_IDS` en
  `/etc/domotica/domotica.env` no tiene efecto hasta `systemctl restart domotica`. Sin reiniciar,
  el servicio sigue con el token viejo y no avisa nada.

## Convenciones

- Mensajes al usuario del bot en **español**; identificadores, logs y comentarios técnicos en inglés.
- Los tests no tocan hardware real: se mockea `pychromecast` y el subproceso de Piper.
  La verificación con el parlante de verdad es un paso aparte, manual.
- Nada de tokens ni chat IDs en el repo. Viven en el archivo de entorno del contenedor.

## Memoria local

`.claude/memory/` (no se commitea, está en `.gitignore`). El backlog es
`.claude/memory/backlog.md` — este proyecto **no** tiene board externo.
