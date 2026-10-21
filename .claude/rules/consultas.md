---
paths:
  - "src/homeauto/ask.py"
  - "src/homeauto/calc.py"
  - "src/homeauto/lists.py"
  - "src/homeauto/meals.py"
  - "src/homeauto/translate.py"
  - "src/homeauto/main.py"
  - "tests/test_ask.py"
  - "tests/test_calc.py"
  - "tests/test_lists.py"
  - "tests/test_meals.py"
  - "tests/test_translate.py"
  - "tests/bot/test_ask_command.py"
  - "tests/bot/test_calc_command.py"
  - "tests/bot/test_list_commands.py"
  - "tests/bot/test_menu_command.py"
  - "tests/bot/test_translate_command.py"
---

# Preguntas, cuentas, listas, menú y traducir

## Cuentas y unidades

`calc.py` resuelve una cuenta o una conversión **sin llamar a ningún modelo**, y por eso es
lo único que la casa contesta con un número exacto.

- 🔴 **Nació de un agujero que ya existía.** Una cuenta por `/preguntar` vuelve con dígitos,
  así que `ask._safe_to_say()` la mandaba al chat y el parlante decía "te lo dejé escrito".
  Acá el resultado pasa por `verbalize` y **se puede decir**.
- 🔴 **Lo escrito y lo hablado son distintos**, la misma separación de `ask.Answer` y
  `seq.Summary`: `written` es `15 × 4 = 60` y `spoken` es "Son sesenta".
- 🔴 **`verbalize.MAXIMUM` es el techo real.** Pasado el millón, `spoken` vuelve vacío y el
  comando contesta que ese número no lo puede decir, con la cifra escrita al lado. La
  respuesta no se pierde, cambia de forma — igual que en `ask`.
- 🔴 **El evaluador tiene tope de potencia a propósito.** `9 ** 9 ** 9` cuelga el proceso
  antes de contestar; `MAX_POWER_BASE` y `MAX_EXPONENT` lo frenan. Es `ast` con una lista
  blanca de operadores: no hay `eval`, no hay nombres, no hay llamadas.
- **Las unidades son una tabla propia, no `pint`.** El CT tiene 512 MB y ya se descartó
  Kokoro por RAM; lo que pregunta una casa entra en veinte filas. Si algún día hace falta
  más, ahí sí entra una dependencia.
- ⚠️ **La temperatura no escala, se desplaza**, así que va aparte de la tabla de factores.
  "veinte grados" sin apellido es Celsius: es lo que se mide acá.
- ⚠️ **La coma decimal es de ida y de vuelta.** Entra como la escribe una persona (`1,5`),
  se convierte a punto para Python y vuelve a coma para el chat.

## Las listas

`lists.py` guarda dos listas —**compras** y **pendientes**— en la octava tabla de `jobs.db`,
con el mismo patrón que las otras siete.

- 🔴 **Dos listas fijas y no un nombre libre.** "agregá a X Y" no se puede partir sin
  adivinar dónde termina el nombre. Una tercera es una línea en `_NAMES`.
- **El nombre se busca del más largo al más corto.** "a la lista de compras leche" nombra una
  lista; "a comprar pan" no, y entra entero como ítem. Es la misma lección que `en <equipo>`:
  un prefijo que también puede ser texto real se come parte del mensaje.
- **Se separa por comas y por "y".** Dictado, "leche y pan" son dos cosas; obligar a la coma
  hacía que una nota de voz guardara un solo ítem con todo adentro. La regla es una sola,
  `lists.split_items()`, y la usan el chat y la pantalla.
- **Un duplicado se avisa, no se repite**, comparando sin mayúsculas.
- **Cada ítem guarda cuándo se agregó** (`added_at`), para que `/depurar listas` proponga
  los de más de treinta días. La columna se suma sola al abrir una base vieja
  (`_add_missing_columns()`), y las filas de antes quedan sin fecha: el depurador las cuenta
  pero no las toca.
- 🔴 **La lista se lee, no se escucha.** `/compras` y `/pendientes` contestan al chat como
  `/lista`: números y cantidades son de leer. Lo único hablado es el conteo del cierre del
  día, y ese va en palabras.
- **`/compras` nombra a `/sacar`**, como `/lista` nombra a `/cancelar`: es la única entrada
  del menú que deja a otro comando sin puerta.

## Menú semanal

`/menu` muestra la semana de lunes a domingo con almuerzo y cena. `meals.MealPlanner` la pide
al modelo barato de `LLM_PROVIDER` (`main.build_model()`, sin búsqueda, `MENU_TIMEOUT` de
treinta segundos), la valida y `MealStore` la guarda en `meal_plans`. Sin la clave del
proveedor de texto, `/menu` contesta que no hay modelo.

- **Se arma la primera vez que se pide.** Si la semana no está guardada, `/menu` la arma;
  `/menu nuevo [pedido]` la rearma entera con lo que se pida («sin carne») y el pedido queda
  guardado y se muestra arriba. **El domingo ya muestra la semana que viene.**
- **No repite la semana anterior**: sus platos van al prompt como lo que no se repite.
  `/menu otra <AAAA-MM-DD> <comida>` cambia un solo plato y evita también los de esa semana.
- 🔴 **Un menú inválido no guarda nada.** Siete días exactos, cada comida con un nombre de
  hasta ochenta caracteres y entre uno y cuarenta ingredientes; un ingrediente con un dígito
  trae cantidades y tira todo con `MealError`. `save_week()` corre recién con la semana entera
  validada, así que un error deja la semana anterior como estaba.
- 🔴 **La alacena se saca en código, no se confía en el prompt.** El prompt pide ingredientes
  sin sal, aceite, pimienta, agua ni condimentos, y `_is_pantry()` igual los saca —por la
  primera palabra, o si dicen «condimento»— antes de guardar. Si no, `/menu compras` llenaría la
  lista de cosas que hay en cualquier casa. Los repetidos se sacan sin mirar acentos.
  ⚠️ Un condimento con nombre propio pasa: en una corrida real, «orégano» llegó a los
  ingredientes.
- **`/menu compras` pasa lo que queda de hoy** (`left_today()`): el almuerzo hasta las quince
  —el mismo corte de `correct.MEALS`— y la cena hasta las veintidós. `/menu compras semana`
  pasa toda la semana y `/menu compras <AAAA-MM-DD> <comida>`, un plato. Va por `ListStore.add()`,
  así que lo que ya estaba en compras se avisa y no se repite.
- **Los botones**: «🛒 Pasar a compras» (la semana) y «🔄 Otra idea» para la próxima comida
  (`upcoming()`), si cae en la semana que se muestra. Después de `otra`, los dos del plato nuevo.
  La fecha va en ISO porque la arma el botón.
- **Cambiar un plato avisa a los demás chats** de `ALLOWED_CHAT_IDS`: «🍽 <nombre> cambió la
  cena del miércoles 21/10: …». Ver **A quién le llega cada aviso**, en `.claude/rules/avisos.md`.
- 🔴 **El menú se lee, no se escucha**, como las listas: «por el parlante» contesta escrito y
  avisa que el menú no se dice.
- **`MENU_LUNCH_AT` y `MENU_DINNER_AT` deciden qué comidas tiene el menú y a qué hora se
  avisa cada una**: `off` saca esa comida y no agenda su aviso; con las dos en `off` el menú
  está apagado. El default de la cena es 17:30 porque en esta casa se cena a las 19:30.
- **El kiosco muestra los platos del día de la próxima comida** en «🍽 Idea para hoy» (o
  «para mañana»), con el mismo `upcoming()` y solo las comidas que no están en `off`. Ver
  **El kiosco**, en `.claude/rules/web.md`.

### Aviso antes de cada comida

`main.schedule_meals()` agenda `menu-lunch` y `menu-dinner` con `_schedule_daily`, por
`to_thread` como los otros diarios. Sin planner no se agenda ninguno. `MealReminder.text_for()`
arma el texto y `HouseVoice.tell_everyone()` lo manda a todos, **solo escrito**:
«🍽 Idea para el almuerzo: Milanesas con puré.\nLleva: carne, pan rallado, huevo, papa.», con
«🛒 Pasar a compras» (`menu compras <fecha> <comida>`, solo ese plato) y «🔄 Otra idea»
(`menu otra <fecha> <comida>`).

- **Usa la semana de hoy** (`week_of()`), no la regla del domingo de `/menu`: el domingo a la
  noche avisa la cena de ese domingo.
- **Si la semana está vacía y la anterior tuvo menú, la arma y la guarda**, evitando los
  platos de la anterior y sin heredar su pedido. Si nunca hubo menú no arma nada: el primero
  lo pide alguien con `/menu`.
- **No manda nada** si la semana existe pero no tiene esa comida, si el modelo falla (queda
  un warning en el log) o en vacaciones (`away_of()`).
- ⚠️ **El descanso no lo frena y las vacaciones sí**, al revés que el resumen y el cierre,
  que en vacaciones salen por chat. Es solo escrito, así que el descanso no le cambia nada.
  En vacaciones no hay nadie en casa que vaya a cocinar, decisión del dueño del 2026-10-20.
  Las horas por defecto (11:00 y 17:30) quedan lejos del descanso del CT.
- **Ocho semanas de historia** (`KEEP_WEEKS`): `save_week()` poda lo anterior. `replace()`
  conserva el pedido de la semana del plato.
- **Fuera del menú de Telegram y en `HELP`**; entra también por el router. Ver **Comandos y
  alias**, en `.claude/rules/router-y-conversacion.md`.

## Traducir

`translate.py` traduce un texto con el modelo barato y **lo deja escrito**.

- 🔴 **Nunca se dice en voz alta.** Piper habla `es_AR` y lee cualquier otro idioma con
  fonética española. Pedirlo "por el parlante" contesta la traducción escrita y avisa por qué
  no suena. Hablarla obligaría a otra voz de Piper, y con ella a otra clave de cache.
- **La lista de idiomas es cerrada** (`LANGUAGES`), por lo mismo que los alias de equipo:
  "al final no fui" empieza igual que "al francés" y un prefijo ambiguo se come el mensaje.
- **Sin idioma, va de español a inglés y al revés**, que es el caso de esta casa.
- **Acá no hay original que gane**: si el modelo no contesta, no hay nada que decir, así que
  el error sale al chat en vez de un texto a medias.

## Preguntas

`ask.py` contesta una pregunta con un modelo con **búsqueda** y la casa la dice. Es lo único
que la casa dice que no generó ella ni escribió una persona: viene de afuera.

- 🔴 **Lo escrito y lo hablado son textos distintos**, la misma separación que hace
  `seq.Summary`. Una respuesta de búsqueda está hecha de años, cifras y resultados, y eso es
  exactamente lo que el sintetizador lee mal. `Answer.written` conserva todo y va al chat;
  `Answer.spoken` es una o dos oraciones con los números en palabras y es lo único que llega
  a Piper. Contra el endpoint real, en doce corridas la mitad hablada volvió **siempre sin un
  solo dígito**: el modelo respeta la consigna. La validación está igual, porque el día que no
  la respete nadie se va a enterar por el log.
- 🔴 **Si la voz no se puede confiar, no se habla, pero nunca se pierde la respuesta.** Con un
  dígito, vacía o demasiado larga, el parlante dice "te lo dejé escrito en el chat" y el chat
  tiene la respuesta entera. Se descarta, no se recorta: media oración es peor que un puntero.
- ⚠️ **La mitad hablada no es un resumen.** Pedirle "resumida" convirtió un chiste en estilo
  indirecto —"el papá le responde que no sabe"— y lo mató. Ahora el prompt dice que una
  respuesta corta se repite entera y tal cual, y que solo se condensa lo que de verdad es
  largo. Hay test que verifica que el prompt lo siga diciendo, porque es lo único que lo
  sostiene.
- **Un top diez dicho entero es un minuto de parlante.** Por eso hay tope de largo
  (`MAX_SPOKEN`) además del de dígitos. Está en cuatrocientos porque el top diez real volvió
  entre doscientos noventa y trescientos cincuenta y cinco caracteres: más ajustado tiraba al
  chat una respuesta que se podía decir.
- ⚠️ **La pregunta viaja literal**, como el texto de `/decir`. Reescribirla contestaría otra
  pregunta.
- 🔴 **La respuesta no pasa por el pulidor**, y es la única excepción a la regla de que todo
  lo generado se pule. Ya es prosa de un modelo: pulirla sumaría otros seis segundos a un
  camino que ya es lento y la validación la descartaría igual, porque cambia los números
  respecto del original por diseño.
- **El modelo es el mismo cliente que el del pulido, configurado al revés**:
  `main.build_model(ask=True)`, con búsqueda y `ASK_TIMEOUT` de **sesenta** segundos, contra los seis del pulido. Pulir no tiene nada que
  buscar y nadie espera una reescritura; una pregunta sí y alguien está mirando el chat.
  Medido contra la API real, un flash tardó **entre ocho y cuarenta segundos**: treinta
  hubiera cortado las más lentas.
- 🔴 **Buscar obliga a razonar.** `_must_think()` ignora el `thinking=False` cuando hay
  búsqueda: el criterio para decidir *qué* buscar es el razonamiento, y apagarlo deja el
  grounding adivinando. Es la misma razón por la que Gemma nunca recibe el switch.
- 🔴 **`ASK_MODEL` nunca hereda de `LLM_MODEL`, y el default es un flash entero.** Medido
  contra el endpoint real con la misma consigna y las mismas cuatro preguntas:
  `gemini-3.1-flash-lite` —el del pulido— **usó la búsqueda en una de cuatro** y contestó el
  resto de memoria, incluida la temperatura de ahora, que se inventó. `gemini-3.7-flash` y
  `gemini-flash-latest` buscaron en las cuatro. Un lite es la elección correcta para pulir,
  donde no hay nada que buscar, y la incorrecta acá: **una respuesta vieja dicha con
  seguridad es peor que ninguna.** Con Claude vale lo mismo para `ANTHROPIC_ASK_MODEL`, que
  no hereda de `ANTHROPIC_MODEL` porque Haiku no tiene búsqueda.
- **El proveedor de las preguntas es `ASK_PROVIDER`**, no `LLM_PROVIDER`; vacío, hereda ese.
  `ASK_MODEL` o `ANTHROPIC_ASK_MODEL` se eligen por `ASK_PROVIDER` (`text_ask_model`), y
  `build_asker()` devuelve None si ese proveedor no tiene clave (`ask_enabled`), aunque el
  texto ande. En esta casa es `anthropic`: Sonnet contestó bien y con fuentes en unos diez
  segundos. Ver **Proveedor del texto**, en `.claude/rules/voz.md`.
- 🔴 **El prompt tiene que mandar a buscar primero, y decirle que su información está vieja.**
  Con "buscá en internet si hace falta" al final, el mismo modelo grande buscaba mucho menos:
  el formato rígido de dos secciones le corría la atención a formatear. Con la orden adelante,
  cuatro de cuatro. No es adorno del texto: es la diferencia entre buscar y no.
- ⚠️ La pregunta entra por `/preguntar`, que acepta `en <equipo>` adelante como todos. Como
  un solo alias desconocido se trata como texto, "en qué año nació Messi" se contesta sin
  intentar hablarle a un equipo llamado "qué".
