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

console.log("ok");
