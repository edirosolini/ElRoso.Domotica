---
paths:
  - "src/homeauto/cleanup.py"
  - "tests/test_cleanup.py"
  - "tests/bot/test_purge_command.py"
---

# Depurador

`/depurar` propone borrar las teles que ya no se usan y los avisos que ya no sirven, y borra
solo al confirmar. `cleanup.Cleaner` arma los candidatos y borra; `Commands.purge()` es el
comando y sus botones.

## Quién y cómo

- **Solo los chats de `ALERT_CHAT_IDS`** (`Config.alert_recipients`, que sin esa clave cae
  en `ALLOWED_CHAT_IDS`). Los demás reciben «Solo los chats de alertas pueden depurar.» La
  regla vive en `Commands`, así que vale igual desde `/control`.
- **Tres pasos**: `/depurar` cuenta lo que sobra por categoría, con «Ver teles (N)» y «Ver
  avisos (N)»; cada «Ver» corre `/depurar teles` o `/depurar avisos` y muestra el detalle con
  el motivo de cada uno, más «Borrar N» y «Cancelar». Los avisos de «Ver» suman los restos.
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

- **a** — su autor no está en `ALLOWED_CHAT_IDS` (con la lista vacía no aplica).
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

## Umbrales

Son constantes de `cleanup.py` (`TELE_UNSEEN`, `IGNORED_IN_A_ROW`, `OVERDUE`, `PLAN_TTL`), no
claves de entorno.
