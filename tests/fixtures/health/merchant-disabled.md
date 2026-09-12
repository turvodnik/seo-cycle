# Provider Health: merchant

- Generated: <TS>
- Status: `disabled_in_config`
- Config key: `sources.google_merchant.enabled`
- Note: Провайдер выключен в конфиге проекта (sources.google_merchant.enabled: false) — health-проверка не запускалась: переменные окружения не читались, сеть и локальные приложения не опрашивались. Это ожидаемое состояние, не ошибка. Чтобы проверять провайдера, поставь sources.google_merchant.enabled: true или убери ключ.
