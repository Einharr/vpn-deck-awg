# VPN Deck AWG

Decky-плагин для управления VPN прямо из Game Mode на Steam Deck. Это форк
`MrWaip/vpn-deck`, в котором переработаны runtime, хранение профилей и интерфейс.

## Поддерживаемые конфиги

В сборке закреплены **amneziawg-go v3.0.3** и
**amneziawg-tools v3.0.20260730**. Современный runtime используется для всех
поколений конфигов, а плагин автоматически определяет и показывает:

- WireGuard
- AmneziaWG 1.0
- AmneziaWG 1.5
- AmneziaWG 2.0
- AmneziaWG 3.0

Плагин не конвертирует конфиг и не удаляет неизвестные поля — файл сохраняется
как профиль и передаётся актуальному `awg-tools`.

## Что изменено

- Новый основной экран: состояние VPN, активный профиль и быстрые действия.
- Карточки профилей с версией протокола, endpoint, адресом и типом маршрутизации.
- Предпросмотр и проверка `.conf` до импорта.
- PrivateKey/PresharedKey не попадают в данные dashboard UI.
- Режим «один VPN одновременно» для безопасного переключения маршрутов.
- Нормальное persistent-хранилище Decky и миграция старых профилей.
- Восстановление системных ссылок после обновлений SteamOS.
- Просмотр handshake/traffic для активного peer.
- Диагностика Internet/DNS/HTTPS и лог `awg-quick`.
- Воспроизводимая сборка AWG runtime из закреплённых upstream-тегов.
- Upstream `awg-quick` автоматически адаптируется под `resolvectl` SteamOS и
  получает route-fix исходного vpn-deck.
- CI для Python и TypeScript/Decky frontend.

## Сборка

```bash
pnpm install
pnpm build
just test
just build-binaries
just build-plugin
```

`just build-binaries` собирает runtime через `infra/Dockerfile` и кладёт в
`bin/` `amneziawg-go`, `awg`, `awg-quick` и `versions.json`.

## Хранение профилей

Новые профили хранятся в persistent settings-каталоге Decky. При первом
запуске старые конфиги vpn-deck копируются туда, если они найдены. Системные
ссылки создаются в `/etc/amnezia/amneziawg/` и по умолчанию автоматически
восстанавливаются после обновлений SteamOS.

Плагин использует Decky `root` flag: он нужен для сетевых интерфейсов,
маршрутов и системных ссылок.
