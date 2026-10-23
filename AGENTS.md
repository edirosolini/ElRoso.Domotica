# AGENTS.md

Compartido por Codex y Claude Code. Cada línea de este archivo debe cambiar lo que hacés. Proyecto, stack y reglas de dominio: `CLAUDE.md`; por dominio: `.claude/rules/`.

## 1. Planificá antes de tocar el código
- Tarea larga: primero decime en 2-3 frases qué creés que estoy buscando. Empezá solo después de que diga que sí.
- Escribí los pasos en `PLAN.md`; cada uno dice cómo vas a demostrar que funciona.
- Dos intentos fallidos en un mismo paso: pará, anotá en `PLAN.md` qué falló y volvé a planificar.
- Si pausás la tarea a mitad: dejá `PLAN.md` al día para que otra sesión la retome.

## 2. Hacé el cambio mínimo que funcione
- Quedate dentro de esta tarea. No rompas nada que ya funcione.
- ¿Hay un compromiso? Sopesá UX (usuarios), DX (el siguiente desarrollador) y AX (el siguiente agente).
- No agregues dependencias, renombres ni refactors que nadie pidió.
- Hacé una copia antes de borrar o sobrescribir cualquier cosa.

## 3. Dividí el trabajo entre subagentes
- Roles de `.claude/agents/`: lee `planner` (y `Explore`); edita `executor` (`comments` y `docs` solo en lo suyo); revisa `tester`, que solo informa y nunca edita.
- Cada uno recibe una tarea, una condición de fin y devuelve un informe de 5 líneas.
- En paralelo está bien. Dos agentes sobre el mismo archivo, no.
- Comprobá la afirmación clave de un informe antes de construir sobre ella.

## 4. Hacete cargo del bug
- Reproducilo primero siguiendo mis pasos. ¿No podés? Decime qué necesitás.
- Corregí la causa y después volvé a correr los mismos pasos.
- Nunca silencies un error para que desaparezca.

## 5. Verificá antes de decir que está terminado
- Corré las pruebas y leé vos el resultado.
- UI: abrila e intentá romperla: entrada vacía, doble envío, recarga.
- ¿No corriste una comprobación? Decilo. Una comprobación no corrida no cuenta como pasada.
- Informá en 2-3 líneas: qué elegiste, a qué renunciaste y por qué.

## 6. Anotá cada corrección
- Cuando te corrija, agregá una línea en Lessons: "Cuando X, hacé Y". Va solo acá, no en la memoria de Claude Code.
- Mismo error dos veces: la lección no está clara. Reescribila.
- Preguntame antes de cambiar cualquier cosa por encima de Lessons.

## Lessons
<!-- Lo más reciente arriba. Eliminá lo que ya no aplique. -->
