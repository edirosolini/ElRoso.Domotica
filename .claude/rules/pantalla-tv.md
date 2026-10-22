---
paths:
  - "src/homeauto/screen.py"
  - "src/homeauto/voice/caster.py"
  - "src/homeauto/web/pages/alarma.html"
  - "src/homeauto/web/static/alarm.js"
  - "src/homeauto/main.py"
  - "tests/schedule/test_screen.py"
  - "tests/voice/test_caster_screen.py"
  - "tests/bot/test_screen_command.py"
---

# Pantalla en la TV

## Pantalla en la TV

`screen.py` pone la pantalla de la casa en las teles por **DashCast** (app `84912283`):
`/pantalla` muestra el kiosco a pedido y una alarma que suena prende su propia vista. Sin
`API_TOKEN` no hay páginas que mostrar, así que tampoco hay pantalla.

- 🔴 **`Caster.show()` lanza DashCast con `force=True`.** Sin `force` abre la página en un
  iframe, y ahí la bloquean la CSP (`frame-ancestors 'none'`, que **no se toca**) y el mixed
  content: DashCast es https y la casa, http.
- **Probado el 2026-10-15 en las tres teles**: comedor (Google TV Streamer), recámara
  (Chromecast con Google TV) y habitación (Chromecast HD). Aguantó cuarenta minutos seguidos
  sin que Cast lo cerrara; lo que lo reemplazó fue una app abierta a mano.
- **Con la app de la tele viva y la capacidad `show`, la página va a la app**; si no, o si la
  app no confirma, por DashCast. Ver **Órdenes**, en `.claude/rules/app-tele.md`.
- 🔴 **Lo que se castea es siempre `/pantalla?ver=1`**, el kiosco de solo lectura. Ver
  **Pantalla de la casa**, en `.claude/rules/web.md`.
- **El kiosco que se castea escala con el alto de la tele**, en 1080p y en 720p; en 720 líneas
  las listas van lado a lado. Ver **El kiosco**, en `.claude/rules/web.md`.
- **Tres piezas.** `ScreenPages` decide qué URL va en cada tele y le pregunta a `Hush`;
  `Screens` prende, apaga y agenda el cierre; `ScreenStore` (`screens`) guarda qué alarma
  prendió cada tele y cuándo se cierra. `main()` arma el `Hush` y `ScreenPages` **antes** de
  `build_speakers(restore=...)`, porque cada `Caster` recibe la página a restaurar por
  constructor.

**`/pantalla`.** Sin argumento muestra en `SCREEN_DEVICE` (default `comedor`); `en <equipo>`
la manda a otra tele y `apagar`, adelante o atrás, la saca.

- **`apagar` solo cierra si DashCast sigue abierto** (`Caster.hide()`): si alguien ya puso
  otra app, `quit_app()` se la cortaría. Contesta que la pantalla no estaba prendida.
- **Con la app de la tele viva y la capacidad `show`, `apagar` también cierra su vista**: la
  app vuelve al kiosco y se va atrás. Ver `hide` en **Órdenes**, en `.claude/rules/app-tele.md`.
- **Un equipo fuera de `SCREEN_DEVICES` contesta que no tiene pantalla**, sin castear nada.
- **Trae «Apagar pantalla»**, que manda `pantalla apagar en <equipo>`.
- 🔴 **Respeta las vacaciones pero no el descanso.** Mostrar no hace ruido: a las once de la
  noche alguien puede querer ver la agenda. En vacaciones contesta que no prende la tele.
- **No está en el menú, sí en `HELP`.** Ver **Comandos y alias**, en `.claude/rules/router-y-conversacion.md`.

**Después de un anuncio.** Hablarle a una tele cierra DashCast: el receptor de audio lo
desaloja.

- 🔴 **Si el anuncio desalojó a DashCast, al terminar el clip vuelve a mostrar.** `Caster`
  mira la app antes de hablar y, si era DashCast, espera el final del clip aunque no haya
  subido el volumen, y después pide la página a `ScreenPages.restore_url()`. Si la tele tenía
  otra cosa, no se toca.
- **La página entra por constructor** (`Caster(screen=...)`), así que sobrevive un reinicio:
  no depende de recordar qué se mostró.
- **Restaurar que falla no hace fallar el anuncio**: se loguea y sigue. El anuncio ya sonó.
- **En descanso o en vacaciones no restaura**: `restore_url()` devuelve `None` y la tele
  queda con lo que dejó el receptor de audio.

**Vista de alarma.** `/alarma?job=<id>` muestra la hora grande, el mensaje y la fecha, y
consulta `/api/ringing/<id>` cada cinco segundos.

- **Se lee de lejos**: el `body` es `kiosk alarm-view` y todo mide en `vh`. La hora va en
  `min(32vh, 28vw)`, con `22vh` antes como respaldo para el navegador sin `min()`, así entra
  también en una pantalla vertical. Las capturas `tele` (1920×1080) y `tele720` (1280×720) de
  `deploy/capture-ui.sh` la muestran. Ver **Temas**, en `.claude/rules/web.md`.
- **Si la alarma es de alguien, abajo del mensaje dice «Para <nombre>»** o «Para todos», con
  el `for` del feed, que sale de la foto de lo que sonó (`forText()`). Va en `.alarm-for`, una
  píldora del acento más grande que el rótulo de arriba, no como `.eyebrow`. De nadie, o de
  una persona que ya no está, no muestra la línea. El kiosco de la tele suma «· para <nombre>» en
  «Hoy» y en «Lo próximo». Ver **Pantalla de la casa**, en `.claude/rules/web.md`.

- **Una alarma cuyo equipo está en `SCREEN_DEVICES` prende la vista en esa tele al sonar**
  (`Screens.ring()` al disparar y `light()` después del primer anuncio). Sin equipo, cuenta
  el `CAST_DEFAULT`.
- **Un recordatorio no prende la vista**: con la app de la tele sale como cartel encima de lo
  que haya, sin DashCast. Ver **Recordatorio**, en `.claude/rules/app-tele.md`.
- 🔴 **Qué equipos tienen pantalla es config, no se deduce**: `SCREEN_DEVICES`, default
  `comedor,recamara,habitacion`. `model_name` no sirve para saberlo (ver **Gotchas**, en `.claude/rules/voz.md`).
- **Mientras suena, lo que se restaura después de cada repetición es la vista de alarma**, no
  el kiosco: `ScreenStore.job_for()` dice qué alarma tiene esa tele.
- **La vista de alarma dura un minuto por sonido** (`VIEW_MS` en `alarm.js`, contado desde que
  carga la página): después pasa sola a `/pantalla?ver=1` aunque siga sonando, y la próxima
  repetición la vuelve a cargar al restaurar. Entre repeticiones hay cinco minutos de kiosco.
- **Cuando deja de sonar, la página también pasa sola a `/pantalla?ver=1`**: el feed contesta
  `ringing: false` y `alarm.js` cambia de dirección. Las dos reglas viven en `nextPage()`.
- 🔴 **A los quince minutos de que deja de sonar se cierra DashCast** (`OFF_DELAY`), con el
  timer `screen-off:<equipo>`, y **solo si sigue abierto**, igual que `apagar`; con la app,
  también cierra su vista. Una alarma
  nueva en esa tele antes del cierre lo cancela.
- **Se rearma en `start()`**: un cierre pendiente vuelve a agendarse, uno vencido se cierra
  ya, y una tele de una alarma que ya no suena queda con quince minutos desde el arranque.
- **En descanso o en vacaciones no se prende nada** (`Hush.is_quiet()` cubre las dos). Una
  alarma igual se escribe al chat.
- **Una tele que falla no frena la alarma**: `Reminders._on_screen()` loguea y sigue.
