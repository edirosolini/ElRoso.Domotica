// Prueba con node la lógica pura de kiosk.js, sin navegador ni dependencias.
"use strict";

var assert = require("assert");
var path = require("path");
var kiosk = require(path.join(__dirname, "../../src/homeauto/web/static/kiosk.js"));

var NOW = new Date(2026, 9, 5, 12, 47).getTime();

function at(hour, minute) {
  return new Date(2026, 9, 5, hour, minute || 0).getTime();
}

// Cuánto falta, en horas y minutos.
assert.strictEqual(kiosk.untilText(at(14), NOW), "en 1 h 13 min");
assert.strictEqual(kiosk.untilText(at(13), NOW), "en 13 min");
assert.strictEqual(kiosk.untilText(at(14, 47), NOW), "en 2 h");
// Con segundos de por medio, se redondea para arriba como el reloj.
assert.strictEqual(kiosk.untilText(at(14), NOW + 30000), "en 1 h 13 min");
assert.strictEqual(kiosk.untilText(at(12, 47), NOW), "ahora");

// La línea de abajo de «Lo próximo».
assert.strictEqual(
  kiosk.nextMeta({ start: new Date(at(14)).toISOString(), time: "14:00", tomorrow: false }, NOW),
  "en 1 h 13 min · 14:00"
);
assert.strictEqual(
  kiosk.nextMeta({ start: new Date(at(9)).toISOString(), time: "09:00", tomorrow: true }, NOW),
  "mañana · 09:00"
);

// La marca «ahora» va después de lo que ya pasó.
assert.strictEqual(kiosk.nowIndex([{ time: "07:00", past: true }, { time: "14:00", past: false }]), 1);
assert.strictEqual(kiosk.nowIndex([{ time: "07:00", past: true }, { time: "08:00", past: true }]), 2);
// Sin nada pasado, después de lo de todo el día.
assert.strictEqual(kiosk.nowIndex([{ time: null, past: false }, { time: "14:00", past: false }]), 1);
assert.strictEqual(kiosk.nowIndex([]), 0);

// De lo pasado quedan los dos últimos; lo que viene y lo de todo el día quedan enteros.
function hours(list) {
  return list.map(function (entry) { return entry.time; }).join(" ");
}
var day = [
  { time: null, past: false }, { time: "07:00", past: true }, { time: "08:00", past: true },
  { time: "09:00", past: true }, { time: "10:00", past: true }, { time: "14:00", past: false },
  { time: "21:00", past: false },
];
assert.strictEqual(hours(kiosk.trimPast(day, 2)), " 09:00 10:00 14:00 21:00");
assert.strictEqual(kiosk.nowIndex(kiosk.trimPast(day, 2)), 3);
assert.strictEqual(hours(kiosk.trimPast(day.slice(0, 3), 2)), " 07:00 08:00");
assert.strictEqual(hours(kiosk.trimPast([{ time: "14:00", past: false }], 2)), "14:00");

// El cielo con mayúscula y la sensación al lado.
assert.strictEqual(kiosk.skyLine({ sky: "nublado", feels_like: 19 }), "Nublado · sensación 19°");

// La leyenda de las vacaciones, con la hora solo si no es medianoche.
assert.strictEqual(kiosk.awayText("2026-10-25T00:00:00"), "De vacaciones hasta el 25/10");
assert.strictEqual(kiosk.awayText("2026-10-05T18:30:00"), "De vacaciones hasta el 05/10 a las 18:30");
assert.strictEqual(kiosk.awayText(null), "");
assert.strictEqual(kiosk.awayText("cualquier cosa"), "");

// En la tele, con ?ver=1, el kiosco no escribe.
assert.strictEqual(kiosk.readOnly("?ver=1"), true);
assert.strictEqual(kiosk.readOnly("?a=b&ver=1"), true);
assert.strictEqual(kiosk.readOnly(""), false);
assert.strictEqual(kiosk.readOnly("?ver=0"), false);
assert.strictEqual(kiosk.readOnly("?ver=10"), false);

// La tarjeta del menú: el título según el día y una fila por comida con su clase.
assert.deepStrictEqual(
  kiosk.mealView({ day: "2026-10-21", tomorrow: false, items: [
    { meal: "almuerzo", label: "Almuerzo", dish: "Milanesas con puré", state: "past" },
    { meal: "cena", label: "Cena", dish: "Tarta de acelga", state: "next" },
  ] }),
  { title: "🍽 Idea para hoy", rows: [
    { text: "Almuerzo · Milanesas con puré", className: "past" },
    { text: "Cena · Tarta de acelga", className: "on" },
  ] }
);
assert.deepStrictEqual(
  kiosk.mealView({ day: "2026-10-22", tomorrow: true, items: [
    { meal: "almuerzo", label: "Almuerzo", dish: "Ñoquis", state: "next" },
    { meal: "cena", label: "Cena", dish: "Pizza", state: "later" },
  ] }),
  { title: "🍽 Idea para mañana", rows: [
    { text: "Almuerzo · Ñoquis", className: "on" },
    { text: "Cena · Pizza", className: "" },
  ] }
);
assert.strictEqual(kiosk.mealView(null), null);
assert.strictEqual(kiosk.mealView({ day: "2026-10-21", tomorrow: false, items: [] }), null);

// Lo de hoy dice para quién es, si es de alguien.
assert.strictEqual(kiosk.todayLabel({ label: "📌 la pastilla", title: "x", for: "China" }),
  "📌 la pastilla · para China");
assert.strictEqual(kiosk.todayLabel({ label: "⏰ arriba", title: "x", for: null }), "⏰ arriba");
assert.strictEqual(kiosk.todayLabel({ title: "Dentista" }), "Dentista");

console.log("ok");
