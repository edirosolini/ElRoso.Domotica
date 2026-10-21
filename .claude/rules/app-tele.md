---
paths:
  - "src/homeauto/tele.py"
  - "src/homeauto/web/tele.py"
  - "src/homeauto/voice/tele.py"
  - "tests/test_tele.py"
  - "tests/web/test_tele_service.py"
  - "tests/voice/test_tele_caster.py"
  - "android/**"
---

# App de la tele

## Registro en el CT

La app de la tele es una app Android propia para las teles de `SCREEN_DEVICES`. **La fase
uno está en curso**: existen el lado del CT (registro, latido, consulta de qué mostrar y
órdenes con su Cast de respaldo) y la app, que ejecuta las órdenes, muestra la alarma, la
apaga con el OK del control y se ofrece a actualizarse, en **La app Android**. Cómo se baja el APK está en **App de la tele**, en
`.claude/rules/web.md`.

Tres piezas, sin nada de HTTP en las dos primeras:

- `tele.TeleStore` (`teles`): una fila por tele con versión, capacidades, último latido y
  dirección. Agrega solo las columnas que le falten a una tabla vieja.
- `tele.TeleLink`: registra y anota latidos, dice si una tele está viva y guarda el buzón de
  órdenes de cada tele.
- `web.tele.TeleService`: valida los pedidos y arma las respuestas. `WebApp._tele()` lo rutea.

Se cablea en `main()` **solo con la API**, o sea con `API_TOKEN`, igual que el resto de `WebApp`.

| Ruta | Qué hace |
| --- | --- |
| `GET /api/tele/setup` | con qué configurar la app: `devices`, las teles de `SCREEN_DEVICES`, y `people`, los chats de `ALLOWED_CHAT_IDS` como `{chat_id, name}` |
| `POST /api/tele/hello` | registra la tele, o la actualiza, y cuenta como latido. Devuelve `{alias, caps}` |
| `GET /api/tele/<alias>/poll` | cuenta como latido y devuelve `{"alarm": id o null, "orders": [...]}` |
| `POST /api/tele/<alias>/ack` | lo que la app dice de una orden, `{seq, state}`. Devuelve `{"accepted": bool}` |

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
- Otro método es un 405 con `Allow`; una ruta de `/api/tele/` que no es ninguna de las cuatro,
  un 404. Un error del servicio es un 500 genérico y se loguea.

**Latido.**

- **Una tele está viva si latió hace menos de tres minutos** (`STALE`). `hello` y cada `poll`
  son latidos.
- 🔴 **El latido va a disco como mucho una vez por minuto** (`WRITE_EVERY`): en memoria se
  anota siempre, en `teles` solo si pasó el minuto. `hello` escribe siempre.
- Tras un reinicio, el primer pedido de una tele trae de disco su último latido.
- **La dirección sale de `Request.client`**, la IP que ve `api._Handler`, no de algo que
  mande la app. Se guarda con cada latido que se escribe.
- **`ack` no es latido.**

🔴 **Sin secreto compartido**, decisión del dueño del 2026-10-21: el mismo nivel que
`/control`, abierto en la LAN de confianza. ⚠️ Cualquiera que alcance el CT puede registrar
una tele de `SCREEN_DEVICES`, hacerla latir y leer en `setup` los chats de la casa con sus
nombres, los mismos que ya da `/api/people` cuando la pantalla escribe.

## Órdenes

`TeleLink` guarda en memoria un buzón por tele. Una orden es `{seq, kind, ...}`: `play` con
`url`, `min_volume` y `seconds`; `show` con `url`; `stop` y `hide` sin más.

- 🔴 **Cada `poll` devuelve todas las órdenes que siguen `pending`**, hasta que la app conteste
  `received`: la misma orden llega en varios `poll`. La app no la ejecuta de nuevo, ver
  **Órdenes en la app**.
- **El `seq` arranca en el milisegundo del arranque del proceso** y crece de a uno por tele.
  El buzón no va a disco: así, tras un reinicio, un `seq` nuevo no repite uno que la app ya
  descartó.
- **`stop` anula todo lo abierto** de esa tele (`cancelled`) y queda él mismo como orden.
- **Se recuerdan las últimas treinta y dos órdenes cerradas** por tele (`KEEP_CLOSED`); las
  más viejas se borran al mandar una nueva.

**`ack`.** El cuerpo es `{seq, state}`, con `state` en `received`, `done` o `failed`
(`ACK_STATES`).

- Pasa por `_refuse_write`, igual que `hello`. Un cuerpo que no es un objeto, un `seq` que no
  es entero desde cero (un booleano no cuenta) o un `state` desconocido son un 400.
- Un alias fuera de `SCREEN_DEVICES` o que nunca hizo `hello` es un 404.
- **`{"accepted": false}`** si la orden no existe o ya cerró (`done`, `failed` o
  `cancelled`): un `ack` tardío no revive nada. Repetir `received` es `true`.
- **`show`, `stop` y `hide` cierran con `received`** (`DELIVERED_ONLY`): pasan a `done` al
  llegar a la app, así no quedan abiertas en el buzón. Solo `play` espera un `done` propio.

**`voice.tele.TeleCaster`.** `build_speakers(..., tele=)` envuelve en él al `Caster` de cada
tele de `SCREEN_DEVICES`; sin API no hay `TeleLink` y todo sigue por Cast. Usa la app solo si
la tele está viva **y** anunció la capacidad (`TeleLink.can()`); si no, va directo por Cast.

- **`play`**: espera `received` diez segundos (`ACK_TIMEOUT`) y después `done` hasta la
  duración del clip más `FINISH_MARGIN`, con tope `FINISH_TIMEOUT`; sin duración, el tope. A
  cualquiera de los dos se le suman treinta segundos (`APP_WAKE_MARGIN`): lo que la app espera a
  que la tele prenda antes de sonar. Si no llega, o llega `failed`, anula la orden y **lo dice
  por Cast**.
- 🔴 **`APP_WAKE_MARGIN` son los diez segundos de `OrderRunner.wakeTimeoutMs` más los veinte de
  `settleMs`, en la app.** Si cambia uno, hay que cambiar el otro: con el margen corto el CT
  repite por Cast un aviso que la app todavía va a decir.
- ⚠️ **`received` sin `done` a tiempo también sale por Cast**, así que puede sonar dos veces:
  un aviso dicho dos veces sale más barato que uno perdido.
- **Un `play` anulado por un `stop` no va a Cast.**
- **`show`**: alcanza con `received`; sin él, o con `failed`, va por DashCast.
- 🔴 **`stop`**: manda la orden a la app si está viva con la capacidad `play` (no `show`), y
  además corta por Cast si no lo está o si lo último que sonó en esa tele salió por Cast
  (`_by_cast`). Así «Apagar» corta donde de verdad está sonando.
- **`hide`**: si la app está viva con `show`, le manda `hide` y espera `received`; sin él lo
  anula y lo loguea. **Además cierra DashCast** si sigue abierto (`Caster.hide()`). Devuelve
  verdadero si cerró cualquiera de los dos, y un error de DashCast no cuenta si la app ya cerró.
- **Lo demás sigue siempre por Cast**: `set_volume`, `turn_off`, `showing` y el resto de lo
  que tiene `Caster`.
- 🔴 **La espera bloquea un hilo, nunca el event loop**: `TeleLink.wait()` duerme en una
  `threading.Condition`, en el mismo hilo donde antes esperaba el Cast.

## La app Android

Vive en `android/tele/`, en Kotlin, y **se compila en Docker**: sin Android Studio ni SDK en
la máquina. Paquete `ar.elroso.domotica.tele`.

- **Dos módulos.** `:core` es JVM puro —protocolo, URLs, latido, backoff, elección, actualización— y es lo
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
- **La persona no viaja en `hello`**, que manda alias, versión y capacidades: solo la usa el OK
  de la alarma.

**Servicio.**

- `TeleService` corre en primer plano con notificación. Arranca al abrir la app, al terminar
  el primer uso, al prender el equipo y al actualizarse la app (`BootReceiver`, con
  `BOOT_COMPLETED` y `MY_PACKAGE_REPLACED`, solo si ya hay tele elegida).
- 🔴 **Sin `MY_PACKAGE_REPLACED`, instalar una versión encima deja el servicio caído**: Android
  lo para al reemplazar el paquete y nada lo vuelve a levantar hasta abrir la app o prender
  el equipo.
- **Hace `hello` y después `poll` cada cinco segundos.** Sin red, o ante un error del CT,
  espera diez, veinte, cuarenta y sesenta segundos como tope (`BeatSchedule`), y vuelve a cinco
  con la primera respuesta buena. Un `hello` rechazado con 4xx también espera.
- **Se vuelve a registrar** ante un 404 del `poll` o si cambian las capacidades.
- 🔴 **Capacidades: `play` siempre; `show` y `overlay` solo con el permiso de superposición
  concedido.** Sin él Android no deja a la app ponerse adelante desde el servicio: la alarma
  suena pero no se ve. Se mira en cada latido, así que concederlo o sacarlo dispara un `hello`
  nuevo.
- Al abrirse, la app pide notificaciones, «mostrar sobre otras apps» y después «instalar apps
  desconocidas» (`REQUEST_INSTALL_PACKAGES`, la pantalla de `MANAGE_UNKNOWN_APP_SOURCES`, que
  existe en Google TV), un permiso por vez y una vez por apertura.
- El log va a logcat con el tag `DomoticaTele`.

**Kiosco.** `MainActivity` es un WebView con JavaScript sobre `/pantalla?ver=1` del CT, o
sobre la URL que le pase un `show`. `Kiosk` es el puente entre el servicio y el kiosco abierto:
si no hay kiosco abierto, lo que el servicio le pide se pierde sin error.

**Órdenes en la app.** `OrderRunner`, en `:core`, ejecuta cada orden sobre `TeleDevice`, que en
Android es `AndroidDevice`. Contesta `received` antes de ejecutar.

- **`play` corre en su propio hilo**, uno solo para todos los `play`, así el latido sigue y un
  `stop` lo puede cortar a mitad. Espera que prenda con tope de diez segundos —si no prende,
  suena igual— y, solo si estaba apagada, veinte más para que asiente.
- 🔴 **En Android 14 el wake lock no prende la pantalla.** `AndroidDevice.wake()` además trae
  `MainActivity`, declarada con `turnScreenOn` y `showWhenLocked`, y eso es lo que prende la
  tele; necesita la superposición. Sin esto la tele seguía en reposo y el audio no tenía salida:
  con el Chromecast dormido, la salida HDMI recién se conecta al despertar.
- 🔴 **Los veinte segundos están medidos en la tele de la habitación** (Chromecast con Google TV
  HD, 2026-10-21): la pantalla se enciende en un segundo, la tele termina el enganche por HDMI a
  los diez y recién reproduce sonido a los dieciocho. Con tres se perdía la frase entera. Con la
  tele prendida no se espera.
- ⚠️ **En el Chromecast la salida HDMI es de volumen fijo**: subir `STREAM_MUSIC` no cambia lo que
  se escucha, manda el volumen de la tele.
- **Sube `STREAM_MUSIC` al piso de `min_volume`** (`VolumeFloor`): el CT lo manda de cero a
  cien y se lleva a los pasos del equipo **redondeando para arriba**; sin valor, la mitad. Solo
  sube, nunca baja, y **restaura el volumen al terminar o al fallar**.
- Reproduce con `USAGE_MEDIA` y `CONTENT_TYPE_SPEECH`, con foco de audio transitorio. Contesta
  `done` si el audio terminó y `failed` si no se pudo bajar, reproducir, o no terminó a tiempo
  (la duración más quince segundos; sin duración, dos minutos).
- **Un `play` cortado por un `stop`, antes o mientras suena, no contesta nada más**: el CT ya lo
  anuló.
- **`show`** prende la pantalla y pone adelante `MainActivity` con la `url`. **`stop`** corta el
  audio y vuelve el kiosco a `/pantalla?ver=1`. **`hide`** vuelve al kiosco y manda la app
  atrás. Un `play` o un `show` sin `url` contesta `failed`.
- **Si un `ack` no llega al CT, la app no lo reintenta**: lo loguea, y el CT cae solo a Cast
  cuando se le vence la espera.
- 🔴 **Una orden repetida no se ejecuta de nuevo, pero se vuelve a confirmar**: `received` y,
  si ya terminó, su `done` o `failed`. Un `ack` que no llegó al CT se repite así en el próximo
  `poll`. `OrderInbox` recuerda los últimos sesenta y cuatro `seq` y `OrderRunner` el último
  estado de otras tantas.
- Una orden ilegible o de un tipo desconocido se descarta al leer el `poll`; el CT la da por
  perdida a los diez segundos.

**Alarma.** El `poll` trae la alarma que suena en la tele; cuando cambia, `Kiosk` la anota.

- **Con el kiosco abierto carga `/alarma?job=<id>`, pero no lo pone adelante**: eso lo hace el
  `show` que manda `Screens`. La vista de alarma vuelve sola al kiosco, igual que en DashCast.
- 🔴 **El OK del control apaga la alarma a nombre de la persona elegida**: manda a
  `/api/command` `{chat_id, data: "callar <id>"}`, el mismo botón que «🔕 Apagar» (`AlarmKey`).
  Mientras hay alarma y persona, abajo dice «OK para apagar». **Sin persona, el OK no hace
  nada** con la alarma y queda en el log.
- ⚠️ **El OK solo llega si la app está adelante**: es una tecla de `MainActivity`. La respuesta
  del CT se espera diez segundos, lo que dura cualquier pedido de la app; si tarda más queda un
  error en el log, aunque el comando haya corrido.

**Actualización.** `Updater`, en `:core`, busca una versión nueva en `/app/tele.json` del CT
(contrato en **App de la tele**, `.claude/rules/web.md`) y la ofrece con `SessionInstaller`.

- **`TeleService` lo corre a los treinta segundos de arrancar y después cada hora**, en un hilo
  propio aparte del latido y de `play`. Un error se loguea y espera a la hora siguiente.
- **`UpdatePolicy` decide, en este orden**: `CURRENT` si el `versionCode` publicado no es mayor
  que el propio; `REJECTED` si esa misma versión ya falló de forma definitiva; `RECENT` si esa misma versión ya se ofreció hace menos de seis horas
  (`RETRY_MS`, guardado por versión en `SharedPreferences`, así que sobrevive un reinicio);
  `ALARM` con una alarma en la tele (`Kiosk.alarm`); `PLAYING` con un `play` en curso
  (`OrderRunner.playing`); `ASLEEP` con la tele en reposo; `NOT_ALLOWED` sin el permiso de
  instalar apps; si no, `OFFER`. Lo que no es `OFFER` ni `CURRENT` se loguea con el motivo.
- 🔴 **Con la tele en reposo no se ofrece** (`ASLEEP`, `PowerManager.isInteractive`): la pantalla
  de confirmar quedaría abierta sin nadie que la vea. No cuenta como oferta, así que se vuelve a
  mirar en el chequeo siguiente.
- **Antes de abrir una sesión nueva se abandonan las propias que quedaron abiertas**
  (`SessionInstaller.abandonOpen()`), para que no se apilen pantallas de confirmar.
- **Una falla definitiva no se vuelve a ofrecer**: `InstallReceiver` guarda el `versionCode`
  (`rejected_code`) ante `STATUS_FAILURE_INCOMPATIBLE`, `_CONFLICT` o `_INVALID` —por ejemplo,
  un APK firmado con otra clave—. Una versión mayor sí se ofrece. Una cancelación, falta de
  espacio u otra falla siguen la regla de las seis horas.
- 🔴 **Alarma, audio y reposo se miran dos veces**: antes de bajar y otra vez después de verificar,
  justo antes de abrir la instalación. La pantalla de confirmar nunca tapa una alarma que
  empezó durante la descarga.
- **Baja a `cacheDir/update.apk` con tope de `size`** bytes: si pasa, corta. Después
  `ApkCheck` compara tamaño y sha256 con `tele.json`; si no coinciden, descarta y lo loguea. El
  archivo se borra al terminar, haya instalado o no.
- **Instala con una sesión de `PackageInstaller`**; el estado llega a `InstallReceiver`, que
  abre la pantalla del sistema para confirmar con el control y loguea cómo terminó. **Siempre
  pide confirmar**: alguien tiene que elegir instalar. En el emulador el foco arrancó en
  «Cancelar»; es comportamiento del sistema, no de la app.
- **Cuenta como oferta solo si la sesión se commiteó.** Si bajar, verificar o abrir la sesión
  falla, no se anota y se reintenta en la hora siguiente, sin esperar las seis horas.
- ⚠️ **Sin verificar en una tele real**: la oferta con la tele prendida, el abandono de
  sesiones y el rechazo por falla definitiva. En el emulador: en reposo no ofrece, y al prender
  sí.

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
  para instalar encima sube el `versionCode`, y es lo único que mira `UpdatePolicy`. Hoy es la
  `0.3.0`, `versionCode` 6.
- **Del wrapper solo se versiona `gradle-wrapper.properties`, con el sha256 de la
  distribución.** `gradlew` y el jar se generan en Docker si faltan y están en `.gitignore`.
- 🔴 **La firma de release usa una clave fija fuera del repo**, en `TELE_KEYS_DIR` (por
  defecto `~/.config/domotica/android`): `tele-release.jks` y `keystore.properties`. Se monta
  de solo lectura. Sin ella `build.sh` falla e imprime cómo crearla. **Si se pierde, la
  versión nueva no instala encima: hay que desinstalar la app en cada tele.**
