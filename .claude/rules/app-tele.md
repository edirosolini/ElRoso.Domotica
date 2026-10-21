---
paths:
  - "src/homeauto/tele.py"
  - "src/homeauto/web/tele.py"
  - "tests/test_tele.py"
  - "tests/web/test_tele_service.py"
  - "android/**"
---

# App de la tele

## Registro en el CT

La app de la tele es una app Android propia para las teles de `SCREEN_DEVICES`. **La fase
uno está en curso y hoy existe solo el lado del CT**: el registro, el latido y la consulta
de qué mostrar. Cómo se baja el APK está en **App de la tele**, en `.claude/rules/web.md`.

Tres piezas, sin nada de HTTP en las dos primeras:

- `tele.TeleStore` (`teles`): una fila por tele con versión, capacidades, último latido y
  dirección. Agrega solo las columnas que le falten a una tabla vieja.
- `tele.TeleLink`: registra y anota latidos, y dice si una tele está viva.
- `web.tele.TeleService`: valida los pedidos y arma las respuestas. `WebApp._tele()` lo rutea.

Se cablea en `main()` **solo con la API**, o sea con `API_TOKEN`, igual que el resto de `WebApp`.

| Ruta | Qué hace |
| --- | --- |
| `GET /api/tele/setup` | con qué configurar la app: `devices`, las teles de `SCREEN_DEVICES`, y `people`, los chats de `ALLOWED_CHAT_IDS` como `{chat_id, name}` |
| `POST /api/tele/hello` | registra la tele, o la actualiza, y cuenta como latido. Devuelve `{alias, caps}` |
| `GET /api/tele/<alias>/poll` | cuenta como latido y devuelve `{"alarm": id}` o `{"alarm": null}` |

- **`hello` pasa por `_refuse_write`**: `application/json` y `Origin` igual a `Host`, si no
  415 o 403. Un cuerpo que no es un objeto JSON es un 400.
- **Validaciones de `hello`, cada una un 400 con el motivo**: `alias` tiene que estar en
  `SCREEN_DEVICES` (se compara sin mayúsculas ni espacios); `version_name`, texto de hasta
  cuarenta caracteres (`MAX_VERSION`); `version_code`, entero desde cero, y un booleano no
  cuenta; `caps`, una lista.
- **De `caps` quedan solo las conocidas** (`tele.CAPS`: `play`, `show`, `overlay`), sin
  repetidas. Lo demás se ignora sin error, y la respuesta dice qué se aceptó.
- **`poll` de una tele que no está en `SCREEN_DEVICES` o que nunca hizo `hello` es un 404.**
- 🔴 **La alarma del `poll` sale de `ScreenStore.job_for()`**, la misma tabla que usa DashCast.
  Ya respeta descanso y vacaciones: `Screens.ring()` no anota la alarma en esos casos. Ver
  **Pantalla en la TV**, en `.claude/rules/pantalla-tv.md`.
- Otro método es un 405 con `Allow`; una ruta de `/api/tele/` que no es ninguna de las tres,
  un 404. Un error del servicio es un 500 genérico y se loguea.

**Latido.**

- **Una tele está viva si latió hace menos de tres minutos** (`STALE`). `hello` y cada `poll`
  son latidos.
- 🔴 **El latido va a disco como mucho una vez por minuto** (`WRITE_EVERY`): en memoria se
  anota siempre, en `teles` solo si pasó el minuto. `hello` escribe siempre.
- Tras un reinicio, el primer pedido de una tele trae de disco su último latido.
- **La dirección sale de `Request.client`**, la IP que ve `api._Handler`, no de algo que
  mande la app. Se guarda con cada latido que se escribe.
- ⚠️ `TeleLink.alive()` existe pero todavía nadie lo consulta.

🔴 **Sin secreto compartido**, decisión del dueño del 2026-10-21: el mismo nivel que
`/control`, abierto en la LAN de confianza. ⚠️ Cualquiera que alcance el CT puede registrar
una tele de `SCREEN_DEVICES`, hacerla latir y leer en `setup` los chats de la casa con sus
nombres, los mismos que ya da `/api/people` cuando la pantalla escribe.

Las órdenes a la tele, su confirmación y el Cast de respaldo cuando la app no responde
**todavía no existen**.
