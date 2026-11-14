// Prueba con node la lógica pura de dialog.js, sin navegador ni dependencias.
"use strict";

var assert = require("assert");
var path = require("path");
var dialog = require(path.join(__dirname, "../../src/homeauto/web/static/dialog.js"));

// Las etiquetas por defecto de cada diálogo; lo que se pasa pisa solo lo suyo.
assert.deepStrictEqual(dialog.labels("confirm"), { yes: "Sí, borrar", no: "No" });
assert.deepStrictEqual(dialog.labels("ask"), { yes: "Guardar", no: "No" });
assert.deepStrictEqual(dialog.labels("confirm", { yes: "Sí, cambiar" }), { yes: "Sí, cambiar", no: "No" });
assert.deepStrictEqual(dialog.labels("ask", { no: "Cancelar" }), { yes: "Guardar", no: "Cancelar" });
assert.deepStrictEqual(dialog.labels("confirm", null), { yes: "Sí, borrar", no: "No" });

// Escape es «No», también con el nombre viejo de la tecla; Tab se queda adentro.
assert.strictEqual(dialog.keyAction("Escape"), "no");
assert.strictEqual(dialog.keyAction("Esc"), "no");
assert.strictEqual(dialog.keyAction("Tab"), "tab");
assert.strictEqual(dialog.keyAction("Enter"), null);
assert.strictEqual(dialog.keyAction("a"), null);

// El foco da la vuelta adentro del diálogo, para adelante y para atrás.
assert.strictEqual(dialog.nextFocus(3, 0, false), 1);
assert.strictEqual(dialog.nextFocus(3, 2, false), 0);
assert.strictEqual(dialog.nextFocus(3, 0, true), 2);
assert.strictEqual(dialog.nextFocus(2, -1, false), 0);
assert.strictEqual(dialog.nextFocus(2, -1, true), 1);

// La respuesta se da una sola vez, aunque se toque dos veces.
var calls = [];
var answer = dialog.once(function (value) { calls.push(value); });
answer(true);
answer(true);
answer(false);
assert.deepStrictEqual(calls, [true]);

console.log("ok");
