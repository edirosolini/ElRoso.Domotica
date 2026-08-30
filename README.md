# Domótica

Bot de Telegram que maneja dispositivos de casa. Hoy: hacer hablar al parlante Google Nest
con voz sintetizada offline. Timers y alarmas incluidos.

## Comandos

```
/decir buenas noches          habla ahora
/timer 10m sacá la pizza      avisa dentro de 10 minutos
/alarma 7:30 arriba           avisa a esa hora
/volumen 40                   0 a 100
/lista                        lo que está programado
/cancelar 3                   cancela por número
/parar                        corta lo que esté sonando
```

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

El servicio lee un archivo de entorno (en el contenedor, `/etc/nestbot/nestbot.env`, chmod 600):

```ini
TELEGRAM_TOKEN=          # token de @BotFather
ALLOWED_CHAT_IDS=        # vacío = el primero que escriba queda registrado
CAST_UUID=               # UUID del dispositivo, no su IP
```

`ALLOWED_CHAT_IDS` vacío deja el bot **abierto**: cualquiera que lo encuentre puede usarlo.
Se deja así solo para el alta inicial; una vez que sabés tu chat ID, se completa y se reinicia.

## Despliegue

Corre en el CT 300 del Proxmox de casa. Ver `CLAUDE.md` para direcciones y trampas conocidas.
