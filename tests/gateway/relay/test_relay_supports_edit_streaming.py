"""A relay chat whose descriptor says ``supports_edit: false`` must not be streamed (#154674).

The stream consumer re-sends every update it cannot edit as a NEW message, so streaming into a
connector that cannot edit (SMS / iMessage) turns one reply into a burst of texts. The gateway
skips streaming for non-editing adapters through ``SUPPORTS_MESSAGE_EDITING``; the relay adapter
fronts several platforms, so the answer has to come from the chat's own descriptor.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from gateway.config import Platform, PlatformConfig
from gateway.platforms.event import MessageEvent, MessageType
from gateway.relay.adapter import RelayAdapter
from gateway.relay.descriptor import CONTRACT_VERSION, CapabilityDescriptor
from gateway.run_turn import GatewayTurnMixin, adapter_supports_editing
from gateway.session import SessionSource

from tests.gateway.relay.test_relay_per_platform_caps import MultiDescriptorStub


def _descriptor(platform: str, *, supports_edit: bool, ops: tuple = ()) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        contract_version=CONTRACT_VERSION, platform=platform, label=platform.title(),
        max_message_length=4096, supports_draft_streaming=False, supports_edit=supports_edit,
        supports_threads=False, markdown_dialect="plain", len_unit="chars", supported_ops=ops,
    )


SMS = _descriptor("sms", supports_edit=False)
TELEGRAM = _descriptor("telegram", supports_edit=True)


def _source(platform: Platform, chat_id: str) -> SessionSource:
    return SessionSource(platform=platform, chat_id=chat_id, chat_type="dm", user_id="u-1")


async def _adapter(primary, *others):
    stub = MultiDescriptorStub(primary, *others)
    stub._identities = [(d.platform, f"bot-{d.platform}") for d in (primary, *others)]
    adapter = RelayAdapter(PlatformConfig(), primary, transport=stub)
    await adapter.connect()
    return stub, adapter


async def _push(stub, platform, chat_id):
    await stub.push_inbound(MessageEvent(text="hi", message_type=MessageType.TEXT,
                                         source=_source(platform, chat_id)))


def _scfg():
    return SimpleNamespace(cursor=" ▉", edit_interval=1.0, buffer_threshold=40,
                           fresh_final_after_seconds=0.0, transport="edit")


@pytest.mark.asyncio
async def test_non_editable_relay_chat_skips_streaming_and_editable_chat_still_streams():
    stub, adapter = await _adapter(TELEGRAM, SMS)
    await _push(stub, Platform.TELEGRAM, "tg-1")
    adapter._platform_by_chat["sms-1"] = "sms"  # an inbound from the SMS connector

    assert adapter.supports_message_editing_for_chat("sms-1") is False
    assert adapter.supports_message_editing_for_chat("tg-1") is True
    assert adapter_supports_editing(adapter, "sms-1") is False

    runner = object.__new__(GatewayTurnMixin)
    with pytest.raises(RuntimeError):
        runner._build_stream_consumer_config(_source(Platform.RELAY, "sms-1"), _scfg(), adapter,
                                             on_missing_cursor="raise")
    cfg, _ = runner._build_stream_consumer_config(_source(Platform.RELAY, "tg-1"), _scfg(), adapter,
                                                  on_missing_cursor="raise")
    assert cfg.cursor == " ▉"
    # The commentary fallback still builds a consumer for the SMS chat, without an edit cursor.
    cfg, _ = runner._build_stream_consumer_config(_source(Platform.RELAY, "sms-1"), _scfg(), adapter,
                                                  on_missing_cursor="fallback")
    assert cfg.cursor == ""


@pytest.mark.asyncio
async def test_primary_descriptor_without_edit_governs_unknown_chats():
    _stub, adapter = await _adapter(SMS)
    assert adapter.supports_message_editing_for_chat("never-seen") is False


@pytest.mark.asyncio
async def test_edit_op_missing_from_advertised_ops_means_no_editing():
    no_edit_op = replace(TELEGRAM, supported_ops=("send", "typing"))
    _stub, adapter = await _adapter(no_edit_op)
    assert adapter.supports_message_editing_for_chat("c") is False
    legacy = replace(TELEGRAM, supported_ops=())  # legacy connector: LEGACY_OPS includes edit
    _stub, adapter = await _adapter(legacy)
    assert adapter.supports_message_editing_for_chat("c") is True


def test_non_relay_adapters_keep_the_class_attribute():
    assert adapter_supports_editing(SimpleNamespace(SUPPORTS_MESSAGE_EDITING=False), "c") is False
    assert adapter_supports_editing(SimpleNamespace(SUPPORTS_MESSAGE_EDITING=True), "c") is True
    assert adapter_supports_editing(SimpleNamespace(), "c") is True
