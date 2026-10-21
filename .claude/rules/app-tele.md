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
uno está en curso**: existen el lado del CT (registro, latido y consulta de qué mostrar) y la
app base, en **La app Android**. Cómo se baja el APK está en **App de la tele**, en
`.claude/rules/web.md`.

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

## La app Android

Vive en `android/tele/`, en Kotlin, y **se compila en Docker**: sin Android Studio ni SDK en
la máquina. Paquete `ar.elroso.domotica.tele`.

- **Dos módulos.** `:core` es JVM puro —protocolo, URLs, latido, backoff, elección— y es lo
  único con tests (`android/tele/build.sh test`). `:app` es lo de Android: pantallas, servicio,
  arranque y el transporte HTTP. Lo que se puede probar sin Android va a `:core`.
- 🔴 **`targetSdk` 34, no más.** Desde el 35 Android no deja arrancar desde `BOOT_COMPLETED`
  un servicio en primer plano de tipo `mediaPlayback`, que es justo lo que hace la app al
  prender la tele. `minSdk` 26.

**Primer uso.**

- Sin tele elegida, `MainActivity` manda a `SetupActivity`: pide `setup` al CT y se elige con
  el control el alias, de `devices`, y la persona, de `people`. Si `people` viene vacío se
  guarda sin persona. Queda en `SharedPreferences`.
- ⚠️ **Hoy la elección no se puede cambiar** sin borrar los datos de la app desde Ajustes.
- ⚠️ **La persona todavía no viaja al CT**: `hello` manda alias, versión y capacidades.

**Servicio.**

- `TeleService` corre en primer plano con notificación. Arranca al abrir la app, al terminar
  el primer uso y al prender el equipo (`BootReceiver`, solo si ya hay tele elegida).
- **Hace `hello` y después `poll` cada cinco segundos.** Sin red, o ante un error del CT,
  espera diez, veinte, cuarenta y sesenta segundos como tope (`BeatSchedule`), y vuelve a cinco
  con la primera respuesta buena. Un `hello` rechazado con 4xx también espera.
- **Se vuelve a registrar** ante un 404 del `poll` o si cambian las capacidades.
- **Capacidades: solo `overlay`, y solo si el permiso de superposición está concedido.** Se
  mira en cada latido, así que concederlo o sacarlo dispara un `hello` nuevo. `play` y `show`
  todavía no se anuncian.
- ⚠️ El `poll` hoy solo anota en el log la alarma que llega: la app no la muestra.
- Al abrirse, la app pide notificaciones y después «mostrar sobre otras apps», un permiso
  por vez y una vez por apertura.
- El log va a logcat con el tag `DomoticaTele`.

**Kiosco.** `MainActivity` es un WebView con JavaScript sobre `/pantalla?ver=1` del CT.

**Red.** 🔴 **Texto claro solo al host de `-Phouse`**: `networkConfig` genera el
`network_security_config` con ese host y nada más. La URL de la casa sale de `-Phouse`
(`TELE_HOUSE` en `build.sh`) o del default de `app/build.gradle.kts`; cambiarla es compilar
de nuevo.

**Compilación.**

- `android/tele/build.sh [destino.apk]` arma el release firmado y lo verifica con
  `apksigner`; `android/tele/build.sh test` corre los tests de `:core`. La imagen trae JDK 17,
  el SDK 34 y Gradle 8.7, con las descargas verificadas por sha256. La caché de Gradle queda
  en un volumen de Docker.
- **`versionCode` y `versionName` van a mano en `version.properties`.** Una versión nueva
  para instalar encima sube el `versionCode`.
- **Del wrapper solo se versiona `gradle-wrapper.properties`, con el sha256 de la
  distribución.** `gradlew` y el jar se generan en Docker si faltan y están en `.gitignore`.
- 🔴 **La firma de release usa una clave fija fuera del repo**, en `TELE_KEYS_DIR` (por
  defecto `~/.config/domotica/android`): `tele-release.jks` y `keystore.properties`. Se monta
  de solo lectura. Sin ella `build.sh` falla e imprime cómo crearla. **Si se pierde, la
  versión nueva no instala encima: hay que desinstalar la app en cada tele.**
