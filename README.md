# Domótica

Bot de Telegram que maneja dispositivos de casa. Hoy: hacer hablar al parlante Google Nest
con voz sintetizada offline. Timers, alarmas y recordatorios incluidos.

## Comandos

```
/decir buenas noches            habla ahora
/decir en tv que bajen a comer  lo dice en ese equipo
/llamar a cenar                 llama a toda la casa; sin nada, a lo que toque
/timer 10m sacá la pizza        avisa una vez, dentro de 10 minutos
/timer mañana 10:00 médico      avisa una vez, a esa hora
/recordar diaria 8:00 pastilla  recordatorio todos los días
/recordar lun-vie 7:30 colegio  recordatorio solo esos días
/recordar mensual 10 9:00 luz   recordatorio el 10 de cada mes
/recordar para China diaria 8:00 pastilla  para alguien de la casa; también «para todos»
/pastillas                      cuántas quedan de cada remedio
/pastillas 7 enalapril 30       cada «Hecho» del recordatorio #7 descuenta una
/pastillas enalapril +30        repone
/pastillas enalapril aviso 5    avisa con 5 o menos (por defecto, 7)
/turnos 7 Cin, Die              el #7 le toca a uno por semana
/turnos 7 off                   lo corta
/turnos                         lo que se turna y a quién le toca
/menu                           qué se come esta semana, almuerzo y cena
/menu nuevo sin carne           la vuelve a armar con ese pedido
/menu compras                   pasa a compras lo que queda de hoy
/menu compras semana            lo de toda la semana
/menu otra 2026-10-21 cena      cambia ese plato
/alarma 7:30 arriba             para despertarse, una vez
/alarma diaria 7:30 arriba      para despertarse, todos los días
/alarma lun-vie 5:30 arriba     para despertarse, solo esos días
/alarma hábiles 6:30 arriba     de lunes a viernes, salvo feriados
/alarma mensual 10 9:00 luz     el 10 de cada mes
/alarma en comedor para China 7:30 arriba  en ese equipo, para esa persona
/lista                          lo que está programado
/cancelar 3                     cancela por número
/posponer                       repite en 10 minutos la alarma que acaba de sonar
/silencio 2h                    no habla por un rato
/hablar                         cancela el silencio
/vacaciones hasta 25/10         no habla hasta la vuelta, ni lo urgente
/vacaciones off                 las corta
/volumen 40                     0 a 100
/parar                          corta lo que esté sonando
/apagar en todos                cierra la app y deja los equipos en reposo
/pantalla                       la pantalla de la casa en la tele del comedor
/pantalla en recamara           en otra tele
/pantalla apagar                la saca
/clima                          dice el pronóstico en voz alta
/preguntar cuánto mide el Aconcagua   lo averigua y lo contesta en voz alta
/agenda                         qué te queda hoy
/agenda mañana                  el día siguiente completo
/estado                         cómo están los servicios vigilados
/equipos                        qué equipos hay y cuál está activo
/usar tv                        cambia el equipo por defecto
/depurar                        cuenta lo que sobra: teles, avisos, historial, audio y listas; borra solo al confirmar
/depurar historial 6            deja seis meses de historial y propone borrar lo cerrado de antes
```

**Horario de descanso.** De **23:00 a 07:00** por defecto, nada suena en voz alta: el aviso llega igual a
Telegram, pero los parlantes se quedan callados. Vale para las alarmas y también para un
`/decir` manual — la regla protege a los que duermen, no a quien está escribiendo. Se cambia
con `QUIET_FROM` y `QUIET_TO`; poniendo las dos iguales se desactiva.

**Volumen mínimo.** Todo lo que la casa dice —un `/decir`, una alarma, el clima, el resumen,
un aviso del monitor— **sube el volumen a 60 si está más bajo**, y lo devuelve a como estaba
en cuanto termina de hablar. Una casa en volumen bajo convierte cualquier anuncio en nada.
Si el equipo ya está en 60 o más, no se toca. Una alarma usa un piso de **90**: es para
despertar. El `/volumen` que pongas sigue siendo el de la música: esto solo aplica mientras
habla el bot.

**Silencio a pedido.** Para una siesta o una reunión, `/silencio 2h` calla los parlantes por
ese rato (acepta los mismos formatos que un timer: `30m`, `1h30m`). `/silencio` sin nada dice
si está callado y hasta cuándo; `/hablar` lo cancela. Se guarda en SQLite, así que un
reinicio en medio de la siesta no devuelve la casa hablando.

**Modo vacaciones.** `/vacaciones hasta 25/10` calla la casa hasta la vuelta; con hora,
`/vacaciones hasta 25/10 18:00`, y sin hora es a las 00:00. `/vacaciones 25/10` también
sirve. Una fecha que ya pasó este año se toma del siguiente; hoy o antes se rechaza.
`/vacaciones off` las corta y `/vacaciones` sola dice cómo están. Mientras duran **nada sale
por los parlantes, ni lo urgente**: las alarmas, el monitor, la API, el resumen, el cierre,
el clima y la agenda llegan solo al chat, con sus botones. Una alarma no repite y no trae
«🔕 Apagar», y activarlas corta las que estén sonando. `/decir`, `/llamar` y lo que pidas
«por el parlante» contestan por qué no suena; `/apagar`, `/parar` y `/volumen` siguen
andando. Activarlas o cortarlas les avisa a los otros chats quién fue, y al terminar se
escribe a todos «🧳 Terminó el modo vacaciones, vuelvo a hablar.». `/hablar` no las corta.
Se guardan en SQLite: si vencen con el servicio caído, el aviso sale al arrancar.

**Resumen de la mañana.** A la hora de `BRIEFING_AT` (por defecto 08:00, `off` lo apaga) dice
de una vez lo que hay para el día: si es feriado, la agenda, el clima, la economía, qué
servicios vigilados no responden, los errores de la noche y, al final, el versículo del día. Los titulares van solo
al chat. Si todo está en orden no nombra ningún servicio. No hace falta tener agenda
configurada: con el clima solo ya sirve, y una fuente que falla no se lleva puestas a las
otras. El detalle está en [El resumen de la mañana](#el-resumen-de-la-mañana).

**Cierre del día.** A la hora de `CLOSING_AT` (por defecto 22:00, `off` lo apaga) dice lo que
viene: qué tenés agendado mañana, cómo va a estar el día y qué servicios siguen sin responder.
Si no juntó nada que decir, se queda callado. Ponerlo después de `QUIET_FROM` lo deja escrito
en el chat, sin voz.

**Resumen semanal.** A la hora de `WEEKLY_AT` (por defecto el domingo a las 19:00, `off` lo
apaga) escribe a todos los chats el balance de los últimos siete días: cuántos días se marcó
«Hecho» cada recordatorio (`la pastilla: 5 de 7`, sumando lo pospuesto), las alarmas que
sonaron hasta el final sin que nadie las apagara y lo que no salió por el parlante. Los
timers no entran, y lo que no sonó por un feriado tampoco. Solo va al chat, nunca por el
parlante, y una semana sin nada que contar no manda nada.

**Cuentas y unidades.** `/calcular 15 por 4` hace la cuenta y `/calcular 20 grados en
fahrenheit` convierte. No pasa por ningún modelo: el número sale exacto y, si entra en el
rango que se puede decir, suena en palabras cuando lo pedís por el parlante.

**Listas.** `/agregar leche, pan` suma a la lista de compras y `/agregar a pendientes llamar
al plomero` a la otra. `/compras` y `/pendientes` las muestran numeradas, `/sacar 2` saca una
y `/sacar todo` la vacía. El cierre del día dice cuántas cosas quedan por comprar.

**Menú de la semana.** `/menu` muestra de lunes a domingo el almuerzo y la cena; si la semana
no está armada, la arma el modelo de texto (ver **Redacción más natural**) sin repetir los
platos de la semana anterior. El domingo ya muestra la semana siguiente. `/menu nuevo sin
carne` la rearma entera con ese pedido, y `/menu otra 2026-10-21 cena` cambia un plato y les
escribe a los demás «🍽 <nombre> cambió la cena del miércoles 21/10: …». `/menu compras` pasa
a la lista de compras los ingredientes de lo que queda de hoy, `/menu compras semana` los de
toda la semana y `/menu compras 2026-10-21 cena` los de un plato; lo que ya estaba no se
repite. Los ingredientes van sin cantidades, y la sal, el aceite, la pimienta y el agua no se
pasan; otro condimento con nombre propio, como el orégano, puede llegar a compras. Si lo que arma el modelo no sirve, no se guarda nada. Se lee y nunca
suena: pedido «por el parlante», contesta escrito y avisa por qué. `MENU_LUNCH_AT=off` o
`MENU_DINNER_AT=off` saca esa comida del menú. No está en el menú de Telegram: se escribe, se
pide sin barra o se toca «Menú» en el control. El kiosco muestra la próxima comida en «🍽 Idea
para hoy» (ver **La pantalla de la casa**).

**Aviso antes de cada comida.** A la hora de `MENU_LUNCH_AT` (11:00) y de `MENU_DINNER_AT`
(17:30) les escribe a todos el plato de hoy, solo escrito: «🍽 Idea para el almuerzo:
Milanesas con puré.» y abajo «Lleva: carne, pan rallado, huevo, papa.», con «🛒 Pasar a
compras» para los ingredientes de ese plato y «🔄 Otra idea» para cambiarlo. Usa la semana de
hoy, también el domingo. Si la semana no está armada y la anterior sí, la arma sin repetir sus
platos. No manda nada si nunca hubo menú, si a la semana le falta esa comida, si el modelo
falla o en vacaciones; el horario de descanso no lo frena. `off` en la clave apaga ese aviso.

**Traducir.** `/traducir hola` va de español a inglés y al revés; `/traducir al francés hola`
al idioma que pidas. Vuelve escrito y nunca por el parlante: la voz de la casa habla español
y leería el resto con fonética española.

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

**La pantalla en la tele.** `/pantalla` pone el kiosco de la casa en la tele de
`SCREEN_DEVICE` (por defecto, el comedor), con `en <equipo>` en otra, y `/pantalla apagar`
la saca; la respuesta trae el botón «Apagar pantalla». En la tele va **solo para mirar**: sin
campos para agregar ni círculos para tachar. Apagar solo cierra la pantalla si sigue puesta:
si alguien abrió otra app, no la toca. Si la casa habla por esa tele, la pantalla vuelve sola
al terminar el anuncio. Funciona en horario de descanso, porque no hace ruido, pero no de
vacaciones. Qué equipos tienen pantalla se configura en `SCREEN_DEVICES`: a uno que no está
ahí le contesta que no tiene pantalla. Sin `API_TOKEN` no hay pantalla que mostrar.

**Alarma en la tele.** Una alarma en un equipo de `SCREEN_DEVICES` prende la tele con la hora
grande, el mensaje y para quién es durante un minuto después de cada sonido, y entre una repetición y la
siguiente muestra el kiosco. Cuando deja de sonar pasa sola al kiosco, y a los 15
minutos se cierra, si nadie puso otra cosa. En descanso o de vacaciones no se prende.

**Elegir equipo.** Cualquier comando acepta `en <equipo>` adelante y va solo a ese; `/usar`
cambia el que se usa cuando no decís nada, y queda guardado por chat. Un timer recuerda a
qué equipo iba, así que se puede programar en uno y seguir hablando por otro.

`en` solo se interpreta como destino si la palabra siguiente es un equipo conocido:
`/decir en casa hace frío` dice la frase entera, no se come nada.

**Alarma, recordatorio y timer suenan distinto.** La alarma es para despertarse: un despertador
de ráfagas que suben de volumen, el parlante a 90 como mínimo, «🔕 Apagar» y «Posponer». Si
nadie la apaga, vuelve a sonar cinco minutos después de terminar, con un despertador más largo, durante
media hora: cinco repeticiones más. Cada una escribe «Sigue sonando» al chat, también en
horario de descanso, y al final avisa «Dejé de sonar».
«Apagar» funciona desde cualquier chat, corta lo que esté sonando y les avisa a los demás
quién la apagó; posponer, `/cancelar` o borrarla también cortan la repetición. El recordatorio (`/recordar`) repite siempre en los días marcados —una
medicación, salir al colegio— y el timer es de una sola vez; los dos suenan con un beep suave
y traen «✅ Hecho» además de posponer. «Hecho» vale desde cualquier chat y les avisa a los demás chats quién lo
marcó, y ya no se puede posponer. Si nadie lo toca, el chat insiste a los 5, 10 y 15
minutos con «🔔 Sigue pendiente» (con el nombre adelante si era para alguien: «🔔 Enano, sigue
pendiente: …»), solo con «Hecho», y el parlante lo dice con el beep suave:
«Sigue pendiente: tomar la pastilla.», con el nombre adelante si era para alguien. En descanso,
silencio o vacaciones solo se escribe. «Hecho», posponer o `/cancelar` lo cortan. Un recordatorio sin días no se agenda:
para algo de una sola vez está `/timer`.

**Pastillas que se acaban.** `/pastillas 7 enalapril 30` ata el recordatorio #7 a un remedio
con 30 dosis, y cada «Hecho» de ese recordatorio descuenta una; un doble toque no descuenta
dos veces y nunca baja de cero. Dos tomas pueden contar del mismo remedio: se atan al mismo
nombre, sin importar mayúsculas. Sin cantidad, ata si el remedio ya existe y si no pregunta
cuántas hay; si ya existe y escribís una cantidad, la fija en vez de sumarla. Con 7 o menos (se cambia
con `/pastillas enalapril aviso 5`) escribe una sola vez a todos «💊 Quedan 7 de enalapril,
comprar.» y lo suma a `/compras` si no estaba; no suena por el parlante. `/pastillas
enalapril +30` repone y, si queda por encima del aviso, lo vuelve a armar. Solo se atan
recordatorios que repiten, y un recordatorio pospuesto sigue contando del mismo remedio.

**Tareas por turno.** `/turnos 7 Cin, Die` hace que el #7 le toque a uno distinto cada
semana, de lunes a domingo, en ese orden y empezando por el primero esta semana: el aviso dice
«Le toca a Cin: sacar la basura», y también lo pospuesto, el «Hecho» y la pantalla. Los
nombres se separan por comas o por «y» y van solo con letras y espacios, porque se dicen en
voz alta; un solo nombre también vale. Solo se turna lo que repite, y lo puede hacer
cualquier chat. Volver a correr `/turnos` sobre el mismo número arranca la cuenta de nuevo
esta semana; `/turnos 7 off` lo corta y `/lista` muestra los nombres. No se puede cambiar el
turno a mano ni saltear una semana. Si un nombre no es de una persona cargada en la casa, la
respuesta lo avisa: en su semana el aviso no va a su chat.

**Para quién es.** `/timer`, `/alarma` y `/recordar` aceptan `para <persona>`, `para todos`
o `para nadie`, después de `en <equipo>` y antes de los días y la hora:
`/alarma en comedor para China lun-vie 7:30 arriba`. Al sonar, uno de una persona con
Telegram le llega solo a ella, y el parlante dice «China, arriba». La persona tiene que estar
cargada en «👪 Personas», en `/control`; los nombres de varias palabras valen y no importan
las mayúsculas. Con un nombre que no está, contesta que no está en el padrón y no programa
nada. La respuesta y `/lista` muestran « · para China». Sin `para`, es como siempre: para
nadie en particular.

**Llamar a alguien en el aviso.** Un mensaje que empieza con el nombre entre corchetes,
`/recordar diaria 9:00 [Papá] tomar medicación`, suena y se escribe «Papá, tomar medicación».
El nombre va solo con letras y espacios, al principio; cualquier otro corchete queda como se
escribió. Lo escrito de «Sigue sonando» y `/lista` lo siguen mostrando entre corchetes; lo
dicho sale «Papá, …», y «Sigue pendiente» lo escribe con el nombre adelante.

Los timers, las alarmas y los recordatorios se guardan en SQLite y **sobreviven un reinicio**. Lo que venció
mientras el servicio estaba caído se anuncia al arrancar, en vez de perderse.

Formatos de tiempo aceptados: `10m`, `5min`, `2h`, `90s`, `1h30m`, `23:15`, `5.30`,
`mañana 8:00`. Una hora que ya pasó se entiende como la de mañana.

Una alarma o un recordatorio puede repetirse los días que se le pidan, escribiéndolos antes de la hora:
rangos (`lun-vie`, `vie-lun` cruza el fin de semana), listas (`mar,jue`), un día suelto
(`sab`) o los atajos `finde`, `semana` y `hábiles`. Se aceptan nombres completos y con acento
(`miércoles`). Los días eligen qué ocurrencia de la hora dispara, así que ahí la hora es
obligatoria: `/alarma lun-vie 10m` no tiene sentido y se rechaza.

**Feriados.** `hábiles` (o `habiles`) es de lunes a viernes **y además no suena en
feriados**: `/alarma hábiles 6:30 arriba`, `/recordar hábiles 7:00 salida al colegio`.
`lun-vie` y `semana` suenan igual en un feriado. Ese día el bot no dice nada y escribe a
todos «🏖 Feriado (<nombre>): hoy no suena «arriba»»; al día siguiente vuelve a
su horario. Cuentan los feriados nacionales inamovibles y trasladables; un día puente
suena. Salen de argentinadatos, sin cuenta ni API key: se
bajan al arrancar y todos los días a las 4 de la mañana, y desde noviembre también los del
año siguiente. Si no se pueden bajar se usan los últimos que se bajaron, y si nunca se
bajaron, todo suena. Solo aplica a lo que repite por días de la semana; las alarmas y
recordatorios que ya existían no cambian.

Para una vez por mes, `mensual` y el día del mes antes de la hora:
`/recordar mensual 10 9:00 pagar la luz`. La hora también es obligatoria. Si el mes no tiene
ese día, suena el último día del mes y al siguiente vuelve al pedido: un 31 suena el 31 de
enero, el 28 de febrero y el 31 de marzo; al crearlo, el bot lo avisa. Los timers no repiten,
tampoco por mes.

## Sin la barra (opcional)

Con la clave del modelo de texto cargada (ver **Redacción más natural**), un mensaje suelto
también se entiende. No hace falta acordarse de
ningún comando:

```
decí que ya llegué                        →  /decir que ya llegué
decile a todos que la comida está lista   →  /decir en todos que la comida está lista
poneme un timer de 10 minutos para la pizza  →  /timer 10m sacar la pizza
despertame a las 7 y media                →  /alarma 7:30 despertame
recordame la pastilla todos los días a las 8  →  /recordar diaria 8:00 la pastilla
recordame el 10 de cada mes a las nueve pagar la luz  →  /recordar mensual 10 9:00 pagar la luz
recordame los días hábiles a las siete salida al colegio  →  /recordar hábiles 7:00 salida al colegio
recordale a China tomar la pastilla todos los días a las ocho  →  /recordar para China diaria 8:00 tomar la pastilla
recordale a Papá en media hora sacar la ropa  →  /timer para Papá 30m sacar la ropa
bajá el volumen a 40                      →  /volumen 40
callate una hora                          →  /silencio 1h
nos vamos de vacaciones hasta el 25 de octubre  →  /vacaciones hasta 25/10
cuánto mide el Aconcagua                  →  /preguntar cuánto mide el Aconcagua
compré 30 de enalapril                    →  /pastillas enalapril +30
la basura la sacan Cin y Die una semana cada uno, es el 7  →  /turnos 7 Cin, Die
armá otro menú sin carne                  →  /menu nuevo sin carne
pasá a compras lo del menú de la semana   →  /menu compras semana
llamá a todos a cenar                     →  /llamar en todos a cenar
poné la pantalla en la tele de la recámara  →  /pantalla en recamara
limpiá las teles viejas                   →  /depurar teles
```

**Ejecuta y te dice qué entendió**, no pregunta antes. La respuesta arranca con
`Entendí: /timer 10m sacar la pizza`, así que si leyó mal se ve en el acto y se deshace con
`/cancelar`. Tarda alrededor de un segundo más que escribir el comando a mano.

⚠️ **Lo que la casa dice en voz alta siempre sale de tu mensaje.** El intérprete puede elegir
el comando y el equipo, pero no puede reescribir el texto de un `/decir`: si lo que quedaría
para decir no está en lo que escribiste, no lo dice y lo trata como pregunta. Un mensaje
inventado en boca de la casa es peor que no entender.

**Si falta un dato, te lo pregunta.** «creá una alarma» no es un error: es media orden, así
que el bot pide la otra mitad y se acuerda de lo que ya le dijiste.

```
vos:  creá una alarma
bot:  ¿A qué hora?
vos:  a las 7
bot:  ¿Qué querés que diga?
vos:  arriba
bot:  ¿Una sola vez, todos los días, o algunos días?
vos:  de lunes a viernes
bot:  Entendí: /alarma lun-vie 7:00 arriba
      Alarma lun, mar, mié, jue, vie #3 en parlante para mañana 07:00: «arriba»
```

Solo pregunta lo que **falta**: `dame el clima` se ejecuta de una, como siempre. Un comando
completo en medio de la charla gana —«dame el clima» mientras armás una alarma es un comando,
no una respuesta— y **`olvidalo` deja lo que estaba a medio armar**. Si te vas, vence solo a
los diez minutos: una respuesta de la nada no puede caer en una pregunta de hace media hora.

Lo que quedó a medio armar se guarda en SQLite, así que un reinicio en medio de la charla no
pierde el hilo.

Los comandos con barra siguen funcionando igual y no pasan por el intérprete.

## Preguntas (opcional)

`/preguntar` manda la pregunta a un modelo con búsqueda, escribe la respuesta en el chat y
dice un resumen por el parlante. El proveedor sale de `ASK_PROVIDER` (`google` o
`anthropic`); vacío, usa el mismo que la redacción. Así el texto puede ir con Gemini y las
preguntas con Claude.

```
/preguntar top 10 de los mejores goles de Messi
```

**Lo escrito y lo dicho no son el mismo texto, a propósito.** Una respuesta de búsqueda está
llena de años y cifras, y el sintetizador lee un dígito como un número suelto mal declinado.
Así que al chat va la respuesta completa y al parlante una o dos oraciones con los números en
palabras. Un top diez dicho entero también sería un minuto de parlante.

Si esa versión hablada no se puede confiar —le quedó un dígito, vino vacía o se fue de largo—
el parlante dice **"te lo dejé escrito en el chat"** y no lee nada más. La respuesta nunca se
pierde: siempre está escrita.

**Contestar tarda.** Sale a buscar, y medido contra la API real las respuestas tardaron entre
8 y 40 segundos. Espera hasta 60. Mientras tanto el bot sigue atendiendo todo lo demás.

⚠️ **No le pongas acá el modelo del pulido.** `/preguntar` usa un modelo distinto a propósito:
con las mismas cuatro preguntas, el `flash-lite` que pule los avisos **usó la búsqueda en una
de cuatro** y contestó el resto de memoria — se inventó la temperatura del momento. Un flash
entero buscó en las cuatro. Para pulir una frase el lite sobra; para contestar no alcanza.

```ini
ASK_PROVIDER=anthropic                 # google o anthropic; vacío hereda LLM_PROVIDER
ASK_MODEL=gemini-3.7-flash             # default; vacío usa este mismo
ANTHROPIC_ASK_MODEL=claude-sonnet-5-5  # el de Claude; NO hereda de ANTHROPIC_MODEL
```

`ASK_PROVIDER=anthropic` sin `ANTHROPIC_API_KEY`, o un valor que no sea `google` ni
`anthropic`, y el servicio no arranca. `ASK_PROVIDER=google` sin `LLM_API_KEY` apaga solo
`/preguntar`. Al arrancar, el log dice con qué va cada uno: «texto con google:
gemini-3.1-flash-lite, y las preguntas con anthropic: claude-sonnet-5-5».

Con Claude pasa lo mismo, más marcado: Haiku, el barato, **no tiene búsqueda web**. Por eso
`/preguntar` va con Sonnet, que busca hasta tres veces por pregunta.

## Redacción más natural (opcional)

Todo lo que la casa dice puede pasar por un modelo de lenguaje para que suene mejor en voz alta:
agenda, clima, avisos de evento, el mensaje de un timer o una alarma, los avisos del monitor y
de Seq, el aviso de lluvia y lo que entra por la API. El uso real son decenas de llamadas por
día: con Google entra en el free tier de sobra.

La respuesta de `/preguntar` **no** pasa por acá: ya es prosa de un modelo, y una segunda
pasada solo sumaría espera.

**`/decir` no pasa por acá: se corrige, no se reescribe.** Ahí las palabras son tuyas y
siguen siendo tuyas; lo que se arregla es cómo quedaron escritas. En todo lo demás el original
siempre gana cuando el modelo falla, tarda o contesta algo sospechoso: nadie se queda sin
aviso porque un modelo estaba lento.

**Lo que escribís se dice bien escrito.** Antes de sintetizar, `/decir` pasa por una
corrección que arregla la ortografía y **no puede cambiar ninguna palabra**:

```
vos:   deci a Diego que es hoa de comer
suena: «Diego, es hora de cenar»          ← a las 21:30
bot:   Ya le avisé: «Diego, es hora de cenar»

vos:   avisales q llego en 1 minuto
suena: «Avisales que llego en un minuto»  ← antes sonaba "uno minuto"
```

Tres cosas puede tocar, y nada más: la ortografía y la puntuación, los números —que pasan a
palabras porque el sintetizador lee mal un dígito— y **la comida, que sigue al reloj**: "es
hora de comer" a la noche es cenar, y al mediodía almorzar. Si el modelo intenta cualquier
otra cosa —agregar una palabra, sacarla, dar vuelta la frase— se descarta y se dice tal cual
lo escribiste. Sin clave tampoco cambia nada.

```
antes:  Atención: Dentista, en diez minutos, en Consultorio.
ahora:  Tenés turno con el dentista en diez minutos en el consultorio.
```

**El proveedor se elige con `LLM_PROVIDER`**: `google` (default) o `anthropic`. El mismo vale
para la redacción, el texto sin barra, la corrección de `/decir`, `/traducir` y `/menu`. `/preguntar`
lo hereda salvo que `ASK_PROVIDER` diga otro (ver **Preguntas**).

Con Google, se saca una clave en [Google AI Studio](https://aistudio.google.com/apikey):

```ini
LLM_API_KEY=              # sin clave, apagado: el texto sale tal cual
LLM_MODEL=gemini-3.1-flash-lite
```

Con Claude, una clave de la [consola de Anthropic](https://console.anthropic.com/):

```ini
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=        # obligatoria con anthropic: sin ella el servicio no arranca
ANTHROPIC_MODEL=claude-haiku-5-5
```

⚠️ **Las notas de voz se transcriben siempre con Google**, porque Claude no acepta audio. Con
`LLM_PROVIDER=anthropic`, dejá también `LLM_API_KEY`: sin ella el texto anda y los audios
contestan «No escucho audios».

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

curl -s https://api.anthropic.com/v1/messages \
  -H "content-type: application/json" -H "anthropic-version: 2023-06-01" \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -d '{"model":"claude-haiku-5-5","max_tokens":64,"messages":[{"role":"user","content":"decí hola"}]}'
```

**Lo que el modelo no puede hacer.** Solo reescribe; no informa. La respuesta se descarta —y se
dice el texto original— si trae dígitos, si cambia un número, una hora o un momento del día, si
pierde el título de un evento, o si se va de largo. Si la API falla o tarda, también gana el
original: nadie se queda sin aviso porque el modelo estaba lento.

⚠️ **Esto mejora la redacción, no la voz.** El timbre lo pone Piper y sigue igual.

## El resumen de la mañana

A la hora de `BRIEFING_AT` la casa dice, en un solo texto: si hoy es feriado y por qué, qué
hay en la agenda, cómo está el cielo, los tres números de la economía, qué servicios están
caídos, los errores de Seq de las últimas doce horas, los titulares del día y, al final, el
versículo del día. Los servicios
caídos y los errores de la noche solo se escriben a los chats de `ALERT_CHAT_IDS`; el
parlante los dice igual.

**Las fuentes son independientes**: la que no contesta deja un hueco, nunca cancela el
resumen. Un calendario caído no te puede costar el clima.

**Economía** (`ECONOMY=off` la apaga): dólar oficial, riesgo país e inflación del último mes
publicado. Sale de dolarapi y argentinadatos — gratis, sin cuenta y sin API key, igual que el
clima. Un número que no se pueda decir en palabras se calla: al parlante nunca le llega un
dígito.

**Noticias** (una clave `NEWS_RSS_<MEDIO>` por medio): los titulares salen del RSS de los
medios configurados, tomando turnos entre ellos — cinco titulares de un solo diario son su
portada, no las noticias del día. **Solo van al chat**, enteros y con sus cifras: son lo más
largo del resumen y lo único que no se puede accionar, así que se leen en vez de escucharse.

**Versículo del día** (`VERSE=off` lo apaga): el de YouVersion, en la Nueva Traducción
Viviente. Cierra lo hablado con la referencia en palabras —"de Salmos, capítulo diecinueve,
versículo catorce"— y el texto tal cual. Sin cuenta ni API key. Si el texto trae un número,
no se dice: queda escrito en el chat.

De la agenda, el resumen dice la hora y el título; el lugar queda para `/agenda`.

**Feriado**: arranca con «Hoy es feriado: <motivo>.», con el nombre como lo publica
argentinadatos. Dicho, las abreviaturas van enteras («Gral.» es «General») y un número
romano después de un nombre va en palabras («León XIV» es «León catorce»); si aun así
quedara un número, dice solo «Hoy es feriado.». Un día puente es «Hoy es día no laborable.».

## Avisos del cielo

Además del resumen, la casa avisa sola cuando algo del pronóstico lo amerita. Cada aviso sale
**una vez por día** y ninguno le come el turno a otro:

| aviso | cuándo |
| --- | --- |
| lluvia | 60% o más de probabilidad en las próximas 6 horas |
| tormenta | tormenta pronosticada en las próximas 6 horas |
| viento | ráfagas de 50 km/h o más en las próximas 6 horas |
| calor | máxima del día de 33° o más |
| frío | mínima del día de 3° o menos |
| sol | índice ultravioleta máximo del día de 11 o más (extremo) |
| aire | peor índice de calidad del aire (US AQI) de 101 o más entre las 8 y las 20 |

El calor, el frío, el sol y el aire se avisan **entre las 7 y las 11**: son sobre el día
entero y a las cuatro de la mañana no le sirven a nadie. Los umbrales son constantes del
código, no configuración. Ninguno de estos avisos entra en el resumen de la mañana.

La calidad del aire sale de la API de calidad del aire de Open-Meteo, también gratis y sin
clave. Es un modelo global (CAMS) de unos 40 km de resolución, no un sensor del barrio: sirve
para un día malo de verdad, no para el aire de la cuadra. El aviso no dice la cifra.

## Vigilancia de servicios

Dos señales que cubren agujeros distintos:

**El túnel.** Un chequeo TCP contra el servidor del VPS a través de WireGuard. Si no responde,
o se cayó el túnel o se cayó el VPS: en cualquier caso hay que ir a mirar. Los servicios a
vigilar viven en `/etc/domotica/checks.json`:

```json
[
  {"name": "vps", "host": "172.68.0.7", "port": 5341, "urgent": true},
  {"name": "landing", "url": "https://elroso.ar"}
]
```

Campos: `name`, y `url` **o** `host`+`port`. Opcionales: `expect` (código HTTP esperado),
`urgent`, `timeout`, `attempts`. Un campo desconocido hace fallar el arranque a propósito —
un typo en `urgent` significaría que nunca te despierta—, y también un `name` de más de
cincuenta y cuatro bytes, que no entra en el botón de confirmar.

**Confirmar una caída.** El aviso de caída trae «✅ Confirmar», además de «Ver estado» y
«Silenciar 1 h». Mientras nadie lo toque, la casa vuelve a avisar a los 5, 10 y 15 minutos y
después cada 30, con «Atención: X sigue sin responder» dicho y «🚨 Sigue caído: X» escrito,
hasta que alguien confirma o el servicio vuelve. Los re-avisos salen en la vuelta del
monitor, así que se pueden atrasar hasta un intervalo de chequeo, y sobreviven un reinicio.
Confirmar solo se puede desde un chat de `ALERT_CHAT_IDS` y les avisa a los otros chats de
alertas quién lo hizo. Un aviso urgente despierta una sola vez: los re-avisos suenan con los
tres beeps pero nunca pasan por encima del horario de descanso ni de `/silencio`, y ahí solo
se escriben. Silenciar no confirma. En modo vacaciones ni la primera caída urgente suena:
todo va solo al chat.

**Los logs.** Consulta Seq y avisa si hay errores nuevos. Seq dice *por qué* se rompió algo,
no solo que no responde; pero muere junto con el VPS, y por eso el túnel se vigila aparte.

Se vigila **un Seq por VPS**, con una clave de configuración por instancia
(`SEQ_URL_<ALIAS>` y `SEQ_API_KEY_<ALIAS>`), igual que los calendarios. El alias **se dice
en voz alta** —"hay dos errores nuevos en Seq de hosting externo"—, así que no lleva dígitos
ni guiones medios. Para un nombre de varias palabras se usa guion bajo, que al hablar se dice
como espacio: `SEQ_URL_HOSTING_EXTERNO`. ⚠️ Que pase la validación no quiere decir que se
entienda dicho: `vps` son letras y el sintetizador lo lee como palabra, no como siglas. Cada instancia lleva su propio enfriamiento y su propia
marca de hasta dónde leyó: un VPS ruidoso no puede tapar el aviso del otro. Con alias, una URL sin
su clave —o una clave sin su URL— **hace fallar el arranque**: saltearla en silencio dejaría
creyendo que se vigilan dos VPS mientras se vigila uno. El par suelto `SEQ_URL`/`SEQ_API_KEY`
de antes se sigue aceptando, sigue diciéndose "Seq" a secas y sigue apagándose sin ruido si
le falta una mitad: así está el env desplegado y no puede dejar de arrancar por eso.

**Internet.** Antes de los servicios, cada ronda prueba la salida de la casa: una conexión TCP
al 443 de `1.1.1.1`, `8.8.8.8` y `9.9.9.9`, por IP y con tres segundos de timeout; con que
conteste uno alcanza. Si no contesta ninguno, esa ronda no chequea los servicios ni consulta
Seq: un corte del proveedor no se avisa como caída del VPS. Corre aunque no haya
`checks.json`. Dos rondas seguidas sin salida declaran el corte, y la casa dice «Se cortó
internet.» una sola vez, con un beep suave, **solo por el parlante** y nunca en el horario de
descanso, con `/silencio` ni de vacaciones: ahí se pierde. Cuando vuelve, lo dice con cuánto duró y escribe a
todos los chats «🌐 Internet se cortó de HH:MM a HH:MM (N min)». Un corte de una sola ronda no
dice nada. El estado sobrevive un reinicio.

**El Proxmox.** Con `PVE_URL`, el monitor suma cuatro chequeos por la API del host:
`proxmox` (que conteste), `el disco del proxmox`, `las máquinas del proxmox` y
`los respaldos`. Se ven en `/estado`, traen «✅ Confirmar» y entran en la línea de caídos del
resumen y del cierre. Ninguno es urgente.

- **Disco**: los storages activos y la raíz del host. Avisa desde `PVE_DISK_ALERT` y vuelve
  recién cinco puntos por debajo, también después de un reinicio.
- **Máquinas**: las que arrancan con el host (`onboot=1`) y están paradas. Es el único de los
  cuatro que re-avisa. Un CT parado a propósito con `onboot=1` avisa: se calla con
  «Confirmar» o sacándole `onboot`.
- **Respaldos**: el último `vzdump` terminado. `WARNINGS` no es caída.
- Si la API no contesta, cae solo `proxmox`: los otros tres no cambian de estado esa vuelta.
  Lo mismo si falla una sola consulta o si todavía no hay respaldos.
- Dicho es genérico («el disco del proxmox está casi lleno»); la máquina, el storage y el
  porcentaje van solo en el chat.

`PVE_URL` y `PVE_TOKEN` van juntos: una sin la otra hace fallar el arranque, igual que una URL
que no sea `https`, un token con otra forma o una `PVE_CA_FILE` que falte o no exista. El
token va en el header y se valida el certificado contra la CA del Proxmox, nunca sin
verificar. El token del CT es de solo lectura (rol `PVEAuditor`).

Tres reglas evitan que esto se vuelva ruido, que es como mueren los monitores:

- Un fallo suelto no es una caída: hacen falta dos rondas seguidas para avisar.
- Se avisa **al cambiar de estado**; mientras dure, solo insiste si nadie confirmó la caída.
  La recuperación también se avisa, y
  nunca como urgente: no hay que despertar a nadie por una buena noticia.
- Los errores de Seq tienen enfriamiento (`SEQ_COOLDOWN_MINUTES`): un servicio roto logra
  cientos de errores por minuto y no puede convertirse en cientos de avisos. El enfriamiento
  corre por instancia, no para todas juntas.

## API para otros sistemas

Cualquier script puede hacer hablar la casa. El bot usa long polling y no expone nada, pero
esta API sí escucha, **solo en la LAN**: hacer hablar la casa pide token. No abrirla a
internet.

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
| `urgent` | `true` ignora el horario de descanso; el modo vacaciones, no |

**Sin `urgent`, dentro del horario de descanso el aviso va solo a Telegram** y la respuesta
lo dice (`"spoken": false`). Nada se pierde, pero nadie se despierta. En modo vacaciones
pasa lo mismo aunque venga con `urgent`.

El token se genera solo la primera vez y vive en `/etc/domotica/domotica.env`. Si no hay
token, la API no arranca — apagada es el estado seguro.

## La pantalla de la casa

El mismo servidor de la API sirve tres páginas para abrir desde el navegador, en cualquier
dispositivo de la casa, y una cuarta para la tele:

```
http://192.168.68.10:8099/agenda              # la agenda, en la última vista elegida
http://192.168.68.10:8099/agenda?m=2026-11    # abre en ese mes
http://192.168.68.10:8099/pantalla            # el kiosco, para dejar fijo en una pantalla
http://192.168.68.10:8099/pantalla?ver=1      # el kiosco solo para mirar, como va a la tele
http://192.168.68.10:8099/alarma?job=7        # la alarma #7 mientras suena; después, el kiosco
http://192.168.68.10:8099/control             # manejar la casa sin Telegram
```

**La agenda** junta lo de la casa y lo de Google Calendar. Arriba están el mes o la semana que
se ve, las flechas, «Hoy» y las vistas Mes, Semana, Día y Lista. Cada evento es un bloque de
color suave: las alarmas (⏰), los recordatorios (📌) y los timers (⏲️) tienen su color; cada
calendario de Google, el suyo, con la leyenda arriba. Lo que ya sonó dice cómo terminó: ✅ y
quién lo marcó, 🔔 los re-avisos o las repeticiones, 💤 pospuesto, ✖️ cancelado, 🔕 apagada y
quién, ⚠️ no sonó, 🏖 feriado. Los feriados aparecen como eventos de todo el día, y lo que
un feriado va a saltear dice «🏖 feriado, no suena». Lo que viene se
calcula igual que cuando suena. Un toque sobre un evento muestra el detalle. Si un calendario
no se pudo leer, lo dice arriba por su nombre y lo marca con ⚠ en la leyenda. Cada
dispositivo recuerda la última vista que se tocó; la primera vez abre en Mes en la
computadora y en Lista en el teléfono. Un enlace con `?m=` abre siempre en el mes. En una computadora el mes entra entero en la
ventana y cada día muestra lo que cabe; en el teléfono, hasta cinco eventos por día. El resto
queda en «+N más», y lo que ya pasó hoy se pliega bajo un «…» que lo despliega. Semana y Día
abren una hora antes de la actual. Se ve clara u oscura según el tema del dispositivo. Se
actualiza sola cada minuto: lo agregado desde Telegram o desde otra pantalla aparece sin
recargar; lo nuevo de Google puede tardar hasta cinco minutos más.

**Crear, editar y borrar desde la agenda.** Tocando un día, o con el botón «+ Nuevo aviso» de
abajo a la derecha (en el teléfono, solo el «+»), se abre un panel: tipo (alarma, recordatorio o timer), mensaje, fecha y
hora, repetición, para quién, equipo y a nombre de quién. Valen las mismas reglas que en Telegram: un
timer suena una vez, un recordatorio repite, «Algunos días» pide los días —y ofrece la casilla
«No suena en feriados»— y «Todos los meses» repite el día del mes de la fecha elegida. Tocando un aviso de
la casa que todavía no sonó aparecen «Editar» y «Borrar»; si repite, se edita o se borra la
serie entera, y el autor no cambia; borrar pide confirmación. Lo de Google Calendar y lo que
ya sonó son solo para mirar.

Cada alta, cambio o baja se avisa en todos los chats. El de un alta o un cambio trae
«Cancelar #N», que cualquiera puede tocar para borrarlo, y a los demás les llega quién lo
borró.

«Para» elige de quién es el aviso: «Nadie» (como siempre), «Todos» o una persona de la casa.
Al sonar, uno de una persona con Telegram le llega solo a ella y el parlante la nombra. Para
quién es se ve en la agenda («· para China»), en el kiosco, en el control y en la alarma de
la tele.

El desplegable «A nombre de» lista las personas de la casa; la que no tiene Telegram dice
«(sin Telegram)», y un aviso a su nombre no aparece en el `/lista` de ningún chat. Si todavía
no se cargó a nadie, lista los chats de `ALLOWED_CHAT_IDS`: cada uno aparece como «Chat
<número>» hasta que le escribe algo al bot; desde ahí, con su nombre de Telegram.

Arriba, «Ver» muestra la agenda de toda la casa o la de una persona: lo suyo y lo de todos,
más Google y los feriados. Cada dispositivo recuerda lo elegido. Lo que viene por turnos entra
en la vista de esa persona recién cuando suena, salvo que el aviso sea suyo o de todos.
**Con `ALLOWED_CHAT_IDS` vacío la pantalla no escribe**: no aparece «Nuevo aviso» ni se
puede editar, borrar, agregar ni tachar.

**El kiosco** es un tablero de tarjetas y se actualiza solo cada minuto:

- **La hora y la fecha**: la de la casa, aunque el dispositivo tenga otra.
- **El clima**: un ícono del cielo, la temperatura, la sensación térmica, la máxima, la
  mínima y la chance de lluvia.
- **Lo próximo**: lo primero que viene con hora, de hoy o de mañana, con cuánto falta y de
  qué calendario es. Lo de todo el día no cuenta. Si no hay nada, «Nada más por hoy».
- **Hoy**: el día como línea de tiempo, con una marca «ahora» y cuántas cosas quedan. De lo
  que ya pasó quedan los dos últimos, con cómo terminó.
- **Idea para hoy**: el almuerzo y la cena del menú de la semana. Hasta las 15:00 resalta el
  almuerzo; de 15:00 a 22:00 atenúa el almuerzo y resalta la cena; desde las 22:00 pasa a
  «Idea para mañana». Una comida en `off` o sin plato no aparece, y sin menú la tarjeta no se
  muestra.
- **Compras y Pendientes**, con cuántos hay. Arriba de cada una hay un campo para agregar:
  «leche y pan, yerba» son tres ítems, como en el chat, y lo que ya estaba no se repite.
  Cada ítem trae un círculo para tacharlo desde ahí. Ni agregar ni tachar avisan en los
  chats.

Se ve claro u oscuro según el tema del dispositivo; en el horario de descanso, o con
`/silencio` o de vacaciones, se pone oscuro y apagado aunque el dispositivo esté en claro.
De vacaciones, abajo de la fecha dice «De vacaciones hasta el 25/10». Apaisado ocupa
tres columnas; vertical, dos; en un teléfono angosto, una sola que se desplaza.

Para dejarlo fijo en una tablet o un teléfono viejo:

1. Abrir `/pantalla` en el navegador y tocar la pantalla una vez: pasa a pantalla completa.
2. Que no se apague la pantalla y que quede enchufado al cargador se configura en el
   dispositivo, no acá.

**El control** hace desde el navegador lo mismo que Telegram. Se llega desde el enlace
«Control» de la agenda y del kiosco (el kiosco de solo lectura, `?ver=1`, no lo muestra).

1. Arriba, en «Soy», elegir quién sos: las personas de la casa o, si todavía no se cargó
   ninguna, los chats de Telegram. El dispositivo lo recuerda. Todo lo que hagas va a tu
   nombre, y a los demás chats les llega como «<tu nombre> (pantalla)», igual que si
   hubieras tocado el botón en Telegram. Alguien sin Telegram solo puede apagar una alarma o
   marcar «Hecho», y eso les llega a todos los chats.
2. **Ahora** muestra lo que pide atención, con sus botones: la alarma que suena («🔕 Apagar»),
   lo que espera su «Hecho», lo último que sonó en tu chat si todavía se puede posponer, las
   caídas sin confirmar («✅ Confirmar», solo si tu chat recibe las alertas) y un botón para
   silenciar la casa, hacerla hablar ya o cortar las vacaciones. Abajo, el estado de cada
   chequeo. Se actualiza cada cinco segundos.
3. El campo de texto acepta lo mismo que un mensaje sin barra en Telegram («poné una alarma a
   las 7»), y los paneles tienen los comandos con sus campos. Los equipos tildados en «Casa»
   van como `en <equipo>`. Si falta un dato, pregunta como en el chat, y la pregunta se puede
   contestar desde acá o desde Telegram. «Pastillas» y «Turnos» tienen un solo botón cada
   uno: con el campo vacío muestran lo que hay; con texto («7 enalapril 30»), lo cargan.
4. Un comando que tarda —una pregunta con búsqueda— muestra «⏳ Procesando…» hasta que
   contesta, aunque tarde un minuto.

**Las personas de la casa** se cargan en la tarjeta «👪 Personas», al pie del control: nombre
y, si tiene, su Telegram, elegido de los chats de `ALLOWED_CHAT_IDS` que no son de nadie, o
«Sin Telegram». Un chat que todavía no le escribió al bot aparece como «Todavía no escribió
(·1234)», con los últimos cuatro números. El nombre es el que dice la casa: letras y espacios, sin números ni guiones,
sin repetir y sin «todos» ni «nadie». Cada fila se renombra, cambia de Telegram o se borra.
Sumar o sacar a alguien no avisa a nadie.

En el teléfono, el menú del navegador ofrece **«Agregar a pantalla de inicio»** y queda como un
ícono «Casa» que abre directo en el control. No es una app instalada: la casa sirve http, y
eso, igual que usar el micrófono, pide HTTPS.

Sin `ALLOWED_CHAT_IDS` el control no maneja nada: no hay a nombre de quién.

**No pide login ni token**, ni para mirar ni para escribir: la usa cualquiera que llegue al
contenedor por la red. Lo que sí rechaza es una escritura que venga de otro sitio abierto en
el navegador. Sin `API_TOKEN` tampoco existe. Lo que sonó antes del 2026-10-05 no está
registrado.

## Instalar la app de la tele

La app de la tele está en `android/tele/`, en Kotlin. Se compila en Docker: no hace falta
Android Studio ni el SDK de Android.

### La clave de firma

Se crea una sola vez y vive fuera del repo, en `~/.config/domotica/android` (o en la carpeta
de `TELE_KEYS_DIR`). Si se pierde, la versión nueva no instala encima de la vieja y hay que
desinstalar la app en cada tele.

```bash
mkdir -p ~/.config/domotica/android && chmod 700 ~/.config/domotica/android
keytool -genkeypair -v -storetype PKCS12 -keystore ~/.config/domotica/android/tele-release.jks \
    -alias tele -keyalg RSA -keysize 4096 -validity 10000 -dname "CN=Domotica tele"
cat > ~/.config/domotica/android/keystore.properties <<'PROPS'
storePassword=<la contraseña que elegiste>
keyAlias=tele
keyPassword=<la misma contraseña: PKCS12 usa una sola>
PROPS
chmod 600 ~/.config/domotica/android/tele-release.jks ~/.config/domotica/android/keystore.properties
```

Sin la clave, `build.sh` no compila y muestra estos mismos comandos.

### Compilar y subir

```bash
android/tele/build.sh                 # APK firmado en android/tele/app/build/outputs/apk/release/
android/tele/build.sh <destino.apk>   # además lo copia ahí
android/tele/build.sh test            # los tests de la lógica de la app
```

La versión se sube a mano en `android/tele/version.properties`: `versionCode` tiene que
crecer para que la nueva instale encima. `TELE_HOUSE` cambia la URL de la casa a la que habla
la app.

El CT sirve el APK para bajarlo desde la misma tele, y su versión en `/app/tele.json`. Para
subir uno nuevo:

```bash
deploy/push-apk.sh <apk>              # usa 192.168.68.60 y el CT 300
deploy/push-apk.sh <apk> <pve> <ctid>
```

Antes de copiar nada saca la versión del APK con `deploy/tele-version.sh`, que necesita la
imagen Docker que deja `android/tele/build.sh`: sin ella, no sube. Deja el APK en
`/var/lib/domotica/app/tele.apk` y después su versión en `/var/lib/domotica/app/tele.json`,
sin reiniciar el servicio, y muestra el sha256 y la versión publicada. `deploy/deploy.sh` no
los toca. Sin `API_TOKEN` la descarga no existe, igual que la pantalla.

`deploy/tele-version.sh <apk>` solo imprime el `tele.json` de un APK, sin subir nada.

### En la tele

Si la tele tiene la app de prueba «Spike tele», desinstalarla antes: es otro paquete y no se
reemplaza sola.

Con Downloader, o con un explorador de archivos con acceso a la red (en casa se usó CX File
Explorer):

1. Darle a esa app el permiso «instalar apps desconocidas».
2. Abrir `http://192.168.68.10:8099/app/tele.apk` e instalar.

La primera vez que se abre, con el control:

1. Elegir qué tele es, de las de `SCREEN_DEVICES`.
2. Elegir de quién es, de las personas de la casa; sin personas cargadas, de los chats.
3. Aceptar las notificaciones y después «mostrar sobre otras apps». En Google TV abre la lista
   general: bajar hasta la app y activarla. Sin ese permiso la alarma suena en la tele pero no
   se ve, y no sale el cartel de los recordatorios.
4. Darle a la app de Domótica «instalar apps desconocidas». Sin ese permiso no se puede
   actualizar sola.

Después muestra la pantalla de la casa y, al prender la tele, se conecta sola con el CT. La
elección queda guardada. Para cambiarla, bajar con el control hasta «Cambiar tele o persona»,
abajo a la derecha; BACK vuelve sin cambiar nada.

### Actualizar una tele

Se sube el `versionCode` en `version.properties`, se compila y se publica con
`deploy/push-apk.sh`. Cada tele mira la versión publicada a los treinta segundos de arrancar
la app y después cada hora; si hay una nueva, la baja, la verifica y abre la pantalla de
instalar: se confirma con el control. En el emulador el foco arrancó en «Cancelar», así que
puede hacer falta moverse hasta el botón de instalar.

No la ofrece con la tele apagada, mientras suena una alarma, con un recordatorio en pantalla o
mientras la tele está hablando; si
una versión falla al instalar —por ejemplo, firmada con otra clave— no la vuelve a ofrecer, y si
se cancela no vuelve a
preguntar por esa versión hasta seis horas después. Al terminar de instalar, la app vuelve a
conectarse sola con el CT. Se instala encima porque se firma con la misma clave: no hay que
desinstalar ni volver a elegir la tele.

Cuando suena una alarma, la tele muestra la hora grande y abajo «OK para apagar»: el OK del
control la apaga a nombre de la persona elegida. Sin persona elegida, el OK no la apaga.

Un recordatorio que espera «Hecho» sale como cartel encima de lo que se esté mirando, incluso
otra app, sin pausarla: el mensaje, para quién es y «OK para marcar hecho». El OK lo marca hecho
a nombre de la persona elegida; cualquier otra tecla lo cierra hasta el próximo re-aviso. Sin
persona elegida, el OK solo lo cierra. Con una alarma sonando no aparece, y en el horario de
descanso o de vacaciones tampoco. HOME no lo cierra: queda arriba del inicio hasta otra tecla.

## Desarrollo

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

Los tests no necesitan hardware ni red: el parlante y Piper están mockeados. Si hay `node`,
también corren la lógica de las páginas; sin `node`, ese test se saltea.

Capturas de la pantalla de la casa, para revisar cómo se ve:

```bash
CAPTURE_BROWSER=chromium deploy/capture-ui.sh http://192.168.68.10:8099 capturas 7
```

Los argumentos son la URL base, la carpeta de salida (por defecto `capturas`) y,
opcional, el número de una alarma para sacar también `/alarma?job=<n>`. Saca `/control`,
`/agenda`, `/pantalla` y `/pantalla?ver=1` en celular (412×915), tablet (1024×768), PC
(1440×900), tele 1080p y tele 720p; además, cada una en tema oscuro en celular y PC, y
control y agenda enteras en una ventana alta. Cada captura usa un perfil vacío, así no
arrastra lo guardado en el navegador. Solo hace GET: no escribe nada en la casa.

| Variable | Para qué | Por defecto |
| --- | --- | --- |
| `CAPTURE_BROWSER` | el Chrome o Chromium a usar | `chromium` |
| `CAPTURE_FLAGS` | banderas de más, como `--no-sandbox` donde no hay sandbox de usuario | ninguna |
| `CAPTURE_WAIT_MS` | cuánto tiempo virtual espera a que la página cargue | `6000` |
| `CAPTURE_TIMEOUT_S` | tope de cada captura, en segundos | `60` |

## Configuración

El servicio lee un archivo de entorno (en el contenedor, `/etc/domotica/domotica.env`, chmod 600):

```ini
TELEGRAM_TOKEN=          # token de @BotFather
ALLOWED_CHAT_IDS=        # vacío = el primero que escriba queda registrado
ALERT_CHAT_IDS=          # quién recibe monitor y Seq; vacío = todos los de arriba
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
CLOSING_AT=22:00         # cierre del día: lo de mañana; "off" lo apaga
WEEKLY_AT=dom 19:00      # resumen semanal, solo escrito; días como una alarma; "off" lo apaga
EVENT_LEAD_MINUTES=10    # cuántos minutos antes avisar
CHECKS_FILE=/etc/domotica/checks.json
CHECK_INTERVAL_SECONDS=120
SEQ_URL_HOSTING=http://172.68.0.7   # logs de un VPS, por el túnel
SEQ_API_KEY_HOSTING=                # clave de solo lectura; falta la clave, no arranca
SEQ_URL_NUBE=http://172.68.2.7      # una clave por VPS; el sufijo es el alias
SEQ_API_KEY_NUBE=
SEQ_COOLDOWN_MINUTES=15             # el enfriamiento es de cada instancia
PVE_URL=https://192.168.68.60:8006  # API del Proxmox; sin URL, no se vigila
PVE_TOKEN=                          # usuario@realm!id=secreto, de solo lectura
PVE_CA_FILE=/etc/domotica/pve-ca.pem   # obligatoria con PVE_URL; tiene que existir
PVE_DISK_ALERT=85                   # % de disco que avisa, de 1 a 99
LLM_PROVIDER=google            # quién escribe el texto: google o anthropic
LLM_API_KEY=                   # API de Google AI Studio; sin clave, apagado. Las notas de voz la usan siempre
LLM_MODEL=gemini-3.1-flash-lite
ASK_PROVIDER=                  # quién contesta /preguntar: google o anthropic; vacío hereda LLM_PROVIDER
ASK_MODEL=gemini-3.7-flash     # el que contesta /preguntar; NO hereda de LLM_MODEL
ANTHROPIC_API_KEY=             # obligatoria si LLM_PROVIDER o ASK_PROVIDER es anthropic
ANTHROPIC_MODEL=claude-haiku-5-5
ANTHROPIC_ASK_MODEL=claude-sonnet-5-5   # el que contesta /preguntar; NO hereda de ANTHROPIC_MODEL
ECONOMY=on                     # dólar, riesgo país e inflación en el resumen
VERSE=on                       # versículo del día (NTV) al final del resumen
NEWS_RSS_INFOBAE=https://www.infobae.com/arc/outboundfeeds/rss/?outputType=xml
NEWS_RSS_AMBITO=https://www.ambito.com/rss/pages/home.xml   # una clave por medio
NEWS_COUNT=5                   # cuántos titulares, hasta diez
SCREEN_DEVICE=comedor          # dónde muestra /pantalla sin equipo
SCREEN_DEVICES=comedor,recamara,habitacion   # qué equipos tienen pantalla, por coma
MENU_LUNCH_AT=11:00            # aviso del almuerzo y el almuerzo en /menu; "off" lo saca
MENU_DINNER_AT=17:30           # aviso de la cena y la cena en /menu; "off" la saca
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

Con más de una persona en la lista, las alarmas, los recordatorios, los timers, la agenda y el clima les llegan a
todas. Los avisos del monitor y de Seq, a `ALERT_CHAT_IDS`, que tiene que ser parte de
`ALLOWED_CHAT_IDS`. Esos chats también son los únicos que leen los servicios caídos y los
errores de la noche en el resumen y el cierre; el parlante los dice igual.

**Cómo habla.** Piper no deja pausa entre oraciones si no se le pide, y eso hace que un
aviso de dos frases suene apurado. Se ajusta por entorno, sin tocar código:

| variable | default | qué hace |
| --- | --- | --- |
| `DOMOTICA_LENGTH_SCALE` | 1.40 | más alto, más despacio |
| `DOMOTICA_SENTENCE_SILENCE` | 1.10 | segundos de pausa entre oraciones |
| `DOMOTICA_NOISE_SCALE` | — | más bajo, más contenido |
| `DOMOTICA_NOISE_W` | — | más alto, menos plano |

Las dos últimas sin valor las decide el modelo de voz. Cambiar cualquiera **rehace el cache**
a propósito: el audio ya guardado se generó con el ritmo viejo.

Rutas, sobreescribibles por entorno: `DOMOTICA_CONFIG`, `DOMOTICA_PYTHON`, `DOMOTICA_VOICE`,
`DOMOTICA_CACHE`, `DOMOTICA_MEDIA_PORT`. La base de timers vive en `STATE_DIRECTORY`, que
systemd crea como `/var/lib/domotica`.

## Despliegue

```bash
deploy/deploy.sh              # usa 192.168.68.60 y el CT 300
deploy/deploy.sh <pve> <ctid>
```

Empaqueta, copia al contenedor, instala el unit y **reinicia** el servicio. Ver `CLAUDE.md`
y `.claude/rules/` para direcciones y trampas conocidas.
