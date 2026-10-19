// Prueba con node la lógica pura de control.js, sin navegador ni dependencias.
"use strict";

var assert = require("assert");
var path = require("path");
var control = require(path.join(__dirname, "../../src/homeauto/web/static/control.js"));

// Los equipos tildados van adelante, como «en a,b» en Telegram.
assert.strictEqual(control.targeted("decir", ["comedor", "recamara"], " hola "),
  "decir en comedor,recamara hola");
assert.strictEqual(control.targeted("decir", [], "hola"), "decir hola");
assert.strictEqual(control.targeted("parar", ["comedor"], ""), "parar en comedor");
assert.strictEqual(control.targeted("pantalla apagar", ["comedor"], ""), "pantalla apagar en comedor");
assert.strictEqual(control.targeted("clima", null, ""), "clima");

// Quién soy: el guardado si sigue en la casa, si no el primero.
var people = [{ chat_id: 42, name: "Eze" }, { chat_id: 77, name: "Chat 77" }];
assert.strictEqual(control.pickChat(people, "77"), 77);
assert.strictEqual(control.pickChat(people, "99"), 42);
assert.strictEqual(control.pickChat(people, null), 42);
assert.strictEqual(control.pickChat([], "42"), null);

// Un botón viaja como data, lo escrito suelto como text.
assert.deepStrictEqual(control.commandBody(42, "callar 17", false), { chat_id: 42, data: "callar 17" });
assert.deepStrictEqual(control.commandBody(42, "dame el clima", true), { chat_id: 42, text: "dame el clima" });
assert.strictEqual(control.liveUrl(-100), "/api/live?chat=-100");

// Cuánto pasó.
var now = "2026-10-19T12:00:00";
assert.strictEqual(control.sinceText("2026-10-19T11:59:40", now), "recién");
assert.strictEqual(control.sinceText("2026-10-19T11:55:00", now), "hace 5 min");
assert.strictEqual(control.sinceText("2026-10-19T09:30:00", now), "hace 2 h");

// El silencio: vacaciones, descanso o la casa hablando.
assert.strictEqual(control.quietTitle({ quiet: false }), "🔊 La casa habla");
assert.strictEqual(control.quietTitle({ quiet: true, reason: "Horario de descanso (22:00–05:25)" }),
  "🤫 Horario de descanso (22:00–05:25)");
assert.strictEqual(control.quietTitle({ quiet: true, away_until: "2026-10-25T00:00:00",
  reason: "De vacaciones hasta el 25/10" }), "🧳 De vacaciones hasta el 25/10");

// Lo urgente: sonando, esperando, posponer, caídas y el silencio, en ese orden.
var off = [{ label: "🔕 Apagar", data: "callar 17" }];
var items = control.urgentItems({
  now: now,
  ringing: [{ job_id: 17, message: "arriba", since: "2026-10-19T11:58:00", actions: off }],
  awaiting: [{ job_id: 9, message: "pastilla", since: "2026-10-19T11:50:00", actions: [] }],
  snooze: { message: "arriba", since: "2026-10-19T11:58:00", actions: [] },
  outages: [{ name: "vps", since: "2026-10-19T11:00:00", actions: [] }],
  quiet: { quiet: false, actions: [] },
});
assert.deepStrictEqual(items.map(function (item) { return item.kind; }),
  ["ringing", "awaiting", "snooze", "outage", "quiet"]);
assert.strictEqual(items[0].title, "⏰ arriba");
assert.strictEqual(items[0].meta, "Sonando hace 2 min");
assert.strictEqual(items[0].actions, off);
assert.strictEqual(items[3].title, "🚨 vps no responde");
assert.deepStrictEqual(control.urgentItems({ now: now }), []);

// El estado de lo que se vigila en una línea.
assert.strictEqual(control.statusText([{ name: "vps", up: false }, { name: "web", up: true }]),
  "🔴 vps · ✅ web");
assert.strictEqual(control.statusText([]), "");

console.log("ok");
