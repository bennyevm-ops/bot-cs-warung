from bot_cs_warung.app import App
from tests.conftest import OWNER, customer, owner


class FakeChannel:
    name = "telegram"

    def __init__(self):
        self.sent = []

    def send(self, out):
        self.sent.append(out)
        return str(500 + len(self.sent))


def test_handoff_round_trip_through_channel(brain):
    channel = FakeChannel()
    app = App(brain, [channel])

    app.on_message(customer("bisa hutang dulu?", chat_id="7"))
    forward, wait = channel.sent
    assert (forward.chat_id, wait.chat_id) == (OWNER, "7")

    # the owner replies to the forwarded message (its id is what the channel returned)
    app.on_message(owner("Boleh kak", reply_to_id="501"))
    assert (channel.sent[2].chat_id, channel.sent[2].text) == ("7", "Dari pemilik: Boleh kak")


def test_send_failure_does_not_stop_other_messages(brain):
    class Flaky(FakeChannel):
        def send(self, out):
            if out.chat_id == OWNER:
                raise RuntimeError("owner unreachable")
            return super().send(out)

    channel = Flaky()
    App(brain, [channel]).on_message(customer("bisa hutang dulu?"))
    assert [o.chat_id for o in channel.sent] == ["1"]
