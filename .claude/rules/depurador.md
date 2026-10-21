---
paths:
  - "src/homeauto/cleanup.py"
  - "tests/test_cleanup.py"
  - "tests/bot/test_purge_command.py"
---

# Depurador

`/depurar` propone borrar las teles que ya no se usan, los avisos que ya no sirven, el
historial viejo, el audio sin usar y los ítems viejos de las listas, y borra solo al confirmar. `cleanup.Cleaner` arma los candidatos y borra; `Commands.purge()` es el
comando y sus botones.

## Quién y cómo

- **Solo los chats de `ALERT_CHAT_IDS`** (`Config.alert_recipients`, que sin esa clave cae
  en `ALLOWED_CHAT_IDS`). Los demás reciben «Solo los chats de alertas pueden depurar.» La
  regla vive en `Commands`, así que vale igual desde `/control`.
- **Tres pasos**: `/depurar` cuenta lo que sobra, una línea por categoría —teles, avisos,
  historial, audio y listas— con un «Ver <categoría> (N)» por cada una que tenga algo; cada «Ver» corre
  `/depurar <categoría>` y muestra el detalle, más «Borrar N» y «Cancelar». Los avisos de
  «Ver» suman los restos. El historial pide antes cuántos meses dejar.
- **El comando entiende varios nombres por categoría** (`PURGE_WORDS`): `tele`/`teles`;
  `aviso`, `alarma`, `recordatorio` y sus plurales; `historial`/`historia`;
  `audio`/`audios`/`cache`/`caché`; `lista`/`listas` (todas las listas), y `compras` o
  `pendientes` (solo esa lista). Otra palabra
  contesta el uso.
- **El botón lleva un token de ocho hexadecimales** (`depurar ok <token>` / `depurar no
  <token>`), de una sola vez, atado al chat que pidió la vista previa y que vence a los diez
  minutos (`PLAN_TTL`). Los planes viven en memoria: un reinicio los vence. Vencido, de otro
  chat o ya usado contesta «Venció, pedilo de nuevo con /depurar.».
- **Al confirmar se vuelve a evaluar todo y se borra la intersección** entre lo mostrado y
  lo que todavía sobra. Lo que cambió en el medio queda, y la respuesta lo dice: «Borré N de
  M. El resto cambió desde que lo viste y quedó.»
- **Todo es escrito, nada sale por el parlante.** Se loguea quién borró cuánto; a los demás
  chats no se les avisa.

## Teles

Candidata si **no está en `SCREEN_DEVICES`** o **no latió en siete días** (`TELE_UNSEEN`; sin
latido nunca, cuenta como viejo). Se borra con `TeleLink.forget()`, de memoria y de `teles`.

- **Nunca una tele viva ni una con fila en `screens`.** `forget()` además se niega solo si
  la tele está viva, así que una que volvió a latir entre la vista y la confirmación queda.
- Sin `API_TOKEN` no hay registro de teles ni `screens`, y la categoría sale vacía.

## Avisos

Candidato si cumple al menos uno, y se muestran todos los que cumple:

- **a** — su autor no es de la casa: el chat que lo creó no está en el padrón
  (`Household.roster()`: los chats de las personas más `ALLOWED_CHAT_IDS`) y su `author_id`
  tampoco es una persona del padrón. Con la lista vacía no aplica. Además, **asignado a una
  persona que ya no está** en el padrón (`ORPHAN`), aunque la baja normal ya lo pasa a «nadie».
  Sin `roster`, `Cleaner` cae a `ALLOWED_CHAT_IDS` y no mira personas.
- **b** — tiene equipos y **ninguno** está en `CAST_DEVICES`. Uno sin equipo no entra.
- **c** — repite y **sus últimas catorce ocurrencias** (`IGNORED_IN_A_ROW`) en
  `fired_history` cerraron sin «Hecho», «Apagar» ni posponer. Las de feriado no cuentan:
  `HistoryStore.latest()` las saltea. Con menos de catorce, no es candidato.
- **d** — de una sola vez y vencido hace más de un día (`OVERDUE`).

**Nunca se toca**: lo que está en `ringing`, lo que muestra una tele en `screens`, lo que
sonó hace menos de `SNOOZE_WINDOW` (por `last_fired` o por `fired_history`), lo que espera
«Hecho» en `awaiting_done` desde hace menos de `SNOOZE_WINDOW` y lo de una sola vez que
todavía no llegó.

**Todo borrado de un aviso pasa por `Reminders.cancel(None, id, any_owner=True)`**: desagenda,
corta lo que suene, cierra la espera con su historial y borra la fila, igual que `/cancelar`.
Nunca un `DELETE` directo sobre `jobs`.

## Restos

Con los avisos van los restos de lo que ya sonó:

- **`last_fired` de más de `SNOOZE_WINDOW`**: ya no se puede posponer.
  `FiredStore.forget_before()`.
- **`awaiting_done` de más de un día** (`awaiting.KEEP`), salvo los de avisos que ya se
  proponen borrar. `Reminders.forget_wait()` lo saca y desagenda su re-aviso.
- **El borrado es condicional en SQL** (`DELETE ... AND fired_at < ?`): si algo volvió a
  sonar entre la vista y la confirmación, la fila nueva no cae.

## Historial

Borra filas de `fired_history` de antes de los meses que se eligen conservar. Es aparte del
recorte automático de doce meses de `HistoryStore`.

- **Los meses se eligen al purgar**, decisión del dueño: `/depurar historial` ofrece «Dejar 1
  mes», «Dejar 3 meses», «Dejar 6 meses» y «Dejar 12 meses» (`HISTORY_MONTHS`), y
  `/depurar historial <n>` acepta de uno a doce (`HISTORY_MIN_MONTHS`, `HISTORY_MAX_MONTHS`);
  un número fuera de rango, también con signo, contesta el rango y no ofrece botones.
  Fuera de ese rango contesta el rango: el resumen semanal usa la última semana.
- **Meses de calendario**, no treinta días: `months_ago()` toma el mismo día y hora `n` meses
  atrás, o el último día de ese mes si no lo tiene. El conteo general usa un mes.
- 🔴 **Nunca una fila abierta.** Se cuentan y se borran solo las cerradas
  (`count_before()` / `delete_before()`), y el `DELETE` además exige que estuviera cerrada al
  armar la vista: lo que se cerró después de mostrarse queda.

## Audio

Los archivos del cache de síntesis (`DOMOTICA_CACHE`, `/var/lib/domotica/cache`), que el
`MediaServer` sirve a los parlantes.

- **Candidatos**: `.wav` y `.ogg` (`CACHED`) sin usar hace más de treinta días
  (`CACHE_UNUSED`), y los `.partial*` de más de una hora (`PARTIAL_STALE`), que ya no se van a
  terminar. Nada de la última hora. Otra extensión no se mira.
- **«Sin usar» es la fecha de modificación**: `VoiceSynth` y `Voicemail` la actualizan al
  reusar un archivo (ver **Cache de audio**, en `.claude/rules/voz.md`). Borrar uno que se
  vuelva a pedir solo cuesta sintetizarlo de nuevo.
- ⚠️ **Hasta treinta días después del despliegue que trajo esto, la fecha de un audio es la
  de creación**: lo que se reusó antes no actualizaba la fecha, así que una frase de todos los
  días puede salir como «sin usar».
- **Se muestran cantidad y megas** (MB decimales, de un millón de bytes), no los nombres: son
  hashes. El conteo general también lleva los megas.
- **Al confirmar se reevalúa por fecha, archivo por archivo, justo antes de borrarlo**
  (`cleanup._unused`): uno que se usó entre la vista y la confirmación queda.

## Listas

Los ítems de `list_items` con `added_at` de hace más de treinta días (`LIST_STALE`).

- **Los ítems sin fecha se cuentan pero no se proponen**: son de antes de que existiera
  `added_at`, y no se sabe su edad. El conteo y el detalle dicen cuántos hay.
- **El borrado es condicional en SQL** (`remove_old()`): solo los ids mostrados que siguen
  teniendo fecha anterior al corte.

## Umbrales

Son constantes de `cleanup.py` (`TELE_UNSEEN`, `IGNORED_IN_A_ROW`, `OVERDUE`, `PLAN_TTL`,
`HISTORY_MONTHS`, `CACHE_UNUSED`, `PARTIAL_STALE`, `LIST_STALE`), no claves de entorno.
