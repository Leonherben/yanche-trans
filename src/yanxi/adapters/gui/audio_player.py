"""基于 PySide6 QtMultimedia 的音频播放适配器 (Audio Player Adapter)

支持后台异步抓取音频、主线程安全播放、口音状态管理与错误处理。
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QMediaDevices

from yanxi.core.tts import AccentType, TTSManager

logger = logging.getLogger(__name__)


class AudioPlayer(QObject):
    """音频播放控制器 (线程安全，支持异步加载与口音追踪)"""

    playback_started = Signal(str)       # 参数: accent ("uk" | "us")
    playback_finished = Signal(str)      # 参数: accent ("uk" | "us")
    playback_failed = Signal(str, str)   # 参数: accent, error_message

    _internal_audio_ready = Signal(str, str, int)   # file_path, accent, req_id
    _internal_audio_failed = Signal(str, str, int)  # accent, error_msg, req_id

    def __init__(self, tts_manager: Optional[TTSManager] = None, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.tts_manager = tts_manager or TTSManager()

        self._player = QMediaPlayer(self)
        self._output = QAudioOutput(self)
        self._player.setAudioOutput(self._output)
        self._output.setVolume(0.85)

        # 动态绑定系统默认音频输出设备，跟随系统插拔耳机/切换蓝牙/扬声器
        self._media_devices = QMediaDevices(self)
        self._media_devices.audioOutputsChanged.connect(self._sync_default_output_device)
        self._sync_default_output_device()

        self._active_accent: str = ""
        self._active_channel: str = ""  # "orig" | "trans"
        self._request_seq: int = 0
        self._lock = threading.Lock()

        # 连接内部跨线程信号
        self._internal_audio_ready.connect(self._on_internal_audio_ready)
        self._internal_audio_failed.connect(self._on_internal_audio_failed)

        # 监听播放状态
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.errorOccurred.connect(self._on_player_error)

    def play(self, text: str, accent: AccentType = "us", channel: str = "orig") -> None:
        """播放指定文本的指定口音音频

        :param text: 待发音文本
        :param accent: "uk" (英音) 或 "us" (美音)
        :param channel: 发音来源渠道 ("orig" 原文, "trans" 译文)
        """
        clean_text = " ".join(text.strip().split())
        if not clean_text:
            return

        with self._lock:
            self._request_seq += 1
            current_req_id = self._request_seq
            self._active_channel = channel

        # 若已命中本地磁盘缓存，直接主线程即时播放
        cached_file = self.tts_manager.get_cached_audio_path(clean_text, accent)
        if cached_file and cached_file.exists() and cached_file.stat().st_size > 0:
            self._play_file(str(cached_file), accent, current_req_id)
            return

        # 无缓存时通知开始加载并启动后台下载线程
        self.playback_started.emit(accent)

        def _fetch_worker() -> None:
            try:
                audio_path = self.tts_manager.fetch_audio_file(clean_text, accent)
                if audio_path and audio_path.exists():
                    self._internal_audio_ready.emit(str(audio_path), accent, current_req_id)
                else:
                    self._internal_audio_failed.emit(accent, "无法获取发音音频", current_req_id)
            except Exception as e:
                logger.warning("TTS audio fetch failed: %s", e)
                self._internal_audio_failed.emit(accent, str(e), current_req_id)

        threading.Thread(target=_fetch_worker, daemon=True).start()

    def stop(self) -> None:
        """停止播放当前音频"""
        self._player.stop()
        if self._active_accent:
            finished_accent = self._active_accent
            self._active_accent = ""
            self.playback_finished.emit(finished_accent)

    @Slot(str, str, int)
    def _on_internal_audio_ready(self, file_path: str, accent: str, req_id: int) -> None:
        with self._lock:
            if req_id != self._request_seq:
                return  # 用户在此期间发起了更新的播放请求，放弃旧结果
        self._play_file(file_path, accent, req_id)

    @Slot(str, str, int)
    def _on_internal_audio_failed(self, accent: str, err_msg: str, req_id: int) -> None:
        with self._lock:
            if req_id != self._request_seq:
                return
            if self._active_accent == accent:
                self._active_accent = ""
        self.playback_failed.emit(accent, err_msg)

    def _sync_default_output_device(self) -> None:
        """保持音频输出设备与操作系统当前默认输出设备严格同步（支持耳机/蓝牙热插拔）"""
        try:
            default_dev = self._media_devices.defaultAudioOutput()
            current_dev = self._output.device()
            if default_dev and (not current_dev or default_dev.id() != current_dev.id()):
                self._output.setDevice(default_dev)
                logger.debug("Synced audio output device to: %s", default_dev.description())
        except Exception as e:
            logger.debug("Audio device sync failed: %s", e)

    def _play_file(self, file_path: str, accent: str, req_id: int) -> None:
        with self._lock:
            if req_id != self._request_seq:
                return
            self._active_accent = accent

        self._sync_default_output_device()
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(file_path))
        self._player.play()
        self.playback_started.emit(accent)

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.StoppedState:
            if self._active_accent:
                finished_accent = self._active_accent
                self._active_accent = ""
                self.playback_finished.emit(finished_accent)

    def _on_player_error(self, error: QMediaPlayer.Error, error_string: str) -> None:
        logger.warning("MediaPlayer error %s: %s", error, error_string)
        if self._active_accent:
            acc = self._active_accent
            self._active_accent = ""
            self.playback_failed.emit(acc, error_string)
