# CLAUDE.md

# Domótica — El Roso

Automatización de la casa, manejada por **Telegram** y, en la LAN, por la web de `/control`.
Hoy hace hablar al parlante; está pensado para sumar dispositivos (luces) sin rediseñar nada.

**No es un producto de El Roso, es laboratorio.** Corre en la red de casa, no en el VPS.

## Estructura

```
Domotica/
├── src/homeauto/
│   ├── config.py        # carga y validación del archivo de entorno
│   ├── quiet.py         # horario de descanso, silencio a pedido y modo vacaciones
│   ├── timespec.py      # parser de "10m", "7:30", "mañana 8:00", "lun-vie"
│   ├── verbalize.py     # números y horas a palabras, para el sintetizador
│   ├── polish.py        # reescribe la redacción con un LLM, sin tocar los datos
│   ├── claude.py        # el modelo de texto por la API de Anthropic, si LLM_PROVIDER o ASK_PROVIDER lo piden
│   ├── correct.py       # corrige lo que escribió una persona, sin cambiar las palabras
│   ├── ask.py           # contesta preguntas con búsqueda: lo escrito y lo dicho
│   ├── summon.py        # la frase con la que la casa llama a alguien
│   ├── route.py         # interpreta un mensaje sin barra y lo manda al comando
│   ├── slots.py         # qué dato le falta a un comando para poder ejecutarse
│   ├── pending.py       # la conversación a medio armar de cada chat
│   ├── weather.py       # clima por Open-Meteo y los avisos del cielo
│   ├── air.py           # calidad del aire de hoy, por Open-Meteo
│   ├── economy.py       # dólar, riesgo país e inflación, en palabras
│   ├── news.py          # titulares por RSS, solo para el chat
│   ├── bible.py         # versículo del día de YouVersion, en la NTV
│   ├── holidays.py      # feriados de argentinadatos, en una caché local
│   ├── briefing.py      # resumen de la mañana: agenda + clima + servicios caídos
│   ├── closing.py       # cierre del día: lo de mañana y lo que sigue roto
│   ├── weekly.py        # balance de la semana sobre el historial, solo escrito
│   ├── calc.py          # cuentas y conversión de unidades, sin modelo
│   ├── lists.py         # las listas de compras y de pendientes
│   ├── meals.py         # el menú de la semana: lo arma el modelo, se valida y se guarda
│   ├── translate.py     # traducir, solo para leer
│   ├── people.py        # el nombre visible de cada chat y el padrón de las personas
│   ├── screen.py        # la pantalla de la casa en las teles: kiosco y vista de alarma
│   ├── cleanup.py       # el depurador: teles, avisos, historial, audio y listas que sobran
│   ├── tele.py          # las teles con la app de la casa: registro, versión y latido
│   ├── api.py           # servidor HTTP de la LAN: /say para otros sistemas
│   ├── bot/             # comandos, sin nada de Telegram adentro
│   ├── schedule/        # timers, alarmas, preferencias por chat
│   ├── agenda/          # Google Calendar: lectura, avisos, resumen
│   ├── voice/           # equipos cast: tts, cast, registro, difusión
│   ├── watch/           # vigilancia de servicios, de Seq, de internet y del Proxmox
│   ├── web/             # pantalla de la casa: agenda, kiosco, control, sus feeds JSON y el APK de la tele
│   └── main.py          # cableado y ciclo de vida del proceso
├── android/tele/        # la app Android de la tele, en Kotlin
├── deploy/              # unit de systemd, despliegue, CLI, la medición del router y la subida del APK de la tele
├── tests/
└── requirements*.txt
```

Carpeta del proyecto en español (convención de `~/Proyectos/ElRoso`), **código en inglés**:
el paquete es `homeauto`, no `domotica`.

## Arquitectura

Una sola regla explica el resto del código: **la lógica no conoce su transporte**.

- `bot/commands.py` no importa nada de `telegram`. Cada método recibe `(chat_id, texto)` y
  devuelve el string de respuesta. Quien lo conecta a Telegram es `main.register()`.
- 🔴 **`Commands` tiene dos transportes**: Telegram y `web.ControlService` (`/control`), que
  corre los mismos `press()` y `free_text()`. Una regla de un comando vale para los dos; no se
  copia en la web.
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
mensaje suelto → route.Router → slots.missing() → falta un dato: pregunta y espera
                    ↓
/decir · /preguntar · API HTTP · alarma · evento de agenda · monitor
                    ↓
        HouseVoice.announce()      ← horario de descanso + a qué equipos
                    ↓
        SpeakerRegistry.get(alias) ← un Speaker por equipo, perezoso
                    ↓
        Speaker.say()  =  VoiceSynth (Piper) → MediaServer (HTTP) → Caster (Cast)
```

El router está **arriba** de todo esto y no habla: solo elige por qué puerta entra el
mensaje. Un mensaje sin barra termina en el mismo lugar que el comando escrito a mano, salvo
que le falte un dato: ahí sale una pregunta al chat y el hilo queda esperando la respuesta,
sin que nada de esto se entere.

`HouseVoice` decide si se habla o solo se escribe, y siempre deja el texto en el chat, salvo
`speak_only()`, que es solo parlante (ver **Caída de internet**, en `.claude/rules/vigilancia.md`).
Las alarmas son la excepción: pasan por `Announcer`, que aplica la misma regla de descanso
y escribe en los chats del aviso: todos los de `ALLOWED_CHAT_IDS`, o solo el de la persona
asignada (ver **Para quién suena**, en `.claude/rules/programado.md`).

`Speaker` es la unidad de "decir algo en un equipo": sintetiza, publica el wav por HTTP y le
pasa la URL al dispositivo. El parlante descarga el audio del CT; no se le manda un archivo.
Con la API, cada tele de `SCREEN_DEVICES` usa un `TeleCaster`: prueba la app si está viva y, si no confirma, Cast.

### Estado

Un solo SQLite, `$STATE_DIRECTORY/jobs.db` (`/var/lib/domotica/jobs.db`), con veintiuna tablas
independientes y una clase por tabla, cada una dueña de su `SCHEMA`:

| Clase | Para qué |
| --- | --- |
| `schedule.Store` | timers, alarmas y recordatorios |
| `schedule.Preferences` | equipo por defecto de cada chat |
| `agenda.SeenStore` | ocurrencias ya avisadas |
| `watch.StatusStore` | último estado de cada chequeo |
| `watch.Marks` | marcas de tiempo de los watchers |
| `quiet.HushStore` | hasta cuándo dura el silencio pedido a mano |
| `pending.PendingStore` | el comando a medio armar de cada chat |
| `lists.ListStore` | las listas de compras y de pendientes |
| `schedule.FiredStore` | lo último que sonó en cada chat y de qué job, para posponerlo |
| `schedule.AwaitingStore` | los recordatorios que sonaron y esperan su «Hecho», con sus re-avisos |
| `strangers.StrangerStore` | los chats fuera de la lista de los que ya se avisó al dueño |
| `schedule.HistoryStore` | todo lo que sonó y cómo terminó, doce meses (`fired_history`) |
| `people.PeopleStore` | el nombre visible de cada chat de la casa, para la pantalla |
| `people.PersonStore` | el padrón: cada persona de la casa, con su chat o sin Telegram (`persons`) |
| `schedule.RingingStore` | las alarmas que siguen sonando, con sus repeticiones (`ringing`) |
| `holidays.HolidayStore` | los feriados del año, y desde noviembre los del siguiente (`holidays`) |
| `schedule.StockStore` | cuántas dosis quedan de cada remedio y cuándo avisar (`pill_stock`) |
| `quiet.AwayStore` | hasta cuándo dura el modo vacaciones (`away`) |
| `screen.ScreenStore` | qué alarma prendió cada tele y cuándo se cierra (`screens`) |
| `meals.MealStore` | el plato de cada día y comida del menú, ocho semanas (`meal_plans`) |
| `tele.TeleStore` | cada tele con la app: versión, capacidades, último latido y dirección (`teles`) |

Comparten archivo pero no se conocen entre sí. Cada una crea su tabla al construirse, así que
un despliegue nuevo no necesita migración.

## Stack

- **Python 3.13** en el contenedor, 3.14 en la notebook. Nada específico de versión.
- **piper-tts** — síntesis de voz **offline**, voz `es_AR-daniela-high`. No sale a internet.
- **Open-Meteo** para el clima y la calidad del aire: sin cuenta, sin API key.
- **icalendar** y **recurring-ical-events** para leer Google Calendar.
- **argentinadatos** para los feriados, igual que para la inflación: sin cuenta, sin API key.
- Servicios externos consultados: Telegram, Open-Meteo (clima y calidad del aire), Google
  Calendar (iCal), YouVersion, argentinadatos, dolarapi, los RSS de noticias, el modelo de
  texto (pulido, router, corrección, traducción y menú) en la API de Google o en la de Anthropic
  según `LLM_PROVIDER`, el de las preguntas según `ASK_PROVIDER` (sin él, el mismo), la API
  de Google para transcribir notas de voz **siempre**, y **Seq** (este último por el túnel
  WireGuard, no por internet).
- **anthropic**, el SDK oficial, para el texto o las preguntas con Claude. Ver **Proveedor
  del texto**, en `.claude/rules/voz.md`.
- La **API del Proxmox** de casa, por la LAN, con un token de solo lectura. Ver
  **Salud del Proxmox**, en `.claude/rules/vigilancia.md`.
- **pychromecast** — control del parlante, sobre un solo **zeroconf** para todo el proceso
  (declarado en `requirements.txt`: se importa en `src/`). Ver los gotchas de cast en
  `.claude/rules/voz.md`.
- **python-telegram-bot** en modo *long polling*.
- **APScheduler** + SQLite para timers y alarmas que sobreviven un reinicio.
- **Kotlin** para la app de la tele, que se compila en Docker, sin Android Studio. Ver
  `.claude/rules/app-tele.md`.
- **FullCalendar** en la pantalla de la casa, vendorizado y sin CDN. Es el único JavaScript
  de terceros del proyecto.

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
ni decorar los tests async. La cobertura sale en cada corrida por `addopts`, y es **un
informe, no una puerta**: `pytest.ini` no fija `fail-under`, así que ningún porcentaje frena
la suite.

No hay linter ni formateador configurados en el repo. Las reglas del proyecto son este archivo
más `.claude/rules/`: ver **Reglas por dominio**.

Los tests **no tocan hardware ni red**: `pychromecast`, el subproceso de Piper y las llamadas
HTTP están mockeados. `tests/conftest.py` tiene lo compartido — `make_config()`, `FakeSpeaker`
y `StubRegistry`; agregar un campo a `Config` se arregla en un solo lugar.

🔴 **Lo que se importa en `src/` va en `requirements.txt`, aunque ande sin declararlo.**
`requests` andaba en el contenedor sin estar declarado: lo arrastraba `casttube`, que es
dependencia de pychromecast. Los once módulos que lo usan —clima, aire, agenda, economía,
feriados, noticias, versículo, pulido, monitor, Seq y Proxmox— lo importan **adentro de la
función**, así que el día que esa cadena cambie no falla
el arranque: falla el primer comando que alguien use, de a uno.
`tests/test_requirements_declared.py` lo sostiene.

Medir el prompt del router, que es lo que sostiene el texto libre:

```bash
scp deploy/measure_router.py root@192.168.68.60:/tmp/
ssh root@192.168.68.60 'pct push 300 /tmp/measure_router.py /tmp/measure_router.py &&
  pct exec 300 -- /opt/domotica/venv/bin/python /tmp/measure_router.py'
```

Corre **adentro del CT** porque ahí está la clave: pasarla por línea de comandos la dejaría
en el historial del shell, igual que el token de `domotica-say`. Son cincuenta y una llamadas
al modelo barato, con pausa para no chocar el límite por minuto.

El proceso es `python -m homeauto.main`, sin entry point instalado.
`deploy/domotica.service` es la referencia de con qué entorno corre de verdad; leerlo antes de
intentar levantarlo a mano.

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

**`config.py` es la fuente de verdad de las claves de entorno**, y acá no hay lista de ellas a
propósito: una lista paralela se desactualiza sola y manda a configurar algo que ya no se lee.
Lo que el archivo acepta se lee en `Config.from_file()`.

🔴 **Los horarios de esta casa no son los defaults del código**, y esa diferencia ya mordió.
Verificados en el CT el 2026-09-22:

| clave | en el CT | default del código |
| --- | --- | --- |
| `QUIET_FROM` | 22:00 | 23:00 |
| `QUIET_TO` | 05:25 | 07:00 |
| `BRIEFING_AT` | 08:45 | 08:00 |
| `CLOSING_AT` | 20:00 | 22:00 |

Son los cuatro valores que deciden **si algo se escucha o solo se escribe**, y por eso son la
única excepción a la regla de arriba: lo demás se mira en el env, esto se piensa antes de
elegir una hora. El cierre del día nació con el default en 22:00, que acá es exactamente el
minuto en que arranca el descanso: habría salido mudo todas las noches, avisando en el chat
que no lo dijo. Con cualquier hora nueva, mirar primero dónde cae `QUIET_FROM`.

**El Proxmox se lee con el token `domotica@pve!monitor`**, rol `PVEAuditor` y `privsep`,
creado por el dueño. La CA del PVE está en `/etc/domotica/pve-ca.pem` (`PVE_CA_FILE`). Ver
**Salud del Proxmox** y el certificado en **Gotchas**, los dos en `.claude/rules/vigilancia.md`.

## Sobre el Asistente de Google

**No se puede tocar.** El Asistente del Nest corre en la nube de Google; desde acá solo se
le manda audio para reproducir. Si contesta "no entiendo", eso se arregla en la app Google
Home (dirección del hogar, idioma, Voice Match), no en este código.

Por eso `/clima` **no** usa el Asistente: consulta Open-Meteo y lo dice con la voz del bot.
Cualquier "inteligencia" que se le quiera agregar al parlante va por este camino — un
comando propio que consulta y habla — nunca intentando engancharse al Asistente.

Al 2026-08-30 el Nest está en `locale es-419` y zona horaria de Buenos Aires, o sea que su
configuración regional es correcta y no es la causa de las fallas del Asistente.

## Gotchas

- 🔴 **httpx loguea la URL completa en INFO, y el token de Telegram va en el path.**
  A nivel INFO el token queda en el journal, en claro y para siempre. `main()` baja
  `httpx`, `httpcore` y `telegram.ext.Updater` a WARNING; `tests/bot/test_logging_hygiene.py`
  lo sostiene.
- 🔴 **IPv6 roto en los contenedores.** Solo tienen link-local `fe80::`, sin IPv6 global.
  Como el DNS devuelve el AAAA y glibc prefiere IPv6, cualquier cliente HTTP se cuelga
  20 s contra hosts doble stack (`api.telegram.org`). Se arregla con
  `precedence ::ffff:0:0/96  100` en `/etc/gai.conf`. **Aplicarlo en todo CT nuevo.**
- ⚠️ **Sin internet, escribir al chat bloquea.** `ChatNotifier` espera cada envío hasta
  treinta segundos, así que durante un corte una alarma o un recordatorio puede tardar eso
  por chat antes de seguir.
- **Telegram por long polling**: no expone ningún puerto a internet. No abrir nada en el router.
- 🔴 **APScheduler lee un datetime naive como UTC.** Todo el proyecto trabaja en hora local
  (el CT está en `America/Argentina/Buenos_Aires`). Un naive `23:14` se agendaba a las 23:14
  UTC — tres horas en el pasado — y el timer disparaba al instante. `JobQueueTimer` le pega
  `astimezone()` antes de agendar. En los logs se veía como `Run time of job was missed by
  2:59:00`, que parece un problema de carga y no de husos.
- 🔴 **Un mensaje editado llega con `update.message` en None.** Con
  `allowed_updates=ALL_TYPES` las ediciones entran a los mismos handlers; `reply_text`
  reventaba con `AttributeError` y en el log salía como "No error handlers are registered",
  que no dice nada. Y antes de reventar el comando **ya se había ejecutado con el argumento
  vacío**, porque el texto salía del mismo `update.message` ausente. El handler ignora todo
  update que no sea un mensaje nuevo, que además es lo correcto: corregir un typo no puede
  poner una segunda alarma.
- 🔴 **Nada bloqueante en el event loop.** Los handlers de Telegram son async, pero el
  descubrimiento (zeroconf) y la síntesis (Piper) son bloqueantes. Llamados desde dentro del
  loop, zeroconf **no descubre nada** y todos los comandos responden "no encontré el
  dispositivo", con un warning suelto de `unregister_all_services skipped as it does blocking
  i/o` como única pista. Todo comando va por `asyncio.to_thread`; hay test que lo verifica.
- **La config se lee una sola vez, al arrancar.** Cambiar el token o `ALLOWED_CHAT_IDS` en
  `/etc/domotica/domotica.env` no tiene efecto hasta `systemctl restart domotica`. Sin reiniciar,
  el servicio sigue con el token viejo y no avisa nada.

## Convenciones

- Mensajes al usuario del bot en **español**. Identificadores en **inglés**.
- **Los logs van en español**, decisión del dueño del 2026-10-15. Hay logs viejos en inglés:
  no se traducen de oficio, se emparejan cuando se toca el archivo.
- 🔴 **Los comentarios y docstrings van en español**, todos. Antes decían inglés y el código
  terminó con 437 en inglés y 47 en español, varios archivos mezclando los dos adentro.
- Los tests no tocan hardware real: se mockea `pychromecast` y el subproceso de Piper.
  La verificación con el parlante de verdad es un paso aparte, manual.
- Nada de tokens ni chat IDs en el repo. Viven en el archivo de entorno del contenedor.

### Qué va en un comentario

Estas reglas vivían fuera del repo y el código se fue llenando de narrativa hasta que hubo
que podarlo entero. Quedan acá para que no se pierdan de nuevo.

- Un comentario dice **qué hace** el código. Nada más.
- **Una línea.** Dos solo si el qué no entra en una.
- **Prohibido**: la historia del bug, las alternativas descartadas, cómo se llegó a la
  solución, anécdotas de depuración, mediciones, quién decidió qué y por qué.
- **Prohibido** repetir lo que el código ya dice (`# incrementa el contador`).
- Comentar solo lo que el código no dice solo. Si es claro, sin comentario.
- **El porqué va en el commit, el PR, este archivo o `.claude/rules/`. Nunca en el código.** Este
  `CLAUDE.md` y `.claude/rules/` son justamente donde vive, y por eso el código no lo repite.
- Excepción única: una **restricción externa no evidente** que rompe si se toca —bug de
  librería, límite de una API, orden obligatorio—. Una línea, seca.
- Docstrings: qué hace, qué recibe, qué devuelve. Sin narrativa.

## Agentes

`.claude/agents/` tiene el circuito de un cambio, y **se versiona**: un agente que cambia
deja historial. Cada uno hace una sola cosa y le pasa la posta al siguiente:

```
planner → (el dueño aprueba) → executor → comments → docs → tester → pr
        → (el dueño mergea) → memory → (el dueño despliega con !) → memory
```

- **Ninguno mergea ni despliega.** El merge y `deploy/deploy.sh` son del dueño.
- 🔴 **Las reglas siguen siendo este archivo y `.claude/rules/`.** Un agente las aplica, no las
  redefine: si un agente y este `CLAUDE.md` o `.claude/rules/` dicen distinto, se corrige el agente.
- Un cambio en los agentes va en su propio PR, como una corrección de docs.

## Memoria local

`.claude/memory/` (no se commitea, está en `.gitignore`, igual que `.claude/worktrees/`). El
backlog es `.claude/memory/backlog.md` — este proyecto **no** tiene board externo.

## Reglas por dominio

Se cargan solas al trabajar los archivos de su `paths:`. Son tan reglas del proyecto como este archivo.

- `.claude/rules/voz.md` — lo que llega al sintetizador y al parlante: verbalize, pulido, corrección, llamar, chime, Piper y Cast.
- `.claude/rules/programado.md` — alarma/recordatorio/timer, repetición, posponer, historial, pastillas y turnos.
- `.claude/rules/descanso-y-feriados.md` — horario de descanso, `/silencio`, modo vacaciones y feriados.
- `.claude/rules/vigilancia.md` — monitor, Seq, caída de internet y salud del Proxmox.
- `.claude/rules/avisos.md` — lista blanca, desconocidos y destinatarios de cada aviso.
- `.claude/rules/resumenes.md` — resumen de la mañana, cierre del día, resumen semanal, economía, noticias y versículo.
- `.claude/rules/clima.md` — aviso de lluvia y los otros avisos del cielo (calor, frío, UV, aire, viento, tormenta).
- `.claude/rules/agenda.md` — Google Calendar por iCal.
- `.claude/rules/router-y-conversacion.md` — texto libre, conversación, notas de voz, por dónde sale la respuesta, botones y comandos.
- `.claude/rules/consultas.md` — preguntas con búsqueda, cuentas y unidades, listas, menú semanal y traducción.
- `.claude/rules/web.md` — API HTTP de la LAN y la pantalla web (agenda, kiosco, escritura, control).
- `.claude/rules/pantalla-tv.md` — DashCast: `/pantalla`, restaurar tras un anuncio y la vista de alarma.
- `.claude/rules/app-tele.md` — la app de la tele: registro en el CT, la app Android y su compilación.
- `.claude/rules/depurador.md` — `/depurar`: qué teles, avisos, historial, audio e ítems de listas sobran, qué nunca se toca y cómo se confirma.
- `.claude/rules/cableado.md` — el composition root `main()` y su test.
