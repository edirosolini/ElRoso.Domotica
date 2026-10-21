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

// Mientras suena se queda un minuto; después, o cuando deja de sonar, vuelve al kiosco.
assert.strictEqual(alarm.nextPage({ ringing: true, message: "arriba" }, 0), null);
assert.strictEqual(alarm.nextPage({ ringing: true, message: "arriba" }, 59999), null);
assert.strictEqual(alarm.nextPage({ ringing: true, message: "arriba" }, 60000), "/pantalla?ver=1");
assert.strictEqual(alarm.nextPage({ ringing: false, message: null }, 0), "/pantalla?ver=1");
assert.strictEqual(alarm.nextPage(null, 0), "/pantalla?ver=1");

// La hora grande y la fecha.
var morning = new Date(2026, 9, 15, 7, 5);
assert.strictEqual(alarm.clockText(morning), "07:05");
assert.strictEqual(alarm.dateText(morning), "jueves 15 de octubre");

// Para quién es la alarma que suena.
assert.strictEqual(alarm.forText({ ringing: true, message: "arriba", for: "China" }), "Para China");
assert.strictEqual(alarm.forText({ ringing: true, message: "arriba", for: "todos" }), "Para todos");
assert.strictEqual(alarm.forText({ ringing: true, message: "arriba", for: null }), "");
assert.strictEqual(alarm.forText(null), "");

console.log("ok");
