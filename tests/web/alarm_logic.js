// Prueba con node la lógica pura de alarm.js, sin navegador ni dependencias.
"use strict";

var assert = require("assert");
var path = require("path");
var alarm = require(path.join(__dirname, "../../src/homeauto/web/static/alarm.js"));

// El número de la alarma sale de la dirección.
assert.strictEqual(alarm.jobFrom("?job=17"), 17);
assert.strictEqual(alarm.jobFrom("?x=1&job=203"), 203);
assert.strictEqual(alarm.jobFrom("?job=abc"), null);
assert.strictEqual(alarm.jobFrom(""), null);

// Mientras suena se queda; cuando deja de sonar vuelve al kiosco de solo lectura.
assert.strictEqual(alarm.nextPage({ ringing: true, message: "arriba" }), null);
assert.strictEqual(alarm.nextPage({ ringing: false, message: null }), "/pantalla?ver=1");
assert.strictEqual(alarm.nextPage(null), "/pantalla?ver=1");

// La hora grande y la fecha.
var morning = new Date(2026, 9, 15, 7, 5);
assert.strictEqual(alarm.clockText(morning), "07:05");
assert.strictEqual(alarm.dateText(morning), "jueves 15 de octubre");

console.log("ok");
