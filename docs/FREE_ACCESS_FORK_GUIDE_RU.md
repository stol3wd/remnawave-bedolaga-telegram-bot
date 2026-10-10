# Бесплатный конфиг и перенос серверных изменений в форк

## Что сделано локально

Исходники и Git-история скопированы с `daun@admin.tracepace.ru:6767`:

- `/opt/remnawave-bedolaga-telegram-bot`, исходный HEAD `12c92f8e895638ab8d26b6af2ff77ac8ea91b9fd`, версия 5.0.0;
- `/opt/bedolaga-cabinet`, исходный HEAD `b866bebeeb6032db4baa3869a4917316fe8e0453`, версия 1.65.0.

Файлы VPS и контейнеры при этой работе не изменялись. Из копии исключены `.env`,
`.env.save*`, `wgcf-account.toml`, `wgcf-profile.conf`, данные БД, логи и загруженные медиа.
Они остаются на сервере; для будущего развёртывания используйте существующие файлы и volumes.

Серверные правки сохранены отдельными коммитами до реализации функции:

- бот: `f4321cd7`, публикация новостей с необязательной авторизацией, логотип и пять файлов переводов `locales/`;
- кабинет: `85b79e4`, volume uploads, nginx, verification HTML, повторная загрузка lazy-компонентов.

Новая функция находится в ветке `feat/free-access-until-quota` всех четырёх локальных репозиториев.
Форк бота: <https://github.com/stol3wd/remnawave-bedolaga-telegram-bot>.
Идентификаторы итоговых коммитов и переносимые Git bundle перечислены в локальном `RESULTS.md`.

## Поведение подписки

Оплаченная подписка в БД Bedolaga остаётся `expired`, с прежним тарифом, датой и платными
squads. Бот сохраняет дополнительную Grace Access сессию, переводит панельного пользователя
в `ACTIVE` только с бесплатным Internal Squad и ограничивает его трафик. Это согласуется
с [ролью Internal Squads в Remnawave](https://docs.rw/learn-en/squads/).

Квота — один раз на конкретную дату истечения оплаченной подписки. По умолчанию 1 ГиБ.
Она не обновляется каждый месяц и не имеет срока в бизнес-логике (`grace_until=NULL`).
Панель использует техническую дату `2099-12-31`, стратегию `NO_RESET` и лимит
`использовано до выдачи + бесплатная квота`. Счётчик при выдаче не обнуляется.
Остаток бесплатной квоты показывается отдельно в кабинете.

Выдача происходит существующим worker/webhook-механизмом Grace Access или кнопкой
«Бесплатный конфиг» в Telegram/кабинете. Для worker задержка соответствует
`GRACE_ACCESS_RECONCILE_INTERVAL_SECONDS` (по умолчанию 60 секунд).

`GET /sub/...` после выдачи использует прежний URL и штатные генераторы Remnawave.
`selectedHosts` ограничивает выдачу выбранным Host; VLESS UUID остаётся личным UUID пользователя.
Существующие raw keys, шаблоны Xray/Clash/Singbox и заголовки продолжают использоваться.
[Штатные raw links доступны в карточке пользователя](https://docs.rw/learn-en/users/).
URL подписки в этой версии панели использует short UUID; брать его нужно из существующего
`subscription_url`, а не самостоятельно подставлять UUID VLESS или числовой REST id.

После расходования квоты доступ закрывается. При переходе сначала удаляются доступные
inbounds, затем восстанавливаются платные настройки: промежуточного доступа к платным
нодам нет. Повторное нажатие не выдаёт квоту второй раз. Оплата восстанавливает актуальные
платные группы, лимит, стратегию сброса и прежний выбор Hosts.

Административная блокировка имеет приоритет. Удалённый/скрытый Host, неверная привязка
или выключенный inbound не дают новый доступ; исчезновение Host у действующей сессии
закрывает её. Временное отключение ноды не расходует выдачу повторно.
Для действующих сессий проверка общего Host кешируется на 30 секунд, чтобы не делать
одинаковые запросы панели на каждого подписчика. Перед новой выдачей кеш не используется.

Общий допуск всех панельных `EXPIRED` удалён. Их доступ не сохраняется на платных нодах.
Remnanode менять не требуется: штатный `addUser` удаляет прежние inbounds и добавляет
новый набор. Очередь панели перечитывает актуальное состояние пользователя после блокировки,
поэтому поздний REMOVE не уничтожает уже назначенный бесплатный доступ.

## Подготовить бесплатный Host

1. В Remnawave создайте отдельный VLESS inbound и активируйте его на нужной ноде.
2. Создайте бесплатный Internal Squad, содержащий **только этот inbound**. Не добавляйте
   в него платные inbounds: сохранённые пользователем старые ссылки должны потерять доступ.
3. В «Subscription → Settings → Бесплатный доступ после истечения оплаты» выберите:
   - `UUID Host`: UUID включённого, видимого Host, привязанного к этому inbound;
   - `VLESS URL`: вставьте ссылку, выберите бесплатный squad и существующий inbound.
     Импорт проверит транспорт, flow, encryption, Reality public key/short id/SNI и создаст Host.
     UUID из вставленной ссылки не сохраняется. Это должен быть inbound вашей панели,
     а не произвольная ссылка чужого VPN.
4. Скопируйте полученный UUID Host в настройку бота `GRACE_ACCESS_EXPIRED_HOST_UUID`.
   Сохранение Host в панели само по себе не включает выдачу бесплатной квоты.

Если импорт сообщает о неподдерживаемых параметрах, задайте Host штатной формой панели
и используйте его UUID. Не отключайте проверки ключей и транспорта.

Настройки Bedolaga доступны в кабинете через общий редактор настроек бота, группа Grace.
Сначала задайте UUID и квоту, затем включите режим. Если ключ уже записан в `.env`, значение
закреплено за `.env`; редактор БД не сможет его заменить. Новые строки `.env.example`
намеренно закомментированы.

```dotenv
GRACE_ACCESS_EXPIRED_SQUAD_UUID=<UUID бесплатного Internal Squad>
GRACE_ACCESS_EXPIRED_HOST_UUID=<UUID Host>
GRACE_ACCESS_EXPIRED_ELIGIBLE_SQUAD_UUIDS=<UUID платного squad>,<ещё один UUID при необходимости>
GRACE_ACCESS_TRAFFIC_GB=1
GRACE_ACCESS_LIMITED_SQUAD_UUID=
GRACE_ACCESS_RESET_TRAFFIC_ON_START=false
GRACE_ACCESS_EXTERNAL_SQUAD_UUID=
GRACE_ACCESS_EXPIRED_UNTIL_QUOTA=true
GRACE_ACCESS_MODE=true
```

Пустой LIMITED squad отключает выдачу по исчерпанию трафика в этом режиме. Флаги trial,
daily и free по умолчанию выключены: бесплатную квоту получают истёкшие платные подписки
из перечисленных исходных squads. Отдельный тип тарифа для бесплатной выдачи не создаётся.
Ограничение доступных сайтов при необходимости задавайте routing Xray бесплатного inbound;
Internal Squad определяет inbounds, а не домены назначения. Текст `GRACE_ACCESS_ALLOWED_SERVICES`
должен соответствовать фактическому routing (по умолчанию он говорит про Telegram).

## Опубликовать локальные коммиты

Команды выполняются на ПК в `C:\Users\minas\vibecode\remnawave\remnawave-src`.
Если ветка уже опубликована, повторный push безопасен.

```powershell
Set-Location C:\Users\minas\vibecode\remnawave\remnawave-src\bedolaga-bot
git remote set-url origin https://github.com/stol3wd/remnawave-bedolaga-telegram-bot.git
git push -u origin feat/free-access-until-quota
```

Для backend/frontend/cabinet нужны ваши собственные форки. В локальном frontend/backend
origin пока указывает на официальный проект; замените его на свой перед push:

```powershell
Set-Location ..\backend
git remote set-url origin https://github.com/<ваш аккаунт>/<форк backend>.git
git push -u origin feat/free-access-until-quota
Set-Location ..\frontend
git remote set-url origin https://github.com/<ваш аккаунт>/<форк frontend>.git
git push -u origin feat/free-access-until-quota
Set-Location ..\bedolaga-cabinet
git remote add origin https://github.com/<ваш аккаунт>/<форк cabinet>.git
git push -u origin feat/free-access-until-quota
```

Вместо GitHub можно перенести готовые `.bundle` из `artifacts/free-access` на другую машину:
`git clone --branch feat/free-access-until-quota <repo>.bundle <папка>`.
История и коммиты сохраняются. `.patch` там же содержит готовый diff функции; в bundle
бота и кабинета дополнительно включены сохранённые серверные правки.

## Безопасно обновить VPS вручную

Эти команды здесь приведены для следующего шага. Во время разработки они не выполнялись.
Сначала опубликуйте ветки, соберите новые панель и кабинет, сделайте резервную копию БД.

На VPS сохраните отдельно БД и файлы с правами только владельца:

```bash
ssh -p 6767 daun@admin.tracepace.ru
umask 077
backup_dir="$HOME/remnawave-before-free-access-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup_dir"
cd /opt/remnawave-bedolaga-telegram-bot
git bundle create "$backup_dir/bot-history.bundle" --all
tar --exclude='./.git' --exclude='./logs' --exclude='./.venv' \
    -czf "$backup_dir/bot-files.tar.gz" .
cd /opt/bedolaga-cabinet
git bundle create "$backup_dir/cabinet-history.bundle" --all
tar --exclude='./.git' --exclude='./node_modules' --exclude='./dist' \
    -czf "$backup_dir/cabinet-files.tar.gz" .
docker exec remnawave_bot_db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
    > "$backup_dir/bot-database.dump"
test -s "$backup_dir/bot-database.dump"
```

Архив файлов содержит серверные секреты; храните его приватно и не добавляйте в GitHub.
Проверяйте код возврата каждой команды, особенно `pg_dump`, до обновления контейнеров.
Сохраните также используемый compose панели и БД панели вашим обычным способом резервирования.

Сверьте `git status --short` с сохранёнными в начале документа изменениями. Если после
копирования появились новые правки, сохраните их и перенесите в отдельный коммит на ПК
перед pull. Приведённые ниже команды предполагают тот же набор правок, который был скопирован.

```bash
cd /opt/remnawave-bedolaga-telegram-bot
git status --short
git stash push -u -m 'VPS customizations before free-access pull' -- \
    app/cabinet/routes/news.py vpn_logo.png locales/en.json locales/fa.json \
    locales/ru.json locales/ua.json locales/zh.json
git remote set-url origin https://github.com/stol3wd/remnawave-bedolaga-telegram-bot.git
git fetch origin feat/free-access-until-quota
git merge-base --is-ancestor HEAD origin/feat/free-access-until-quota
git pull --ff-only origin feat/free-access-until-quota
git status --short
```

Не делайте `stash pop`: эти правки уже включены в baseline-коммит. Сохранённый stash и
архив остаются резервной копией. `.env`, WGCF и данные volumes не затрагиваются указанным stash.
При ошибке `--ff-only` остановитесь и разрешите расхождение локально; не используйте `reset --hard`.

Для кабинета после публикации своего форка аналогично:

```bash
cd /opt/bedolaga-cabinet
git status --short
git stash push -m 'VPS cabinet customizations before free-access pull' -- \
    docker-compose.yml nginx.conf index.html src/App.tsx
git remote set-url origin https://github.com/<ваш аккаунт>/<форк cabinet>.git
git fetch origin feat/free-access-until-quota
git merge-base --is-ancestor HEAD origin/feat/free-access-until-quota
git pull --ff-only origin feat/free-access-until-quota
```

Перед обновлением убедитесь, что нет открытых Grace-сессий. Обновляйте сначала панель
и кабинет, оставив `GRACE_ACCESS_MODE=false`, затем бот.
Контракты frontend должны быть собраны из изменённого backend, а не из старого npm-пакета:

```powershell
Set-Location C:\Users\minas\vibecode\remnawave\remnawave-src\backend
npm ci
Set-Location libs\contract
npm run build:backend
npm run build:frontend
Set-Location ..\..\..\frontend
npm ci
Copy-Item -LiteralPath ..\backend\libs\contract\build -Destination node_modules\@remnawave\backend-contract -Recurse -Force
npm run typecheck
npx vite build
Set-Location ..\backend
docker build -f Dockerfile.local --build-context frontend-src=../frontend -t remnawave-backend:free-access .
```

Используйте полученный образ в существующем compose панели. После обновления панели
перезапустите ноды через панель, чтобы удалить UUID, оставшиеся от прежнего общего
разрешения для `EXPIRED`, и построить конфигурации из актуальных `ACTIVE` и squads.
Это вызывает кратковременный перезапуск Xray; запланируйте его.

После pull бота выполняется миграция Alembic `0132` при штатном старте (проверьте лог).
Она разрешает `grace_until=NULL` и добавляет `quota_exhausted`, сохраняя историю, индексы
и запрет удаления подписки с открытой сессией. Для отката с уже созданными квотными
сессиями нужна резервная копия БД: downgrade намеренно запрещает потерю их истории.

```bash
cd /opt/remnawave-bedolaga-telegram-bot
docker compose build bot
docker compose up -d --no-deps bot
docker compose logs --tail=100 bot
cd /opt/bedolaga-cabinet
docker compose build cabinet-frontend
docker compose up -d --no-deps cabinet-frontend
```

После проверки миграции заполните UUID и включите выдачу по инструкции выше.
Для смены настройки уже действующей выдачи сначала прекратите новые выдачи через `drain`
и дождитесь отсутствия открытых сессий; затем меняйте Host/квоту.
Обычный `drain` прекращает новые выдачи; в квотном режиме срока нет, поэтому для немедленного
отключения конкретной выдачи отключите пользователя в панели и дождитесь закрытия сессии worker.

## Проверить после развёртывания

На тестовом пользователе из разрешённого платного squad:

1. Истечь оплаченной подписке; дождаться worker или нажать «Бесплатный конфиг».
2. В боте оплаченная дата не изменилась; в панели только бесплатный squad, `ACTIVE`, `NO_RESET`.
3. Прежний URL подписки отдаёт выбранный Host с UUID этого пользователя.
4. На ноде личный UUID есть в бесплатном inbound; старый платный конфиг не подключается.
5. Перезапуск ноды сохраняет бесплатный доступ.
6. Исчерпание квоты закрывает подключение; повторная кнопка и перезапуск бота не добавляют трафик.
7. Продление оплаты возвращает платные группы и настройки. Заблокированный администратором
   пользователь и пользователь вне разрешённых squads бесплатный доступ не получают.

Автотесты и локальные сборки описаны в `RESULTS.md`. Проверка на живой PostgreSQL/Xray
не выполнялась: Docker Engine на ПК не запущен, а VPS оставлен без изменений.
