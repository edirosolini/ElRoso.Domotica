---
paths:
  - "src/homeauto/watch/**"
  - "src/homeauto/main.py"
  - "tests/watch/**"
  - "tests/test_config_seq.py"
  - "tests/test_briefing_seq.py"
  - "tests/test_alert_buttons.py"
  - "tests/bot/test_status_command.py"
  - "tests/bot/test_confirm_outage.py"
---

# Vigilancia

## Vigilancia

`homeauto/watch/` mira servicios externos. El diseño lo definió el dueño de la infra y es
mejor que un ping desde afuera: **Seq dice por qué se rompió algo**, no solo que no contesta.

- 🔴 **Seq no puede avisar de que el VPS se cayó**: muere con él. Por eso el túnel se vigila
  aparte, con un TCP simple. Son dos señales que cubren agujeros distintos.
- **Un Seq por VPS**, con una clave de config por instancia (`SEQ_URL_<ALIAS>` /
  `SEQ_API_KEY_<ALIAS>`), igual que los calendarios y por el mismo motivo: una lista separada
  por comas sería ambigua porque las URLs traen `:` y `/` propios.
- 🔴 **El alias de un Seq se dice en voz alta.** Va dentro de "hay dos errores nuevos en Seq
  de hosting externo", que se sintetiza. Por eso `SEQ_ALIAS_SHAPE` prohíbe dígitos y guiones
  medios: es la única config del proyecto cuyo *nombre* llega al parlante.
- **El guion bajo separa palabras y al hablar se dice como espacio.** La primera versión
  exigía una sola palabra y el primer VPS real que se cargó ya no entraba
  (`SEQ_URL_HOSTING_EXTERNO`): la config quedó sin poder leerse y el servicio no hubiera
  arrancado en el reinicio siguiente. El guion bajo es el separador que impone el nombre de
  una variable de entorno, así que se acepta ahí y se convierte en espacio en
  `SeqWatcher.name`. ⚠️ **Las marcas guardan el alias tal cual**, con guiones bajos: lo que
  cambia es lo hablado, no la clave de estado.
- ⚠️ **La forma no puede verificar que se entienda dicho.** `vps` pasa la validación —son
  letras— y Piper lo lee como una palabra, no como siglas. Elegir el alias sigue siendo una
  decisión de quien lo escribe.
- 🔴 **Cada instancia lleva sus propias marcas**, `seq:<alias>:last_check` y `:last_alert`.
  Compartir el archivo no es compartir estado: con un enfriamiento común, un VPS que loguea
  un error por segundo dejaría al otro sin avisar nunca.
- **La instancia vieja conserva el alias vacío**: sigue diciendo "Seq" a secas y sigue leyendo
  `seq:last_check`. Renombrarla haría que un despliegue releyera todo y avisara de errores
  viejos.
- **Con alias, una mitad sin la otra hace fallar el arranque** —URL sin clave o clave sin
  URL—, igual que un campo raro en `checks.json`: saltearla en silencio dejaría creyendo que
  se vigilan dos VPS mientras se vigila uno. ⚠️ El par suelto **no**: el env desplegado tiene
  `SEQ_URL` con la clave vacía, y ponerse estricto ahí dejaría la casa sin arrancar.
- ⚠️ **El watcher entra al job por argumento por defecto**, no por closure: cerrar sobre la
  variable del `for` dejaría todos los jobs leyendo el último Seq de la lista.
- **Se consulta desde casa, no al revés.** Seq tiene alertas por webhook, pero saldrían del
  VPS hacia la casa y ese sentido del túnel no está verificado. El de ida sí.
- **El monitor solo habla cuando algo cambia**, y aguanta dos rondas antes de declarar una
  caída. Un monitor que llora en cada timeout enseña a ignorarlo, que es peor que no tenerlo.
  La única insistencia es la de una caída que nadie confirmó.
- 🔴 **Una caída sin confirmar se re-avisa** a los cinco, diez y quince minutos
  (`REMIND_DELAYS`) y después cada media hora (`REMIND_EVERY`), hasta que alguien toca
  «✅ Confirmar» o el servicio vuelve. Hablado, «Atención: X sigue sin responder.», pulido
  como el resto; escrito, «🚨 Sigue caído: X» con el detalle, solo a alertas y con los mismos
  botones que la caída.
- 🔴 **Lo urgente despierta una vez; insistir no despierta.** El primer aviso conserva
  `urgent`. Los re-avisos van con `urgent=False` y `chime=chime.ALARM`: suenan con los tres
  beeps, pero en descanso o con «Silenciar 1 h» solo se escriben. Para eso
  `HouseVoice.announce()` acepta `chime`; sin él, suena solo lo urgente. **Silenciar no
  confirma**: pasado el silencio, vuelve a sonar.
- ⚠️ **Los re-avisos cuelgan de la vuelta del monitor**, no de un timer propio: salen en la
  primera vuelta pasada su hora, así que se atrasan hasta un `CHECK_INTERVAL_SECONDS`.
- **Se confirma por chequeo y solo desde `ALERT_CHAT_IDS`.** El botón manda
  `confirmar <nombre>` y `Monitor.acknowledge()` avisa a los otros chats de alertas
  «✅ <nombre> confirmó: X no responde». El segundo toque contesta quién ya la había
  confirmado; uno después de la recuperación, que ya volvió.
- 🔴 **La confirmación y los re-avisos viven en `service_status`**: `acked_by`, `acked_at`,
  `reminders` y `next_reminder`, por `_add_missing_columns`. Sobreviven un reinicio.
  `save()` no las toca, `acknowledge()` es condicional —solo una caída avisada y sin
  confirmar— y la recuperación las limpia. Una fila que ya estaba alertada al desplegar queda
  con `next_reminder` vacío: **no re-avisa**.
- 🔴 **El estado se guarda antes de avisar**, con el mismo criterio que posponer: el botón de
  confirmar llega con el aviso y, guardado después, un toque rápido no encontraría la caída.
- ⚠️ **El `name` de un chequeo tiene tope de `MAX_NAME_BYTES` (cincuenta y cuatro)**: va en
  el `callback_data` del botón, que Telegram corta en sesenta y cuatro bytes. Uno más largo
  hace fallar el arranque.
- **Seq queda afuera**: sus avisos no traen «Confirmar» ni se re-avisan.
- 🔴 **`/estado` muestra lo que se vigila ahora, no lo que quedó en la tabla.** `snapshot()`
  filtra por los chequeos configurados: renombrar uno deja su fila vieja y nadie la vuelve a
  chequear, así que quedaba en rojo para siempre, esperando una recuperación que no puede
  llegar. Pasó de verdad al renombrar `vpn-vps` a `vps`.
- ⚠️ **La fila vieja no se borra, se deja de mostrar.** Si algún día se vuelve a usar ese
  nombre, resucita con su `alerted` de entonces: en `alerted=1` se cree que ya avisó y no
  vuelve a avisar de la caída. Borrarla a mano en `service_status` es el arreglo.
- ⚠️ **El `name` de un chequeo también se dice en voz alta** ("atención, hosting externo no
  responde") y ahí **no hay validación** que lo frene, a diferencia del alias de Seq. Un
  nombre con dígitos o guiones se va a escuchar mal.
- **La recuperación nunca es urgente.** Nadie se despierta por una buena noticia.
- **Los avisos traen botones**: el del monitor, «Ver estado» y «Silenciar 1 h», y la caída
  y sus re-avisos además «✅ Confirmar» adelante —la recuperación no—; el de Seq,
  solo «Silenciar 1 h», porque `/estado` muestra los chequeos y no Seq. `HouseVoice` los pasa
  también cuando el aviso cae en descanso y solo se escribe.
- 🔴 **«Silenciar 1 h» no calla lo urgente; las vacaciones sí**, decisión del dueño. Es
  `/silencio 1h`, y lo urgente pasa por encima de cualquier silencio, fijo o pedido: la
  próxima caída urgente suena igual. Lo que calla es lo demás —la recuperación, Seq, la
  lluvia, la agenda—. La única excepción es el **Modo vacaciones**, en `.claude/rules/descanso-y-feriados.md`: ahí una caída urgente
  solo se escribe, con sus botones.
- Un campo desconocido en `checks.json` **hace fallar el arranque**. Un typo silencioso en
  `urgent` significaría que nunca te despierta.
- 🔴 **El aviso dice el ambiente y la aplicación, y salen del evento.** "Hay dos errores en Seq
  de vps" no dice si hay que salir corriendo: un mismo servidor corre varias apps y varios
  ambientes. `EnvironmentName` y `ApplicationName` ya venían en los eventos —verificado contra
  la instancia real—, así que no hay nada que configurar y un servicio nuevo se nombra solo.
- **Producción encabeza**, aunque staging tenga más errores, y arranca con "Atención,
  producción". Con más de dos grupos se nombran los dos primeros y el resto se resume.
- ⚠️ **El nombre de la app se limpia para hablar.** `Staging-Facturador.Backend` se decía
  "staging guion facturador punto backend": se le saca el prefijo del ambiente y los puntos.
  Escrito va el nombre real, que es el que sirve para buscar en Seq.
- ⚠️ **`Staging` se dice "pruebas"** y `Production`, "producción". El valor crudo va al chat;
  el mapa está en `SPOKEN_ENVIRONMENTS` y lo que no figura se dice tal cual.
- **Un evento sin esas propiedades no se pinta como staging**: sale como `❔ sin identificar`.
  Decir "pruebas" de algo que no sabemos sería mentir hacia el lado tranquilo.
- 🔴 **Ningún error de Seq despierta.** Decisión del dueño: en horario de descanso van solo al
  chat, y el resumen de la mañana los recuerda. Ver **Resumen de la mañana**, en `.claude/rules/resumenes.md`.
- ⚠️ Los nombres de campo que devuelve la API de Seq se verificaron contra la instancia real
  recién al cargar la clave; el parser acepta variantes igual, por las dudas.

La topología, que no es obvia: el CT de domótica manda `172.68.0.0/23` al router `.1`, que
tiene una ruta estática al CT 202, que hace MASQUERADE sobre `wg0`. El túnel del VPS es
**WireGuard**, no OpenVPN como los otros.

### Caída de internet

`watch/uplink.py` vigila la salida a internet de la casa. `Uplink` prueba por TCP
`1.1.1.1`, `8.8.8.8` y `9.9.9.9` en el 443, con tres segundos de timeout (`TARGETS`,
`TIMEOUT`), y con un destino que conteste alcanza.

- 🔴 **Sin internet, el túnel y Seq también fallan, y no es su culpa.** Sin esta guarda, un
  corte del proveedor salía como caída del VPS. Por eso hay **una sola ronda**: el job
  `service-watch` corre primero `uplink.run_once()` y después `monitor.run_once()`, y el
  `Monitor` se saltea entero si esa ronda no tuvo salida —no chequea, no cuenta fallas, no
  re-avisa—. Los `SeqWatcher` van en sus propios jobs y miran `uplink.online`, el resultado
  de la última ronda; sin salida no consultan y **no mueven `last_check`**, así que al volver
  leen lo que se perdió. Antes de la primera ronda se da por arriba.
- 🔴 **`service-watch` se agenda siempre**, aunque no haya `checks.json`: el uplink corre
  igual y Seq depende de él.
- ⚠️ **El salto también calla los chequeos de la LAN.** Un `checks.json` con un servicio de
  la casa deja de chequearse mientras dure el corte.
- **Los destinos van por IP y por IPv4.** Por nombre, el DNS también depende de la salida; e
  IPv6 está roto en el CT (ver **Gotchas**, en `CLAUDE.md`).
- **La caída se declara con dos rondas seguidas sin respuesta**, como un servicio.
  `uplink:down_since` se marca en la primera y `uplink:alerted` en la segunda, en
  `watch.Marks`: un reinicio en medio del corte no lo vuelve a avisar. Al volver, las dos se
  borran con `Marks.clear()`. Un corte de una sola ronda no dice nada.
- 🔴 **Al caer, «Se cortó internet.» solo por el parlante**, una vez y con `chime.SOFT`.
  Sale por `HouseVoice.speak_only()`, que no escribe al chat ni pule: con el corte, el chat
  no llega. No es urgente: en descanso, con `/silencio` o de vacaciones no se dice y **se pierde**, no se
  repite al terminar el descanso. No hay re-aviso.
- **Al volver, si se había declarado**, se dice «Volvió internet. Estuvo cortado …» y se
  escribe a todos «🌐 Internet se cortó de HH:MM a HH:MM (N min)». La duración cuenta desde
  la primera ronda fallida; hablada sale de `verbalize.duration()` —«una hora y un
  minuto»— y pasado un día es «más de un día». Se escribe aunque el «Se cortó» se haya
  perdido en el descanso.
- **Una caída del VPS ya declarada no re-avisa durante el corte.** El re-aviso que venció
  mientras tanto sale en la primera ronda con conexión.

### Salud del Proxmox

`watch/proxmox.py` mira el host por su API: que conteste, el disco, las máquinas y los
respaldos. Sin `PVE_URL` no se vigila nada de esto.

- 🔴 **Son cuatro chequeos del mismo `Monitor`, no un watcher aparte**: `proxmox`,
  `el disco del proxmox`, `las máquinas del proxmox` y `los respaldos`, armados por
  `proxmox_checks()`. Así heredan «✅ Confirmar», `/estado` y la línea de caídos del resumen
  y del cierre sin escribir nada de eso de nuevo. El `Monitor` existe aunque `checks.json`
  esté vacío, si hay Proxmox.
- **Ninguno es urgente y ninguno reintenta dentro de la vuelta** (`attempts=1`). La caída se
  declara igual con dos vueltas seguidas, como cualquier chequeo.
- **`Check` trae su propia sonda y sus frases.** `probe` reemplaza al HTTP y al TCP, y
  `down`/`up`/`still` son lo que se dice después del nombre al caer, al volver y al re-avisar:
  «el disco del proxmox está casi lleno», «los respaldos volvieron a salir bien». Las usan el
  aviso, la recuperación, el re-aviso hablado, el escrito y `down_line()`. Los chequeos de
  siempre no cambian de texto. ⚠️ `probe` y las frases **no se cargan desde `checks.json`**.
- 🔴 **Una sonda sin dato no mueve el estado.** Levanta `ProbeSkipped` y el `Monitor` la
  saltea esa vuelta: ni caída ni recuperación. Si la API no contesta, cae solo `proxmox` y los
  otros tres se saltean, en vez de sumar tres caídas falsas. Lo mismo si falla una sola ruta
  o si no hay ningún `vzdump` terminado.
- **Un solo pase por vuelta.** `ProxmoxClient` lee todo de una y lo cachea veinticinco
  segundos (`CACHE_SECONDS`), menos que el intervalo del monitor: los cuatro chequeos leen el
  mismo pase. Toma los nodos `online` de `/nodes`.
- 🔴 **El token va en el header `PVEAPIToken`**, nunca en la URL, y se borra de cualquier
  error antes de que llegue al detalle o al log. `verify` va contra la CA del PVE y nunca es
  `False`.
- **Disco**: los storages activos y habilitados más el `rootfs` del host. Avisa desde
  `PVE_DISK_ALERT` (ochenta y cinco por defecto) y vuelve recién por debajo de la alerta menos
  cinco (`DISK_HYSTERESIS`): un disco que oscila en el borde no avisa en cada vuelta.
  🔴 **La histéresis sobrevive un reinicio**: el `Monitor` le pasa a la sonda el estado
  guardado (`restore`) antes de la primera vuelta, y un disco que estaba lleno sigue lleno
  hasta bajar del umbral bajo.
- **Máquinas**: las que tienen `onboot=1`, no son plantilla y están paradas. **Son las únicas
  que re-avisan**: los otros tres llevan `remind=False`.
- ⚠️ **Un CT parado a propósito con `onboot=1` avisa.** Se calla con «Confirmar» o
  sacándole `onboot`.
- **Respaldos**: el último `vzdump` terminado. `WARNINGS` no es caída y queda solo en el
  detalle escrito.
- 🔴 **Lo hablado es genérico y sin dígitos.** El vmid, el nombre de la máquina y el
  porcentaje van solo en `detail`, que es la copia del chat.
- **Una mitad sin la otra hace fallar el arranque**, como con Seq: `PVE_URL` sin
  `PVE_TOKEN` o al revés. `PVE_URL` tiene que ser `https`, `PVE_TOKEN` tener la forma
  `usuario@realm!id=secreto`, `PVE_CA_FILE` es obligatoria y el archivo tiene que existir, y
  `PVE_DISK_ALERT` va de uno a noventa y nueve. `pve_token` va con `repr=False`.
- ⚠️ **Sin internet, el Proxmox tampoco se chequea**, aunque esté en la LAN: es el mismo salto
  del `Monitor` de **Caída de internet**.

## Gotchas

- 🔴 **El certificado del PVE tiene que nombrar la IP por la que se lo llama.** Tenía la
  `.6` vieja en el SAN y validar contra `192.168.68.60` fallaba. Se regeneró el 2026-10-15
  con `pvecm updatecerts --force`. Si cambia la IP del host, volver a generarlo.
