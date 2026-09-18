# SMS worker

This package converts validated MQTT alert requests into dry-run logs or SMS
delivery through ModemManager. It runs as the single SMS container and never
decides whether a measurement is dangerous.

| File | Responsibility |
|---|---|
| `__main__.py` | Load config, construct storage/sender/subscriber, start optional inbound polling and handle shutdown |
| `subscriber.py` | Subscribe, validate requests, suppress duplicates and publish results/status |
| `sender.py` | Select recipients, queue delivery, call `mmcli`, retry, persist subscriptions and process replies |
| `__init__.py` | Identify the package |

Home Assistant publishes strict requests to `labpulse/sms/send`. Recent request
IDs and event keys are suppressed. Accepted recipient work is queued
sequentially, but the queue is in memory and delivery is not guaranteed.

Dry-run validates and logs without a modem. Home Assistant Test mode prefixes
`[TEST]` and uses `test_recipients`; normal mode uses `recipients`. Inbound
`SUBSCRIBE` and `UNSUBSCRIBE` are accepted only from configured numbers, and a
lock serializes modem send/receive operations.

## Follow an alert

1. [`main()`](__main__.py) loads settings, opens subscription/request-ID state,
   creates the sender, then runs the subscriber's MQTT loop on the main thread.
2. Paho calls [`SmsSubscriber.on_message()`](subscriber.py).
   `parse_sms_payload()` validates the bytes as a
   [`SmsRequest`](../common/mqtt_contracts.py). It contains event identity, text
   and `test_mode`, but no phone numbers. `request_id` links logs and results.
3. `RecentRequestCache.rejection_reason()` checks the saved request ID and a
   short cooldown keyed by mode, service, measurement and event.
4. [`SmsSender.broadcast()`](sender.py) selects normal/test recipients and
   filters subscription choices. It queues `(recipient, request)` pairs only
   when there is room for all active recipients. True means accepted, even if
   everyone has unsubscribed; it never means delivered. Only accepted request
   IDs are remembered by the subscriber.
5. `_worker()` takes one pair, formats the text and calls `send_sms()`. Real
   delivery uses `_send_with_mmcli()` with retries; dry-run just logs.
6. `_report()` calls `publish_delivery_result()`, which serializes a
   `DeliveryResult` to the request's MQTT result topic. `sent` means the modem
   command succeeded; `logged` means dry-run. Neither proves phone receipt.
   Recipient numbers in results are masked; whole-request results use an empty
   recipient.

## Threads, stored state and stopping

The sender thread starts in `SmsSender.__init__()`. Real mode also starts
`SmsCommandMonitor`, which polls inbound messages and processes subscription
commands. Its confirmations call `send_sms()` directly. `_modem_lock` prevents
send/receive operations from overlapping; it is re-entrant so one thread can
enter it again. `SubscriptionRegistry` has a separate lock protecting opt-out
choices and their JSON writes. The main MQTT loop alone owns the request cache;
the sender's result callback publishes messages without changing that cache.

Subscription choices and accepted request-ID timestamps survive restart in
`logs/sms_subscriptions.json` and `logs/sms_processed_requests.json`. Event
cooldowns, pending recipient pairs and inbound processed-path tracking stay in
memory. The broker's persistent session can redeliver QoS 1 requests (delivery
at least once), but it does not preserve the sender queue. A crash after an ID
is remembered can therefore lose unsent work while still suppressing its replay.

Shutdown stops inbound polling, asks the sender to drain its queue, then
publishes offline status and disconnects MQTT. A `None` queue entry tells the
sender to exit after earlier work. Adding it can wait on a full queue; the join
timeout only limits the subsequent wait, and a warning does not kill the thread.

Keep routing and delivery here. Alarm decisions belong to Home Assistant;
topics, payloads and message text come from `labpulse.common`. Tests include
`test_sms_container.py`, contract tests and notification-context tests. See
[User Guide](../../../docs/USER_GUIDE.md),
[Configuration](../../../docs/CONFIGURATION.md) and
[Installation](../../../docs/INSTALLATION.md).
