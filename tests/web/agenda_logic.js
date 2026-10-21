// Prueba con node la lógica pura de app.js, sin navegador ni dependencias.
"use strict";

var assert = require("assert");
var path = require("path");
var agenda = require(path.join(__dirname, "../../src/homeauto/web/static/app.js"));

var NOW = new Date(2026, 9, 5, 12, 0);

function at(hour, minute) {
  return new Date(2026, 9, 5, hour, minute || 0);
}

// Un aviso de la casa que ya sonó hoy.
assert.strictEqual(
  agenda.isPastToday({ start: at(8), end: null, allDay: false, source: "casa", past: true }, NOW),
  true
);
// Uno de la casa que todavía no sonó.
assert.strictEqual(
  agenda.isPastToday({ start: at(20), end: null, allDay: false, source: "casa", past: false }, NOW),
  false
);
// Uno de la casa que pasó su hora mientras la página estaba abierta.
assert.strictEqual(
  agenda.isPastToday({ start: at(11, 59), end: null, allDay: false, source: "casa", past: false }, NOW),
  true
);
// Google: terminó, o empezó pero no terminó.
assert.strictEqual(
  agenda.isPastToday({ start: at(9), end: at(10), allDay: false, source: "google", past: false }, NOW),
  true
);
assert.strictEqual(
  agenda.isPastToday({ start: at(11), end: at(13), allDay: false, source: "google", past: false }, NOW),
  false
);
// Todo el día nunca se oculta.
assert.strictEqual(
  agenda.isPastToday({ start: at(0), end: null, allDay: true, source: "google", past: false }, NOW),
  false
);
// Lo de ayer queda como está.
assert.strictEqual(
  agenda.isPastToday(
    { start: new Date(2026, 9, 4, 8, 0), end: null, allDay: false, source: "casa", past: true }, NOW
  ),
  false
);

// La fecha para el campo datetime-local, en hora local.
assert.strictEqual(agenda.toLocalInput(new Date(2026, 0, 2, 7, 5)), "2026-01-02T07:05");

// Semana y día abren una hora antes de la actual; a medianoche, arriba de todo.
assert.strictEqual(agenda.nowScroll(at(14, 40)), "13:00:00");
assert.strictEqual(agenda.nowScroll(at(9, 0)), "08:00:00");
assert.strictEqual(agenda.nowScroll(at(0, 30)), "00:00:00");

// La repetición que permite cada tipo y si se ven los días de la semana.
assert.deepStrictEqual(agenda.repeatRule("alarm", "monthly"), {
  repeat: "monthly", locked: false, onceOff: false, showDays: false,
});
assert.deepStrictEqual(agenda.repeatRule("reminder", "monthly"), {
  repeat: "monthly", locked: false, onceOff: true, showDays: false,
});
assert.deepStrictEqual(agenda.repeatRule("alarm", "weekly"), {
  repeat: "weekly", locked: false, onceOff: false, showDays: true,
});
// Un timer suena una vez, aunque se haya elegido mensual.
assert.deepStrictEqual(agenda.repeatRule("timer", "monthly"), {
  repeat: "once", locked: true, onceOff: false, showDays: false,
});
// Un recordatorio no puede ser de una sola vez.
assert.strictEqual(agenda.repeatRule("reminder", "once").repeat, "daily");

// «No suena en feriados» solo vale con días de la semana.
assert.strictEqual(agenda.skipsHolidays(agenda.repeatRule("alarm", "weekly"), true), true);
assert.strictEqual(agenda.skipsHolidays(agenda.repeatRule("alarm", "weekly"), false), false);
assert.strictEqual(agenda.skipsHolidays(agenda.repeatRule("alarm", "daily"), true), false);
assert.strictEqual(agenda.skipsHolidays(agenda.repeatRule("timer", "weekly"), true), false);

// El filtro por persona: lo de esa persona y lo de todos; Google y feriados siempre.
var china = { source: "casa", assignee: "person", assignee_id: 3 };
var diego = { source: "casa", assignee: "person", assignee_id: 5 };
var everyone = { source: "casa", assignee: "all", assignee_id: null };
var nobody = { source: "casa", assignee: "none", assignee_id: null };
assert.strictEqual(agenda.visibleFor(china, 3), true);
assert.strictEqual(agenda.visibleFor(diego, 3), false);
assert.strictEqual(agenda.visibleFor(everyone, 3), true);
assert.strictEqual(agenda.visibleFor(nobody, 3), false);
assert.strictEqual(agenda.visibleFor({ source: "google" }, 3), true);
assert.strictEqual(agenda.visibleFor({ source: "feriado" }, 3), true);
// Sin filtro se ve todo.
assert.strictEqual(agenda.visibleFor(diego, null), true);
assert.strictEqual(agenda.visibleFor(nobody, null), true);

// El selector «Para»: nadie, todos y cada persona.
var persons = [{ id: 3, name: "China", chat_id: null }, { id: 5, name: "Diego", chat_id: 42 }];
assert.deepStrictEqual(agenda.assigneeOptions(persons), [
  { value: "none", label: "Nadie" },
  { value: "all", label: "Todos" },
  { value: "p:3", label: "China" },
  { value: "p:5", label: "Diego" },
]);
assert.deepStrictEqual(agenda.assigneeOptions([]), [
  { value: "none", label: "Nadie" },
  { value: "all", label: "Todos" },
]);
assert.deepStrictEqual(agenda.assigneeBody("none"), { assignee: "none" });
assert.deepStrictEqual(agenda.assigneeBody("all"), { assignee: "all" });
assert.deepStrictEqual(agenda.assigneeBody("p:3"), { assignee: "person", assignee_id: 3 });
assert.strictEqual(agenda.assigneeValue({ assignee: "person", assignee_id: 3 }), "p:3");
assert.strictEqual(agenda.assigneeValue({ assignee: "all", assignee_id: null }), "all");
assert.strictEqual(agenda.assigneeValue({ assignee: "none", assignee_id: null }), "none");
assert.strictEqual(agenda.assigneeValue(null), "none");

// A nombre de quién: las personas del padrón o, sin padrón, los chats.
assert.deepStrictEqual(agenda.authorOptions({ persons: persons, people: [{ chat_id: 42, name: "Eze" }] }), [
  { value: "p:3", label: "China (sin Telegram)" },
  { value: "p:5", label: "Diego" },
]);
assert.deepStrictEqual(agenda.authorOptions({ persons: [], people: [{ chat_id: 42, name: "Eze" }] }), [
  { value: "c:42", label: "Eze" },
]);
assert.deepStrictEqual(agenda.authorOptions({}), []);
assert.deepStrictEqual(agenda.authorBody("p:3"), { author_id: 3 });
assert.deepStrictEqual(agenda.authorBody("c:-100"), { author: -100 });

// El filtro recordado en el dispositivo, si esa persona sigue en el padrón.
assert.strictEqual(agenda.savedPerson("3", persons), 3);
assert.strictEqual(agenda.savedPerson("9", persons), null);
assert.strictEqual(agenda.savedPerson("", persons), null);
assert.strictEqual(agenda.savedPerson(null, persons), null);
assert.strictEqual(agenda.savedPerson("abc", persons), null);

// La vista con que abre: la guardada; sin guardar, mes en pantalla ancha y lista en el celular.
assert.strictEqual(agenda.startView(null, false, false), "listWeek");
assert.strictEqual(agenda.startView(null, true, false), "dayGridMonth");
assert.strictEqual(agenda.startView("timeGridWeek", false, false), "timeGridWeek");
assert.strictEqual(agenda.startView("dayGridMonth", false, false), "dayGridMonth");
assert.strictEqual(agenda.startView("cualquiera", false, false), "listWeek");
// Con un mes pedido en la dirección, abre en el mes.
assert.strictEqual(agenda.startView("listWeek", false, true), "dayGridMonth");

// Los calendarios que no se pudieron leer, para marcarlos en la leyenda.
var calendars = [{ name: "familia", color: "#1" }, { name: "familia_privado", color: "#2" }];
assert.deepStrictEqual(agenda.brokenCalendars(calendars,
  ["No pude leer el calendario familia_privado."]), ["familia_privado"]);
assert.deepStrictEqual(agenda.brokenCalendars(calendars, []), []);
assert.deepStrictEqual(agenda.brokenCalendars(calendars, ["No pude leer la agenda."]), []);

console.log("ok");
