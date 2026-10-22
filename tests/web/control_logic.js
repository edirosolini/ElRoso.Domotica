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

// Quién soy: con padrón vacío, se eligen chats.
var people = [{ chat_id: 42, name: "Eze" }, { chat_id: 77, name: "Chat 77" }];
var chats = control.whoOptions({ people: people, persons: [] });
assert.deepStrictEqual(chats, [{ key: "c:42", label: "Eze", name: "Eze" },
  { key: "c:77", label: "Chat 77", name: "Chat 77" }]);
assert.deepStrictEqual(control.whoOptions({ people: people }), chats);
assert.deepStrictEqual(control.whoOptions({}), []);

// Con padrón, se elige persona; la que no tiene Telegram lo dice.
var persons = [{ id: 3, name: "Abuela", chat_id: null }, { id: 5, name: "Eze", chat_id: 42 }];
var options = control.whoOptions({ people: people, persons: persons });
assert.deepStrictEqual(options, [
  { key: "p:3", label: "Abuela (sin Telegram)", name: "Abuela", chat_id: null },
  { key: "p:5", label: "Eze", name: "Eze", chat_id: 42 },
]);

// El guardado si sigue, uno viejo por número de chat; sin guardado válido, nadie.
assert.strictEqual(control.pickWho(chats, "c:77"), "c:77");
assert.strictEqual(control.pickWho(chats, "77"), "c:77");
assert.strictEqual(control.pickWho(chats, "c:99"), null);
assert.strictEqual(control.pickWho(chats, null), null);
assert.strictEqual(control.pickWho(options, "p:5"), "p:5");
assert.strictEqual(control.pickWho(options, "42"), "p:5");
assert.strictEqual(control.pickWho(options, "c:42"), "p:5");
assert.strictEqual(control.pickWho(options, "p:9"), null);
assert.strictEqual(control.pickWho(options, null), null);
assert.strictEqual(control.pickWho([], "42"), null);

// Un botón viaja como data, lo escrito suelto como text, a nombre del chat o de la persona.
assert.deepStrictEqual(control.commandBody("c:42", "callar 17", false), { chat_id: 42, data: "callar 17" });
assert.deepStrictEqual(control.commandBody("c:42", "dame el clima", true), { chat_id: 42, text: "dame el clima" });
assert.deepStrictEqual(control.commandBody("p:3", "callar 17", false), { person_id: 3, data: "callar 17" });
assert.strictEqual(control.liveUrl("c:-100"), "/api/live?chat=-100");
assert.strictEqual(control.liveUrl("p:3"), "/api/live?person=3");

// Un chat se muestra con el nombre visto en Telegram, o como que todavía no escribió.
assert.strictEqual(control.chatLabel({ chat_id: 42, seen: "Ezequiel Di" }), "Ezequiel Di (42)");
assert.strictEqual(control.chatLabel({ chat_id: 5550001234, seen: null }), "Todavía no escribió (·1234)");
assert.strictEqual(control.chatLabel({ chat_id: 77, seen: null }), "Todavía no escribió (·77)");
assert.strictEqual(control.chatLabel({ chat_id: -1001234567, seen: "" }), "Todavía no escribió (·4567)");

// Un formulario sin dato obligatorio consulta vacío y ejecuta con texto; uno obligatorio vacío no manda nada.
assert.strictEqual(control.formCommand("pastillas", false, [], ""), "pastillas");
assert.strictEqual(control.formCommand("pastillas", false, [], " 7 enalapril 30 "), "pastillas 7 enalapril 30");
assert.strictEqual(control.formCommand("turnos", false, [], "7 Cin, Die"), "turnos 7 Cin, Die");
assert.strictEqual(control.formCommand("decir", true, ["comedor"], "  "), null);
assert.strictEqual(control.formCommand("decir", true, ["comedor"], "hola"), "decir en comedor hola");

// Los chats que se pueden asociar: los libres y el propio.
var house = [{ chat_id: 42, seen: "Eze" }, { chat_id: 77, seen: null }];
assert.deepStrictEqual(control.freeChats(house, persons, 3), [{ chat_id: 77, seen: null }]);
assert.deepStrictEqual(control.freeChats(house, persons, 5), house);
assert.deepStrictEqual(control.freeChats(house, persons, null), [{ chat_id: 77, seen: null }]);

// El cuerpo del alta o del cambio de una persona.
assert.deepStrictEqual(control.personBody("  Abuela ", ""), { name: "Abuela", chat_id: null });
assert.deepStrictEqual(control.personBody("Eze", "42"), { name: "Eze", chat_id: 42 });
assert.deepStrictEqual(control.personBody("Eze", "-100"), { name: "Eze", chat_id: -100 });

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

// Lo que suena y lo que espera dicen para quién es.
var assigned = control.urgentItems({
  now: now,
  ringing: [{ job_id: 17, message: "arriba", since: "2026-10-19T11:58:00", for: "China", actions: [] }],
  awaiting: [{ job_id: 9, message: "pastilla", since: "2026-10-19T11:50:00", for: "todos", actions: [] }],
});
assert.strictEqual(assigned[0].meta, "Sonando hace 2 min · para China");
assert.strictEqual(assigned[1].meta, "Espera su «Hecho» · sonó hace 10 min · para todos");

var postponed = control.urgentItems({
  now: now, snooze: { message: "arriba", since: "2026-10-19T11:58:00", for: "China", actions: [] },
});
assert.strictEqual(postponed[0].meta, "Sonó hace 2 min · se puede posponer · para China");

// «Ahora» va compacta si no hay nada más que el silencio.
assert.strictEqual(control.isCalm([]), true);
assert.strictEqual(control.isCalm([{ kind: "quiet" }]), true);
assert.strictEqual(control.isCalm(items), false);
assert.strictEqual(control.isCalm([{ kind: "awaiting" }, { kind: "quiet" }]), false);

// El estado de lo que se vigila en una línea.
assert.strictEqual(control.statusText([{ name: "vps", up: false }, { name: "web", up: true }]),
  "🔴 vps · ✅ web");
assert.strictEqual(control.statusText([]), "");

// «?soy=<persona>» elige a esa persona si está en el padrón.
assert.strictEqual(control.whoFromQuery("?soy=5", options), "p:5");
assert.strictEqual(control.whoFromQuery("?x=1&soy=3", options), "p:3");
assert.strictEqual(control.whoFromQuery("?soy=9", options), null);
assert.strictEqual(control.whoFromQuery("?soy=5x", options), null);
assert.strictEqual(control.whoFromQuery("", options), null);
assert.strictEqual(control.whoFromQuery("?soy=42", chats), null);

// «Ahora» en calma dice que todo está en orden.
assert.strictEqual(control.calmTitle([]), "Todo en orden");
assert.strictEqual(control.calmTitle([{ kind: "quiet" }]), "Todo en orden");
assert.strictEqual(control.calmTitle(items), "Ahora");

// Lo urgente trae de quién es, y lo de quien eligió va primero dentro de cada tipo.
assert.strictEqual(assigned[0].owner, "China");
assert.strictEqual(items[0].owner, null);
var mixed = [
  { kind: "ringing", title: "a", owner: null }, { kind: "ringing", title: "b", owner: "Papá" },
  { kind: "awaiting", title: "c", owner: "China" }, { kind: "awaiting", title: "d", owner: "Papá" },
  { kind: "outage", title: "e", owner: null }, { kind: "quiet", title: "f", owner: null },
];
assert.deepStrictEqual(control.mineFirst(mixed, "Papá").map(function (item) { return item.title; }),
  ["b", "a", "d", "c", "e", "f"]);
assert.deepStrictEqual(control.mineFirst(mixed, null).map(function (item) { return item.title; }),
  ["a", "b", "c", "d", "e", "f"]);

// El timer rápido: minutos y qué; sin minutos válidos no manda nada.
assert.strictEqual(control.timerCommand("10", " sacar la pizza "), "timer 10m sacar la pizza");
assert.strictEqual(control.timerCommand("5", ""), "timer 5m");
assert.strictEqual(control.timerCommand("", "pizza"), null);
assert.strictEqual(control.timerCommand("0", "pizza"), null);
assert.strictEqual(control.timerCommand("2.5", "pizza"), null);

console.log("ok");
