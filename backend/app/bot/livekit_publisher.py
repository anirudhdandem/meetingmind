"""Publish captured PCM frames into a LiveKit room as a microphone audio track."""

from __future__ import annotations

from livekit import api, rtc

from app.bot.audio_capture import CHANNELS, SAMPLE_RATE
from app.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

BOT_IDENTITY = "meetingmind-bot"


class LiveKitPublisher:
    """Connects to a room and exposes capture_frame() for raw PCM bytes."""

    def __init__(self, room_name: str) -> None:
        self.room_name = room_name
        self._room = rtc.Room()
        self._source: rtc.AudioSource | None = None

    def _token(self) -> str:
        s = get_settings()
        return (
            api.AccessToken(s.livekit_api_key, s.livekit_api_secret)
            .with_identity(BOT_IDENTITY)
            .with_name("MeetingMind Bot")
            .with_grants(api.VideoGrants(room_join=True, room=self.room_name))
            .to_jwt()
        )

    async def connect(self) -> None:
        s = get_settings()
        await self._room.connect(s.livekit_url, self._token())
        self._source = rtc.AudioSource(SAMPLE_RATE, CHANNELS)
        track = rtc.LocalAudioTrack.create_audio_track("meet-audio", self._source)
        await self._room.local_participant.publish_track(
            track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        )
        log.info("Publishing audio into LiveKit room %s", self.room_name)

    async def capture_frame(self, pcm: bytes) -> None:
        assert self._source is not None, "connect() first"
        samples_per_channel = len(pcm) // (2 * CHANNELS)
        frame = rtc.AudioFrame(
            data=pcm,
            sample_rate=SAMPLE_RATE,
            num_channels=CHANNELS,
            samples_per_channel=samples_per_channel,
        )
        await self._source.capture_frame(frame)

    async def close(self) -> None:
        await self._room.disconnect()
        log.info("Disconnected publisher from room %s", self.room_name)
