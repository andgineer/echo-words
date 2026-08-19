from echo_words.events import EventHub

pytestmark = __import__("pytest").mark.anyio


async def test_two_subscribers_receive_the_same_event():
    hub = EventHub()
    async with hub.subscribe() as phone, hub.subscribe() as desktop:
        await hub.publish("update", {"entry_id": "one", "text": "слово"})
        assert await phone.get() == await desktop.get()


async def test_a_slow_subscriber_is_dropped_instead_of_blocking_publication():
    hub = EventHub(subscriber_capacity=1)
    async with hub.subscribe() as slow:
        await hub.publish("first", {})
        await hub.publish("second", {})
        assert hub.subscriber_count == 0
        assert (await slow.get()).name == "_disconnect"
