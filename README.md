# Domótica

Bot de Telegram que maneja dispositivos de casa. Hoy: hacer hablar al parlante Google Nest
con voz sintetizada offline. Timers y alarmas incluidos.

## Comandos

```
/decir buenas noches            habla ahora
/decir en tv que bajen a comer  lo dice en ese equipo
/timer 10m sacá la pizza        avisa dentro de 10 minutos
/alarma 7:30 arriba             avisa a esa hora, una vez
/alarma diaria 7:30 arriba      avisa todos los días
/alarma lun-vie 5:30 arriba     avisa solo esos días
/lista                          lo que está programado
/cancelar 3                     cancela por número
/silencio 2h                    no habla por un rato
/hablar                         cancela el silencio
/volumen 40                     0 a 100
/parar                          corta lo que esté sonando
/apagar en todos                cierra la app y deja los equipos en reposo
/clima                          dice el pronóstico en voz alta
/agenda                         qué te queda hoy
/agenda mañana                  el día siguiente completo
/estado                         cómo están los servicios vigilados
/equipos                        qué equipos hay y cuál está activo
/usar tv                        cambia el equipo por defecto
```

**Horario de descanso.** De **23:00 a 07:00** nada suena en voz alta: el aviso llega igual a
Telegram, pero los parlantes se quedan callados. Vale para las alarmas y también para un
`/decir` manual — la regla protege a los que duermen, no a quien está escribiendo. Se cambia
con `QUIET_FROM` y `QUIET_TO`; poniendo las dos iguales se desactiva.

**Avisos urgentes.** Un aviso marcado como urgente —un servicio caído, o `urgent` por la
API— se salta el horario de descanso y además **sube el volumen a 60 si está más bajo**,
devolviéndolo a como estaba en cuanto termina de hablar. Una casa en volumen bajo convierte
una advertencia en nada.

**Silencio a pedido.** Para una siesta o una reunión, `/silencio 2h` calla los parlantes por
ese rato (acepta los mismos formatos que un timer: `30m`, `1h30m`). `/silencio` sin nada dice
si está callado y hasta cuándo; `/hablar` lo cancela. Se guarda en SQLite, así que un
reinicio en medio de la siesta no devuelve la casa hablando.

**Resumen de la mañana.** A la hora de `BRIEFING_AT` (por defecto 08:00, `off` lo apaga) dice
de una vez lo que hay para el día: la agenda, el clima y qué servicios vigilados no responden.
Si todo está en orden no nombra ningún servicio. No hace falta tener agenda configurada: con
el clima solo ya sirve, y una fuente que falla no se lleva puestas a las otras.

**Agenda.** Lee Google Calendar por su **dirección privada en formato iCal**, no por la API:
es solo lectura, así que no hace falta proyecto en Google Cloud, ni OAuth, ni tokens que se
vencen. Además del `/agenda` a pedido:

- **Aviso antes de cada evento**, `EVENT_LEAD_MINUTES` minutos antes (por defecto 10).

Cada aviso se manda una sola vez: queda registrado en SQLite, así que un reinicio no
repite lo ya dicho ni grita eventos que ya empezaron.

⚠️ **La URL privada es una credencial**: quien la tenga lee tu agenda entera. Va en el archivo
de configuración con permisos 600, nunca en el repo.

⚠️ **Google cachea esa URL.** Un evento recién creado puede tardar en aparecer. No es un
problema del bot y no se puede acelerar; si hace falta que sea inmediato, hay que ir por OAuth.

**Clima.** `/clima` consulta Open-Meteo —gratis, sin cuenta ni API key— y lo dice con la voz
del bot. No pasa por el Asistente de Google, así que funciona aunque el Nest conteste "no
entiendo". Combinado con una alarma diaria da el parte de la mañana:

```
/alarma diaria 7:00 clima
```

**Aviso de lluvia.** Cada media hora mira el pronóstico hora por hora y, si en las próximas
seis horas hay al menos 60 % de probabilidad de lluvia, lo dice: *"Ojo, va a llover a eso de
las tres de la tarde"*. Avisa **una vez por día** — la idea es que entres la ropa, no que te
narre el cielo. Se ajusta en `weather.py` (`RAIN_WINDOW_HOURS`, `RAIN_ALERT_CHANCE`), no hay
clave de configuración.

**Apagar.** El protocolo Cast **no tiene apagado**. `/apagar` cierra la app que esté
corriendo y deja el equipo en reposo; de ahí en más, un televisor configurado para dormirse
al perder señal se apaga solo por HDMI-CEC. Un apagado de verdad requeriría ADB, que hay
que habilitar a mano en cada equipo Android TV.

**Elegir equipo.** Cualquier comando acepta `en <equipo>` adelante y va solo a ese; `/usar`
cambia el que se usa cuando no decís nada, y queda guardado por chat. Un timer recuerda a
qué equipo iba, así que se puede programar en uno y seguir hablando por otro.

`en` solo se interpreta como destino si la palabra siguiente es un equipo conocido:
`/decir en casa hace frío` dice la frase entera, no se come nada.

Los timers y las alarmas se guardan en SQLite y **sobreviven un reinicio**. Lo que venció
mientras el servicio estaba caído se anuncia al arrancar, en vez de perderse.

Formatos de tiempo aceptados: `10m`, `5min`, `2h`, `90s`, `1h30m`, `23:15`, `5.30`,
`mañana 8:00`. Una hora que ya pasó se entiende como la de mañana.

Una alarma puede repetirse los días que se le pidan, escribiéndolos antes de la hora:
rangos (`lun-vie`, `vie-lun` cruza el fin de semana), listas (`mar,jue`), un día suelto
(`sab`) o los atajos `finde` y `habiles`. Se aceptan nombres completos y con acento
(`miércoles`). Los días eligen qué ocurrencia de la hora dispara, así que ahí la hora es
obligatoria: `/alarma lun-vie 10m` no tiene sentido y se rechaza.

## Redacción más natural (opcional)

Todo lo que la casa dice puede pasar por un modelo de Google para que suene mejor en voz alta:
agenda, clima, avisos de evento, el mensaje de un timer o una alarma, los avisos del monitor y
de Seq, el aviso de lluvia y lo que entra por la API. Entra en el free tier de sobra: el uso
real son decenas de llamadas por día.

**`/decir` es la excepción y va literal.** Ahí las palabras son tuyas y se dicen como las
escribiste. En todo lo demás el original siempre gana cuando el modelo falla, tarda o contesta
algo sospechoso: nadie se queda sin aviso porque un modelo estaba lento.

```
antes:  Atención: Dentista, en diez minutos, en Consultorio.
ahora:  Tenés turno con el dentista en diez minutos en el consultorio.
```

Se saca una clave en [Google AI Studio](https://aistudio.google.com/apikey) y se pone en la
configuración:

```ini
LLM_API_KEY=              # sin clave, apagado: el texto sale tal cual
LLM_MODEL=gemini-3.1-flash-lite
```

⚠️ **No poner un modelo que razone.** Gemma 4 parece la opción natural por ser abierta, pero
razona antes de cada respuesta y no se puede apagar: tarda **entre 40 y 79 segundos** en
reescribir una frase, medido contra la API. `gemini-3.1-flash-lite` hace lo mismo en menos de
dos segundos. Si el modelo tarda, no se rompe nada —se dice el texto original— pero no pule
nunca.

**Sin clave no cambia nada** y no se sale a internet.

Para probar que la clave anda:

```bash
curl -s -X POST \
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent" \
  -H "Content-Type: application/json" -H "x-goog-api-key: $LLM_API_KEY" \
  -d '{"contents":[{"parts":[{"text":"decí hola"}]}]}'
```

**Lo que el modelo no puede hacer.** Solo reescribe; no informa. La respuesta se descarta —y se
dice el texto original— si trae dígitos, si cambia un número, una hora o un momento del día, si
pierde el título de un evento, o si se va de largo. Si la API falla o tarda, también gana el
original: nadie se queda sin aviso porque el modelo estaba lento.

⚠️ **Esto mejora la redacción, no la voz.** El timbre lo pone Piper y sigue igual.

⚠️ **`/decir` y los timers no pasan por acá.** Lo que escribís vos se dice tal cual.

## Vigilancia de servicios

Dos señales que cubren agujeros distintos:

**El túnel.** Un chequeo TCP contra el servidor del VPS a través de WireGuard. Si no responde,
o se cayó el túnel o se cayó el VPS: en cualquier caso hay que ir a mirar. Los servicios a
vigilar viven en `/etc/domotica/checks.json`:

```json
[
  {"name": "vpn-vps", "host": "172.68.0.7", "port": 5341, "urgent": true},
  {"name": "landing", "url": "https://elroso.ar"}
]
```

Campos: `name`, y `url` **o** `host`+`port`. Opcionales: `expect` (código HTTP esperado),
`urgent`, `timeout`, `attempts`. Un campo desconocido hace fallar el arranque a propósito —
un typo en `urgent` significaría que nunca te despierta.

**Los logs.** Consulta Seq y avisa si hay errores nuevos. Seq dice *por qué* se rompió algo,
no solo que no responde; pero muere junto con el VPS, y por eso el túnel se vigila aparte.

Dos reglas evitan que esto se vuelva ruido, que es como mueren los monitores:

- Un fallo suelto no es una caída: hacen falta dos rondas seguidas para avisar.
- Se avisa **al cambiar de estado**, no mientras dure. La recuperación también se avisa, y
  nunca como urgente: no hay que despertar a nadie por una buena noticia.
- Los errores de Seq tienen enfriamiento (`SEQ_COOLDOWN_MINUTES`): un servicio roto logra
  cientos de errores por minuto y no puede convertirse en cientos de avisos.

## API para otros sistemas

Cualquier script puede hacer hablar la casa. El bot usa long polling y no expone nada, pero
esta API sí escucha: **solo en la LAN, con token**. No abrirla a internet.

Desde el contenedor:

```bash
domotica-say "el backup terminó"
domotica-say --urgent "se cayó producción"
domotica-say -d comedor -d recamara "la cena está lista"
```

Desde cualquier máquina de la red:

```bash
curl -X POST http://192.168.68.10:8099/say \
  -H "X-Token: $TOKEN" -H "Content-Type: application/json" \
  -d '{"text":"el túnel de producción se cayó","urgent":true}'

curl http://192.168.68.10:8099/health     # no pide token
```

| Campo | Qué hace |
| --- | --- |
| `text` | Obligatorio, hasta 500 caracteres |
| `devices` | Lista de alias; por defecto, el equipo principal |
| `urgent` | `true` ignora el horario de descanso |

**Sin `urgent`, dentro del horario de descanso el aviso va solo a Telegram** y la respuesta
lo dice (`"spoken": false`). Nada se pierde, pero nadie se despierta.

El token se genera solo la primera vez y vive en `/etc/domotica/domotica.env`. Si no hay
token, la API no arranca — apagada es el estado seguro.

## Desarrollo

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

Los tests no necesitan hardware ni red: el parlante y Piper están mockeados.

## Configuración

El servicio lee un archivo de entorno (en el contenedor, `/etc/domotica/domotica.env`, chmod 600):

```ini
TELEGRAM_TOKEN=          # token de @BotFather
ALLOWED_CHAT_IDS=        # vacío = el primero que escriba queda registrado
CAST_DEVICES=parlante:d17e8311-...,tv:083e8ba4-...   # alias:uuid, por coma
CAST_DEFAULT=parlante    # cuál se usa si no se dice otro
WEATHER_LAT=-34.6037     # opcional; por defecto, Buenos Aires
WEATHER_LON=-58.3816
WEATHER_PLACE=casa       # opcional, solo para que suene mejor
QUIET_FROM=23:00         # horario de descanso: solo avisa por Telegram
QUIET_TO=07:00           # las dos iguales lo desactivan
API_TOKEN=               # sin token, la API no arranca
API_PORT=8099
CALENDAR_URL_PERSONAL=   # dirección privada en formato iCal
CALENDAR_URL_TRABAJO=    # una clave por calendario; el sufijo es el alias
BRIEFING_AT=08:00        # resumen del día; "off" lo apaga
EVENT_LEAD_MINUTES=10    # cuántos minutos antes avisar
CHECKS_FILE=/etc/domotica/checks.json
CHECK_INTERVAL_SECONDS=120
SEQ_URL=http://172.68.0.7      # logs del VPS, por el túnel
SEQ_API_KEY=                   # clave de solo lectura; sin ella Seq queda apagado
SEQ_COOLDOWN_MINUTES=15
LLM_API_KEY=                   # API de Google AI Studio; sin clave, apagado
LLM_MODEL=gemini-3.1-flash-lite
```

Los equipos van por **UUID, nunca por IP**: son DHCP y se mueven. Para conocer el UUID de un
equipo nuevo, prendelo y mirá `/equipos`, o corré el descubrimiento desde el contenedor.
La clave vieja `CAST_UUID` con un solo UUID se sigue aceptando y equivale a un equipo
llamado `parlante`.

Después de tocar este archivo hay que **reiniciar**: se lee sólo al arrancar.

```bash
systemctl restart domotica
```

`ALLOWED_CHAT_IDS` vacío deja el bot **abierto**: cualquiera que lo encuentre puede usarlo.
Se deja así solo para el alta inicial; una vez que sabés tu chat ID, se completa y se reinicia.

Rutas, sobreescribibles por entorno: `DOMOTICA_CONFIG`, `DOMOTICA_PYTHON`, `DOMOTICA_VOICE`,
`DOMOTICA_CACHE`, `DOMOTICA_MEDIA_PORT`. La base de timers vive en `STATE_DIRECTORY`, que
systemd crea como `/var/lib/domotica`.

## Despliegue

```bash
deploy/deploy.sh              # usa 192.168.68.60 y el CT 300
deploy/deploy.sh <pve> <ctid>
```

Empaqueta, copia al contenedor, instala el unit y **reinicia** el servicio. Ver `CLAUDE.md`
para direcciones y trampas conocidas.
