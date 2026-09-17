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

Keep routing and delivery here. Alarm decisions belong to Home Assistant;
topics, payloads and message text come from `labpulse.common`. Tests include
`test_sms_container.py`, contract tests and notification-context tests. See
[User Guide](../../../docs/USER_GUIDE.md),
[Configuration](../../../docs/CONFIGURATION.md) and
[Installation](../../../docs/INSTALLATION.md).
