# Domótica — El Roso

Automatización de la casa, manejada por **Telegram**. Hoy hace hablar al parlante;
está pensado para sumar dispositivos (luces) sin rediseñar nada.

**No es un producto de El Roso, es laboratorio.** Corre en la red de casa, no en el VPS.

## Estructura

```
Domotica/
├── src/homeauto/
│   ├── config.py        # carga y validación del archivo de entorno
│   ├── timespec.py      # parser de "10m", "7:30", "mañana 8:00"
│   ├── bot/             # comandos, sin nada de Telegram adentro
│   ├── schedule/        # timers, alarmas, preferencias por chat
│   ├── voice/           # equipos cast: tts, cast, registro
│   └── main.py          # cableado y ciclo de vida del proceso
├── deploy/              # unit de systemd y script de despliegue
├── tests/
└── requirements*.txt
```

Carpeta del proyecto en español (convención de `~/Proyectos/ElRoso`), **código en inglés**:
el paquete es `homeauto`, no `domotica`.

## Stack

- **Python 3.13** en el contenedor, 3.12 en la notebook. Nada específico de versión.
- **piper-tts** — síntesis de voz **offline**, voz `es_AR-daniela-high`. No sale a internet.
- **pychromecast** — control del parlante.
- **python-telegram-bot** en modo *long polling*.
- **APScheduler** + SQLite para timers y alarmas que sobreviven un reinicio.

## Dónde corre

**CT 300 `nest-bot`** del Proxmox de casa (`192.168.68.60`), en `192.168.68.10`.
El servicio vive en `/opt/domotica`, la config en `/etc/domotica/domotica.env` (chmod 600).

## Gotchas

- 🔴 **Los dispositivos Google se resuelven por UUID, nunca por IP.** Son DHCP y se mueven:
  el Nest ya saltó de `.13` a `.20` solo. Los UUID están en `CAST_DEVICES`.
- **Los equipos con pantalla solo aparecen en el descubrimiento si están encendidos.** Un
  Google TV apagado no existe para mDNS. No es un error: es que no está.
- 🔴 **La app que está corriendo es dueña de la sesión de medios.** Con YouTube abierto en
  un Chromecast, un `play_media` se lo come YouTube y el anuncio se pierde **en silencio**.
  Hay que desalojar la app ajena primero. El receptor propio (`CC1AD845`) se respeta:
  relanzarlo cortaría el audio en curso.
- 🔴 **Confirmar que empezó a sonar, y que suena lo que se pidió.** Por un instante el
  dispositivo sigue reportando el clip anterior como `PLAYING`: aceptarlo es informar que la
  casa fue avisada cuando no salió nada por los parlantes.
- **No existe apagar por Cast.** Lo máximo es `quit_app()`, que deja el equipo en reposo;
  el televisor se apaga solo si está configurado para dormirse al perder señal.
- **Castear a un equipo con pantalla prende el televisor.** Tenerlo en cuenta antes de
  mandar una alarma de las 7 AM al comedor.
- **Un Speaker por equipo, pero síntesis y servidor HTTP compartidos.** Lo único distinto
  entre equipos es el Caster; duplicar lo demás sería sintetizar dos veces la misma frase.
  Los Speaker se construyen recién al usarse: al arrancar, casi todos los equipos están
  apagados.
- 🔴 **IPv6 roto en los contenedores.** Solo tienen link-local `fe80::`, sin IPv6 global.
  Como el DNS devuelve el AAAA y glibc prefiere IPv6, cualquier cliente HTTP se cuelga
  20 s contra hosts doble stack (`api.telegram.org`). Se arregla con
  `precedence ::ffff:0:0/96  100` en `/etc/gai.conf`. **Aplicarlo en todo CT nuevo.**
- **El que castea sirve el audio por HTTP desde sí mismo**, y el parlante tiene que poder
  alcanzar ese puerto. No es "mandarle un archivo": es publicarlo y pasarle la URL.
- 🔴 **No parar el browser de zeroconf antes de conectar.** `pychromecast` lo necesita vivo
  para abrir la conexión: si se llama `stop_discovery()` antes de `wait()`, el dispositivo
  aparece en el descubrimiento pero la conexión muere con un timeout de 20 s sin explicación.
  Por eso `_Discovery` guarda el browser.
- **`catt` no sirve** para archivos locales — falla siempre con "Playback of local file has
  failed". Se descartó a favor de `pychromecast` directo, que anda.
- **Audios de menos de ~1 s** terminan sin pasar nunca por estado `PLAYING`. Hay que padear
  silencio o no hay forma de confirmar que sonaron.
- **onnxruntime** tira `pthread_setaffinity_np failed` dentro del LXC. Es inocuo:
  se silencia con `OMP_NUM_THREADS=1`.
- **Telegram por long polling**: no expone ningún puerto a internet. No abrir nada en el router.
- 🔴 **APScheduler lee un datetime naive como UTC.** Todo el proyecto trabaja en hora local
  (el CT está en `America/Argentina/Buenos_Aires`). Un naive `23:14` se agendaba a las 23:14
  UTC — tres horas en el pasado — y el timer disparaba al instante. `JobQueueTimer` le pega
  `astimezone()` antes de agendar. En los logs se veía como `Run time of job was missed by
  2:59:00`, que parece un problema de carga y no de husos.
- 🔴 **Nada bloqueante en el event loop.** Los handlers de Telegram son async, pero el
  descubrimiento (zeroconf) y la síntesis (Piper) son bloqueantes. Llamados desde dentro del
  loop, zeroconf **no descubre nada** y todos los comandos responden "no encontré el
  dispositivo", con un warning suelto de `unregister_all_services skipped as it does blocking
  i/o` como única pista. Todo comando va por `asyncio.to_thread`; hay test que lo verifica.
- **La config se lee una sola vez, al arrancar.** Cambiar el token o `ALLOWED_CHAT_IDS` en
  `/etc/domotica/domotica.env` no tiene efecto hasta `systemctl restart domotica`. Sin reiniciar,
  el servicio sigue con el token viejo y no avisa nada.

## Convenciones

- Mensajes al usuario del bot en **español**; identificadores, logs y comentarios técnicos en inglés.
- Los tests no tocan hardware real: se mockea `pychromecast` y el subproceso de Piper.
  La verificación con el parlante de verdad es un paso aparte, manual.
- Nada de tokens ni chat IDs en el repo. Viven en el archivo de entorno del contenedor.

## Memoria local

`.claude/memory/` (no se commitea, está en `.gitignore`). El backlog es
`.claude/memory/backlog.md` — este proyecto **no** tiene board externo.
