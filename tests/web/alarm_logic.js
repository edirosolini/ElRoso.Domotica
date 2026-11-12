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

// Mientras suena se queda hasta el tope; cuando deja de sonar vuelve al kiosco.
assert.strictEqual(alarm.MAX_VIEW_MS, 2100000);
assert.strictEqual(alarm.nextPage({ ringing: true, message: "arriba" }, 0), null);
assert.strictEqual(alarm.nextPage({ ringing: true, message: "arriba" }, 60000), null);
assert.strictEqual(alarm.nextPage({ ringing: true, message: "arriba" }, 2099999), null);
assert.strictEqual(alarm.nextPage({ ringing: true, message: "arriba" }, 2100000), "/pantalla?ver=1");
assert.strictEqual(alarm.nextPage({ ringing: false, message: null }, 0), "/pantalla?ver=1");
assert.strictEqual(alarm.nextPage(null, 0), "/pantalla?ver=1");

// Con el feed caído se queda hasta el tope y después vuelve al kiosco.
assert.strictEqual(alarm.offlinePage(0), null);
assert.strictEqual(alarm.offlinePage(2099999), null);
assert.strictEqual(alarm.offlinePage(2100000), "/pantalla?ver=1");

// La hora grande y la fecha.
var morning = new Date(2026, 9, 15, 7, 5);
assert.strictEqual(alarm.clockText(morning), "07:05");
assert.strictEqual(alarm.dateText(morning), "jueves 15 de octubre");

// La hora grande es la de cuando sonó; sin ella, la hora actual.
assert.strictEqual(alarm.alarmText({ ringing: true, at: "7:05" }, morning), "7:05");
assert.strictEqual(alarm.alarmText({ ringing: true, at: null }, morning), "07:05");
assert.strictEqual(alarm.alarmText({ ringing: true }, morning), "07:05");
assert.strictEqual(alarm.alarmText(null, morning), "07:05");

// Para quién es la alarma que suena.
assert.strictEqual(alarm.forText({ ringing: true, message: "arriba", for: "China" }), "Para China");
assert.strictEqual(alarm.forText({ ringing: true, message: "arriba", for: "todos" }), "Para todos");
assert.strictEqual(alarm.forText({ ringing: true, message: "arriba", for: null }), "");
assert.strictEqual(alarm.forText(null), "");

console.log("ok");
