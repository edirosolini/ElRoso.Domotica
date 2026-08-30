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
- **Open-Meteo** para el clima: sin cuenta, sin API key, sin límite práctico. Es la única
  dependencia externa además de Telegram.
- **pychromecast** — control del parlante.
- **python-telegram-bot** en modo *long polling*.
- **APScheduler** + SQLite para timers y alarmas que sobreviven un reinicio.

## Dónde corre

**CT 300 `nest-bot`** del Proxmox de casa (`192.168.68.60`), en `192.168.68.10`.
El servicio vive en `/opt/domotica`, la config en `/etc/domotica/domotica.env` (chmod 600).

## Sobre el Asistente de Google

**No se puede tocar.** El Asistente del Nest corre en la nube de Google; desde acá solo se
le manda audio para reproducir. Si contesta "no entiendo", eso se arregla en la app Google
Home (dirección del hogar, idioma, Voice Match), no en este código.

Por eso `/clima` **no** usa el Asistente: consulta Open-Meteo y lo dice con la voz del bot.
Cualquier "inteligencia" que se le quiera agregar al parlante va por este camino — un
comando propio que consulta y habla — nunca intentando engancharse al Asistente.

Al 2026-08-30 el Nest está en `locale es-419` y zona horaria de Buenos Aires, o sea que su
configuración regional es correcta y no es la causa de las fallas del Asistente.

## Horario de descanso

De 23:00 a 07:00 (`QUIET_FROM`/`QUIET_TO`) **nada se dice en voz alta**: el aviso va solo a
Telegram, con el motivo. Aplica a las alarmas y también a `/decir` y `/clima` manuales.

La decisión de incluir los comandos manuales es deliberada: la regla existe para no despertar
a nadie, y quien escribe a las 3 AM está despierto pero el resto de la casa no. Si alguna vez
hace falta una excepción por mensaje, cuidado con la palabra clave elegida: `en <equipo>` ya
enseñó que un prefijo que también puede ser texto real se come parte del mensaje.

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
  el televisor se apaga solo si está configurado para dormirse al perder señal. El apagado
  real pide ADB, y los dos equipos de la casa son Google TV, así que los dos podrían.
- 🔴 **El `model_name` de mDNS no dice si el equipo es Android TV.** Un **Chromecast con
  Google TV** se anuncia como `Chromecast`, igual que uno viejo sin sistema operativo. No
  deducir capacidades de ese string: preguntarle al equipo o al dueño.
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
