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
    assert channel.sent[3].chat_id == OWNER and "Terkirim" in channel.sent[3].text
    assert len(channel.sent) == 4


def test_failed_reply_is_reported_to_owner_and_can_be_retried(brain, store):
    class CustomerUnreachable(FakeChannel):
        down = True

        def send(self, out):
            if self.down and out.chat_id == "7":
                raise RuntimeError("blocked by user")
            return super().send(out)

    channel = CustomerUnreachable()
    app = App(brain, [channel])
    app.on_message(customer("bisa hutang dulu?", chat_id="7"))  # only the forward gets out
    app.on_message(owner("Boleh kak", reply_to_id="501"))

    assert [o.chat_id for o in channel.sent] == [OWNER, OWNER]
    assert channel.sent[1].text.startswith("Gagal kirim")
    assert store.get_handoff(1)["answer"] is None

    channel.down = False
    app.on_message(owner("Boleh kak", reply_to_id="501"))
    assert [o.chat_id for o in channel.sent[2:]] == ["7", OWNER]
    assert store.get_handoff(1)["answer"] == "Boleh kak"


def test_message_for_an_inactive_channel_is_not_confirmed(brain, store):
    channel = FakeChannel()
    app = App(brain, [channel])
    hid = store.create_handoff(brain.today(), "whatsapp", "62811", "Budi", "bisa hutang?")
    app.on_message(owner(f"/balas {hid} boleh kak"))
    assert [o.text.split()[0] for o in channel.sent] == ["Gagal"]


def test_send_failure_does_not_stop_other_messages(brain):
    class Flaky(FakeChannel):
        def send(self, out):
            if out.chat_id == OWNER:
                raise RuntimeError("owner unreachable")
            return super().send(out)

    channel = Flaky()
    App(brain, [channel]).on_message(customer("bisa hutang dulu?"))
    assert [o.chat_id for o in channel.sent] == ["1"]
