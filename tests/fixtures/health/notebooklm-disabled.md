# Provider Health: notebooklm

- Generated: <TS>
- Status: `disabled_in_config`
- Config key: `notebooklm_provider.enabled`
- Note: Провайдер выключен в конфиге проекта (notebooklm_provider.enabled: false) — health-проверка не запускалась: переменные окружения не читались, сеть и локальные приложения не опрашивались. Это ожидаемое состояние, не ошибка. Чтобы проверять провайдера, поставь notebooklm_provider.enabled: true или убери ключ.
