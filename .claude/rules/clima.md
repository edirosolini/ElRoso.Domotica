---
paths:
  - "src/homeauto/weather.py"
  - "src/homeauto/air.py"
  - "src/homeauto/main.py"
  - "tests/test_weather.py"
  - "tests/test_weather_alerts.py"
  - "tests/test_rain.py"
  - "tests/test_air.py"
  - "tests/test_config_weather.py"
  - "tests/bot/test_weather_command.py"
---

# Clima

## Aviso de lluvia

`weather.RainWatcher` mira el pronóstico **por hora** y avisa que se viene el agua.

- **Una sola vez por día.** Es el diseño, no una limitación: un segundo aviso el mismo día
  es ruido, y el ruido es cómo un aviso deja de escucharse. La marca vive en `watch.Marks`.
- **Un aviso que falla no se marca**, igual que en la agenda: se reintenta en la vuelta
  siguiente.
- El pronóstico se pide con `forecast_days=2`: a las 22:00 las próximas seis horas caen casi
  todas en el día siguiente. Las listas `daily` siguen empezando por hoy, así que el índice
  cero no cambia de significado.
- ⚠️ **Open-Meteo contesta en hora local y sin offset** (`timezone=auto`). El reloj puede
  venir con zona; se compara naive porque el offset ya está aplicado del otro lado.
- Los umbrales son constantes del módulo, no config: `RAIN_WINDOW_HOURS` y
  `RAIN_ALERT_CHANCE`. Si algún día hay que tocarlos desde el contenedor, ahí sí van a
  `Config`.

## Los otros avisos del cielo

`weather.WeatherWatcher` avisa de calor, frío, ultravioleta, calidad del aire, viento y
tormenta. Misma forma que `RainWatcher` —una vez por día, y lo que no se pudo decir no se
marca— con una diferencia:

- 🔴 **Cada aviso lleva su propia marca.** Con una compartida, un día de calor se comería el
  aviso de las ráfagas que voltean las plantas, y nadie se enteraría de por qué. Es el mismo
  motivo por el que cada Seq tiene las suyas.
- 🔴 **La lluvia sigue en su watcher aparte.** Su marca ya está en la base desplegada y su
  umbral tiene historia; absorberla sería reescribir estado que ya existe para no ganar nada.
  El precio es una consulta más por vuelta a una API gratuita y sin clave.
- **El calor, el frío, el ultravioleta y el aire esperan a que alguien esté despierto**
  (`DAY_ALERT_FROM` / `DAY_ALERT_TO`, de 7 a 11). Son sobre el día entero: a las cuatro de
  la mañana la máxima no le sirve a nadie, y en horario de descanso terminaría en el chat,
  que es donde un aviso se vuelve ruido. El viento y la tormenta son sobre las próximas horas y salen cuando se ven.
- **Un solo pedido contesta las dos reglas de las próximas horas.** `hours_ahead()` devuelve
  la ventana con lluvia, ráfaga y código de cielo juntos, y de ahí salen el viento y la
  tormenta; pedir el pronóstico una vez por regla sería pegarle de más a un servicio que nos
  deja entrar gratis. La lluvia va por `RainWatcher`, con su propio pedido.
- **El ultravioleta viaja en el pedido diario del calor y el frío**: `day_ahead()` devuelve
  `DayAhead(maximum, minimum, uv)`. Con las tres marcas de hoy puestas no se pide nada. Sin
  `uv_index_max` legible, `uv` es `None` y el calor y el frío siguen andando.
- 🔴 **El aire es otro servicio y otro pedido** (`air.py`, `air-quality-api.open-meteo.com`):
  `AirClient.worst_today()` toma el peor `us_aqi` entre las 8 y las 20. Se saltea con su marca
  de hoy puesta, y si falla no cuesta el ultravioleta ni nada más.
- ⚠️ **El aire es CAMS global, de unos cuarenta kilómetros**: mejor que nada, no un sensor.
  Por eso el aviso no dice cifra, solo que se espera mala calidad.
- Ninguno de los dos entra en el resumen de la mañana, y los umbrales (`UV_ALERT`,
  `AIR_ALERT`) son constantes del módulo, como los de la lluvia.
