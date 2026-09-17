"""Reliable HomePod announcement players using direct RAOP streaming."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from typing import Any
from urllib.parse import urlparse

import pyatv
import voluptuous as vol
from pyatv.const import DeviceState, Protocol

from homeassistant.components import media_source
from homeassistant.components.media_player import (
    PLATFORM_SCHEMA,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, STATE_PLAYING
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.network import get_url

_LOGGER = logging.getLogger(__name__)

from .const import (
    CONF_IDENTIFIER,
    CONF_IDLE_ANNOUNCEMENT_VOLUME,
    CONF_PLAYING_VOLUME_BOOST,
    CONF_SOURCE_ENTITY,
    DEFAULT_IDLE_ANNOUNCEMENT_VOLUME,
    DEFAULT_PLAYING_VOLUME_BOOST,
    DOMAIN,
)

CONF_SPEAKERS = "speakers"

SPEAKER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_IDENTIFIER): cv.string,
        vol.Required(CONF_SOURCE_ENTITY): cv.entity_id,
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {vol.Required(CONF_SPEAKERS): vol.All(cv.ensure_list, [SPEAKER_SCHEMA])}
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: dict[str, Any],
    async_add_entities: AddEntitiesCallback,
    discovery_info: dict[str, Any] | None = None,
) -> None:
    """Create configured RAOP announcement players."""
    async_add_entities(
        RaopAnnouncementPlayer(
            hass,
            speaker[CONF_NAME],
            speaker[CONF_IDENTIFIER],
            speaker[CONF_SOURCE_ENTITY],
        )
        for speaker in config[CONF_SPEAKERS]
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one RAOP player from a config entry."""
    async_add_entities(
        [
            RaopAnnouncementPlayer(
                hass,
                entry.data[CONF_NAME],
                entry.data[CONF_IDENTIFIER],
                entry.data[CONF_SOURCE_ENTITY],
                entry,
            )
        ]
    )


class RaopAnnouncementPlayer(MediaPlayerEntity):
    """A media player that pushes announcements directly to a HomePod."""

    _attr_has_entity_name = True
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_should_poll = False
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.BROWSE_MEDIA
        | MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.VOLUME_SET
    )

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        identifier: str,
        source_entity: str,
        entry: ConfigEntry | None = None,
    ) -> None:
        self.hass = hass
        self._attr_name = None
        self._device_name = name
        self._attr_unique_id = f"wakemesh_speaker_{identifier.lower()}"
        self._identifier = identifier
        self._source_entity = source_entity
        self._entry = entry
        self._remove_listener = None
        self._attr_device_info = DeviceInfo(
            identifiers={(
                DOMAIN,
                entry.unique_id if entry and entry.unique_id else self._identifier.lower(),
            )},
            name=self._device_name,
            manufacturer="WakeMesh",
            model="AirPlay announcement destination",
        )

    @property
    def _playing_volume_boost(self) -> float:
        if self._entry:
            return float(
                self._entry.options.get(
                    CONF_PLAYING_VOLUME_BOOST, DEFAULT_PLAYING_VOLUME_BOOST
                )
            )
        return DEFAULT_PLAYING_VOLUME_BOOST

    @property
    def _idle_announcement_volume(self) -> float:
        if self._entry:
            return float(
                self._entry.options.get(
                    CONF_IDLE_ANNOUNCEMENT_VOLUME,
                    DEFAULT_IDLE_ANNOUNCEMENT_VOLUME,
                )
            )
        return DEFAULT_IDLE_ANNOUNCEMENT_VOLUME

    @property
    def available(self) -> bool:
        # RAOP discovery is independent of the native Apple entity. The proxy
        # remains a valid destination even while that entity is sleeping.
        return True

    @property
    def state(self) -> str | None:
        source = self.hass.states.get(self._source_entity)
        return source.state if source else None

    @property
    def volume_level(self) -> float | None:
        source = self.hass.states.get(self._source_entity)
        return source.attributes.get("volume_level") if source else None

    async def async_added_to_hass(self) -> None:
        self._remove_listener = self.hass.bus.async_listen(
            "state_changed", self._source_state_changed
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_listener:
            self._remove_listener()

    async def _source_state_changed(self, event) -> None:
        if event.data.get("entity_id") == self._source_entity:
            self.async_write_ha_state()

    async def _connect(self):
        devices = await pyatv.scan(self.hass.loop, timeout=7)
        if not devices:
            raise RuntimeError(f"RAOP device {self._identifier} was not discovered")

        identifier = self._identifier.lower()
        configured = next(
            (
                device
                for device in devices
                if identifier
                in {str(value).lower() for value in device.all_identifiers}
            ),
            None,
        )
        if configured is None:
            raise RuntimeError(f"RAOP device {self._identifier} was not discovered")

        # Apple advertises a stereo pair or active multi-room group as several
        # endpoints sharing a group id (gid). Exactly one endpoint advertises
        # itself as the group leader (igl=1). Connecting only to that endpoint
        # lets AirPlay fan the stream out in sync and avoids competing streams.
        selected = configured
        airplay = configured.get_service(Protocol.AirPlay)
        properties = airplay.properties if airplay else {}
        group_id = properties.get("gid")
        stereo_pair_id = properties.get("tsid")
        if group_id and stereo_pair_id:
            for candidate in devices:
                candidate_airplay = candidate.get_service(Protocol.AirPlay)
                candidate_properties = (
                    candidate_airplay.properties if candidate_airplay else {}
                )
                if (
                    candidate_properties.get("gid") == group_id
                    and candidate_properties.get("tsid") == stereo_pair_id
                    and candidate_properties.get("igl") == "1"
                ):
                    selected = candidate
                    break

        if selected is not configured:
            _LOGGER.info(
                "Resolved grouped RAOP endpoint %s to leader %s at %s",
                configured.name,
                selected.name,
                selected.address,
            )
        return await pyatv.connect(selected, self.hass.loop)

    async def _download(self, url: str, content_type: str | None) -> str:
        suffix = os.path.splitext(urlparse(url).path)[1]
        if not suffix:
            suffix = {
                "audio/mpeg": ".mp3",
                "audio/wav": ".wav",
                "audio/x-wav": ".wav",
                "audio/flac": ".flac",
            }.get(content_type or "", ".audio")

        session = async_get_clientsession(self.hass)
        async with session.get(url, timeout=30) as response:
            response.raise_for_status()
            payload = await response.read()

        handle, path = tempfile.mkstemp(prefix="ha-raop-", suffix=suffix)
        os.close(handle)
        await self.hass.async_add_executor_job(self._write_file, path, payload)
        return path

    @staticmethod
    def _write_file(path: str, payload: bytes) -> None:
        with open(path, "wb") as output:
            output.write(payload)

    async def async_play_media(
        self,
        media_type: str,
        media_id: str,
        enqueue=None,
        announce: bool | None = None,
        **kwargs: Any,
    ) -> None:
        """Push audio over RAOP and restore prior music playback."""
        source = self.hass.states.get(self._source_entity)
        was_playing = source is not None and source.state == STATE_PLAYING
        path = None
        player = None
        original_volume = None
        try:
            if media_id.startswith("media-source://"):
                resolved = await media_source.async_resolve_media(
                    self.hass, media_id, self.entity_id
                )
                media_id = resolved.url
                media_type = resolved.mime_type or media_type
            if media_id.startswith("/") and not media_id.startswith("/config/"):
                media_id = f"{get_url(self.hass, prefer_external=False)}{media_id}"
            if media_id.startswith(("http://", "https://")):
                path = await self._download(media_id, media_type)
            elif media_id.startswith("/config/"):
                path = media_id
            else:
                raise ValueError("WakeMesh requires an HTTP(S) URL or /config path")

            player = await self._connect()
            try:
                playing = await player.metadata.playing()
                was_playing = was_playing or playing.device_state == DeviceState.Playing
            except Exception:  # Device metadata is optional on some HomePods.
                _LOGGER.debug("Could not read current RAOP playback state", exc_info=True)
            try:
                original_volume = player.audio.volume
                if original_volume is not None:
                    announcement_volume = (
                        min(100.0, original_volume + self._playing_volume_boost)
                        if was_playing
                        else self._idle_announcement_volume
                    )
                    if announcement_volume != original_volume:
                        await player.audio.set_volume(announcement_volume)
            except Exception:
                _LOGGER.debug("Could not adjust RAOP announcement volume", exc_info=True)
            _LOGGER.info(
                "Streaming RAOP announcement to %s (was_playing=%s, volume=%s)",
                self._identifier,
                was_playing,
                original_volume,
            )
            await player.stream.stream_file(path)
        finally:
            if player:
                if original_volume is not None:
                    try:
                        await player.audio.set_volume(original_volume)
                    except Exception:
                        _LOGGER.warning("Could not restore RAOP volume", exc_info=True)
                player.close()
            if path and path.startswith(tempfile.gettempdir()):
                await self.hass.async_add_executor_job(os.unlink, path)

        if was_playing:
            await asyncio.sleep(1.5)
            resume_player = await self._connect()
            try:
                await resume_player.remote_control.play()
                _LOGGER.info("Resumed prior playback on %s", self._identifier)
            finally:
                resume_player.close()

    async def async_browse_media(
        self,
        media_content_type: str | None = None,
        media_content_id: str | None = None,
    ):
        """Expose Home Assistant media sources for the destination picker."""
        return await media_source.async_browse_media(self.hass, media_content_id)

    async def async_media_play(self) -> None:
        await self.hass.services.async_call(
            "media_player", "media_play", {"entity_id": self._source_entity}, blocking=True
        )

    async def async_media_pause(self) -> None:
        await self.hass.services.async_call(
            "media_player", "media_pause", {"entity_id": self._source_entity}, blocking=True
        )

    async def async_set_volume_level(self, volume: float) -> None:
        await self.hass.services.async_call(
            "media_player",
            "volume_set",
            {"entity_id": self._source_entity, "volume_level": volume},
            blocking=True,
        )
