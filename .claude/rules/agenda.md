---
paths:
  - "src/homeauto/agenda/**"
  - "src/homeauto/main.py"
  - "tests/agenda/**"
  - "tests/bot/test_agenda_command.py"
---

# Agenda

## Agenda

`homeauto/agenda/` lee Google Calendar por la **dirección privada en formato iCal**, elegida
sobre la API de Calendar porque esto es solo lectura: sin proyecto en Google Cloud, sin OAuth
y sin refresh tokens. El precio es que **Google cachea esa URL** y un evento nuevo tarda en
aparecer; si algún día hace falta que sea inmediato, ahí sí hay que migrar a OAuth.

- 🔴 **La URL privada es una credencial.** Trato igual que el token de Telegram: archivo con
  permisos 600, jamás en el repo.
- **Una clave de config por calendario** (`CALENDAR_URL_<ALIAS>`). Una lista separada por
  comas sería ambigua: las URLs llevan `:` y `/` propios.
- **Las recurrencias no se parsean a mano.** `recurring-ical-events` expande RRULE y respeta
  EXDATE; hay test con un semanal que tiene una ocurrencia excluida.
- **`Event.key` identifica la ocurrencia, no el evento.** Un semanal dispara muchas veces y
  cada una se avisa una sola vez.
- **Un aviso que falla no se marca como hecho**, para que se reintente en la vuelta siguiente.
- **Nunca se anuncian eventos que ya empezaron.** Tras un reinicio eso sería ruido.
- Un calendario roto no tapa a los otros: se registra en `last_problems` y sigue.
- 🔴 **`speech.describe()` arma una sola oración**, sea uno o varios eventos: «Mañana a las
  nueve de la mañana tenés Reunión», «Hoy todo el día tenés Feria», «Hoy tenés tres cosas:
  todo el día, Feria; a las nueve de la mañana, X; y a las once de la mañana, Y». El lugar va
  después del título («tenés Dentista, en Sanatorio X»). El formato anterior, un encabezado
  «tenés una cosa.» y una oración por evento, sonaba robótico cada vez que el pulidor no lo
  reescribía. Lo de día completo va primero; el día vacío sigue diciendo «No tenés nada
  agendado».
