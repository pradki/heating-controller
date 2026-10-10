# tests/fakes.py - wspólne atrapy dla testów (bez brokera i bez sprzętu)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from relay_client import GatewayRelay  # noqa: E402

_failures = []


def check(name, cond):
    print(("OK  " if cond else "FAIL"), name)
    if not cond:
        _failures.append(name)


def done():
    if _failures:
        print(f"done - {len(_failures)} FAILED: {', '.join(_failures)}")
        sys.exit(1)
    print("done")


class FakePublisher:
    """Zbiera to, co poszłoby na brokera. `rc=0` imituje udaną publikację -
    testy na nieudaną publikację nadpisują `rc` albo `fail_next`."""

    def __init__(self):
        self.messages = []
        self.fail_next = False

    def __call__(self, topic, payload, qos=0, retain=False):
        rc = 4 if self.fail_next else 0
        self.fail_next = False
        self.messages.append((topic, payload, qos, retain, rc))
        return _FakePublishResult(rc)

    def clear(self):
        self.messages = []

    def topics(self):
        return [m[0] for m in self.messages]

    def last(self, topic=None):
        msgs = self.messages if topic is None else [m for m in self.messages if m[0] == topic]
        return msgs[-1] if msgs else None


class _FakePublishResult:
    def __init__(self, rc):
        self.rc = rc


def build(service="heating_service", priority=10):
    publisher = FakePublisher()
    relay = GatewayRelay(publisher, "cave/relay", "relay_heating", service, priority=priority)
    return publisher, relay
