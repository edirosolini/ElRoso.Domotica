---
paths:
  - "src/homeauto/ask.py"
  - "src/homeauto/calc.py"
  - "src/homeauto/lists.py"
  - "src/homeauto/translate.py"
  - "src/homeauto/main.py"
  - "tests/test_ask.py"
  - "tests/test_calc.py"
  - "tests/test_lists.py"
  - "tests/test_translate.py"
  - "tests/bot/test_ask_command.py"
  - "tests/bot/test_calc_command.py"
  - "tests/bot/test_list_commands.py"
  - "tests/bot/test_translate_command.py"
---

# Preguntas, cuentas, listas y traducir

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
- 🔴 **La lista se lee, no se escucha.** `/compras` y `/pendientes` contestan al chat como
  `/lista`: números y cantidades son de leer. Lo único hablado es el conteo del cierre del
  día, y ese va en palabras.
- **`/compras` nombra a `/sacar`**, como `/lista` nombra a `/cancelar`: es la única entrada
  del menú que deja a otro comando sin puerta.

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
- **`GoogleModel` es el mismo cliente que el del pulido, configurado al revés**: `search=True`
  y `ASK_TIMEOUT` de **sesenta** segundos, contra los seis del pulido. Pulir no tiene nada que
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
  seguridad es peor que ninguna.**
- 🔴 **El prompt tiene que mandar a buscar primero, y decirle que su información está vieja.**
  Con "buscá en internet si hace falta" al final, el mismo modelo grande buscaba mucho menos:
  el formato rígido de dos secciones le corría la atención a formatear. Con la orden adelante,
  cuatro de cuatro. No es adorno del texto: es la diferencia entre buscar y no.
- ⚠️ La pregunta entra por `/preguntar`, que acepta `en <equipo>` adelante como todos. Como
  un solo alias desconocido se trata como texto, "en qué año nació Messi" se contesta sin
  intentar hablarle a un equipo llamado "qué".
