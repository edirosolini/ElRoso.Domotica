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
/lista                          lo que está programado
/cancelar 3                     cancela por número
/volumen 40                     0 a 100
/parar                          corta lo que esté sonando
/apagar en todos                cierra la app y deja los equipos en reposo
/equipos                        qué equipos hay y cuál está activo
/usar tv                        cambia el equipo por defecto
```

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

Formatos de tiempo aceptados: `10m`, `5min`, `2h`, `90s`, `1h30m`, `23:15`, `mañana 8:00`.
Una hora que ya pasó se entiende como la de mañana.

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
