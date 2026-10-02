"""言蹊翻译 (YanXi Trans) 设置与 API 配置中心

支持在图形界面中可视化配置翻译服务 API Key、大模型参数、快捷键与外观主题。
"""

from __future__ import annotations

import copy
import threading
from typing import Callable, Dict, Optional

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import yanxi
from yanxi.core.config import AppConfig, ProviderConfig
from yanxi.core.provider_state import is_configured
from yanxi.adapters.gui.selection_modes import MODE_LABELS, MODE_DESCRIPTIONS
from yanxi.adapters.gui.providers import provider_menu_label
from yanxi.core.translator.factory import create_translator
from yanxi.core.updater import check_github_update, open_release_page, UpdateInfo
from yanxi.adapters.gui.theme import AVAILABLE_THEMES
from yanxi.adapters.gui.icon_helper import get_app_icon, find_icon_path


class _TestWorkerSignals(QObject):
    finished = Signal(bool, str)


class _UpdateWorkerSignals(QObject):
    finished = Signal(object)


class SettingsDialog(QDialog):
    """可视化设置中心对话框"""

    def __init__(
        self,
        config: AppConfig,
        on_save: Optional[Callable[[AppConfig], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("言蹊翻译 - 设置")
        self.setWindowIcon(get_app_icon())
        self.resize(520, 560)
        self.setMinimumSize(460, 480)

        self.config = config
        self.on_save = on_save

        # 临时工作副本，点击“保存”时再应用
        self.working_config = copy.deepcopy(config)
        self.current_provider_name = self.working_config.default_provider
        if self.current_provider_name not in self.working_config.providers:
            self.current_provider_name = next(iter(self.working_config.providers.keys()), "microsoft")

        self.signals = _TestWorkerSignals()
        self.signals.finished.connect(self._on_test_finished)
        self.update_signals = _UpdateWorkerSignals()
        self.update_signals.finished.connect(self._on_update_result)
        self.latest_update_info: Optional[UpdateInfo] = None

        self._init_ui()
        self._apply_dialog_style()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        self.tab_widget = QTabWidget(self)

        # 1. 翻译服务选项卡
        self.providers_tab = self._create_providers_tab()
        self.tab_widget.addTab(self.providers_tab, "翻译服务与 API")

        # 2. 取词与快捷键选项卡
        self.selection_tab = self._create_selection_tab()
        self.tab_widget.addTab(self.selection_tab, "快捷键与取词")

        # 3. 界面与交互选项卡
        self.ui_tab = self._create_ui_tab()
        self.tab_widget.addTab(self.ui_tab, "外观与交互")

        # 4. 软件更新与关于选项卡
        self.about_tab = self._create_about_tab()
        self.tab_widget.addTab(self.about_tab, "软件更新与关于")

        main_layout.addWidget(self.tab_widget)

        # 底部操作栏
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.save_btn = QPushButton("保存并应用", self)
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._on_save_clicked)

        self.cancel_btn = QPushButton("取消", self)
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)
        main_layout.addLayout(btn_layout)

    # ==============================
    # 选项卡 1: 翻译服务与 API Key
    # ==============================
    def _create_providers_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # 顶部引擎选择栏
        selector_layout = QHBoxLayout()
        selector_label = QLabel("选择配置服务商:", widget)
        self.provider_combo = QComboBox(widget)
        self.provider_combo.setMinimumWidth(220)

        for name in self.working_config.providers.keys():
            self.provider_combo.addItem(provider_menu_label(name, self.working_config.providers[name]), name)

        idx = self.provider_combo.findData(self.current_provider_name)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)
        self.provider_combo.currentIndexChanged.connect(
            lambda index: self._on_provider_selection_changed(self.provider_combo.itemData(index))
        )

        selector_layout.addWidget(selector_label)
        selector_layout.addWidget(self.provider_combo)
        selector_layout.addStretch()
        layout.addLayout(selector_layout)

        # 服务商配置表单组
        self.provider_group = QGroupBox("参数配置", widget)
        form_layout = QFormLayout(self.provider_group)
        form_layout.setContentsMargins(12, 16, 12, 16)
        form_layout.setSpacing(10)

        # 提示标签 (针对免 Key 微软翻译)
        self.provider_hint_label = QLabel(self.provider_group)
        self.provider_hint_label.setWordWrap(True)
        self.provider_hint_label.setStyleSheet("color: #0969da; font-size: 12px; margin-bottom: 6px;")
        form_layout.addRow(self.provider_hint_label)

        # API Key
        key_layout = QHBoxLayout()
        self.key_edit = QLineEdit(self.provider_group)
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("请输入 API Key (部分免配置服务可留空)")

        self.eye_btn = QPushButton("👁", self.provider_group)
        self.eye_btn.setFixedSize(30, 26)
        self.eye_btn.setToolTip("显示/隐藏 API Key")
        self.eye_btn.clicked.connect(self._toggle_key_echo)

        key_layout.addWidget(self.key_edit)
        key_layout.addWidget(self.eye_btn)
        form_layout.addRow("API 密钥:", key_layout)

        # 模型名称
        self.model_edit = QLineEdit(self.provider_group)
        self.model_edit.setPlaceholderText("如 deepseek-chat, gpt-4o-mini 等")
        form_layout.addRow("模型名称:", self.model_edit)

        # API Base URL
        self.url_edit = QLineEdit(self.provider_group)
        self.url_edit.setPlaceholderText("API 基础请求地址")
        form_layout.addRow("API 地址:", self.url_edit)

        # 设为默认服务
        self.default_check = QPushButton("★ 设为默认翻译引擎", self.provider_group)
        self.default_check.setCheckable(True)
        self.default_check.clicked.connect(self._on_set_default_clicked)
        form_layout.addRow("默认引擎:", self.default_check)

        layout.addWidget(self.provider_group)

        # 连通性测试区
        test_group = QGroupBox("网络与连通性测试", widget)
        test_layout = QVBoxLayout(test_group)
        test_layout.setSpacing(8)

        test_btn_layout = QHBoxLayout()
        self.test_btn = QPushButton("⚡ 测试当前服务连通性", test_group)
        self.test_btn.clicked.connect(self._on_test_connection_clicked)
        test_btn_layout.addWidget(self.test_btn)
        test_btn_layout.addStretch()
        test_layout.addLayout(test_btn_layout)

        self.test_status_label = QLabel("", test_group)
        self.test_status_label.setWordWrap(True)
        self.test_status_label.setStyleSheet("font-size: 12px; color: #57606a;")
        test_layout.addWidget(self.test_status_label)

        layout.addWidget(test_group)
        layout.addStretch()

        # 加载当前服务商数据
        self._load_provider_fields(self.current_provider_name)
        self.key_edit.textEdited.connect(lambda text: self._save_current_provider_fields())
        self.url_edit.textEdited.connect(lambda text: self._save_current_provider_fields())
        return widget

    def _toggle_key_echo(self) -> None:
        if self.key_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.eye_btn.setText("🔒")
        else:
            self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.eye_btn.setText("👁")

    def _load_provider_fields(self, provider_name: str) -> None:
        p_cfg = self.working_config.providers.get(provider_name)
        if not p_cfg:
            return

        self.key_edit.setText(p_cfg.api_key)
        self.model_edit.setText(p_cfg.model)
        self.url_edit.setText(p_cfg.base_url)

        is_default = (self.working_config.default_provider == provider_name)
        self._update_default_button_state(is_default)

        # 友好说明提示
        if provider_name == "microsoft":
            self.provider_hint_label.setText(
                "💡 微软翻译默认采用官方免 Key 免费通道，开箱即用；如需使用 Azure 官方认知服务专线，可在此输入 Azure Key。"
            )
            self.provider_hint_label.show()
        elif provider_name == "custom":
            self.provider_hint_label.setText(
                "💡 自定义服务适用于本地 Ollama 或私有部署的 OpenAI 规范接口（如 http://localhost:11434/v1）。"
            )
            self.provider_hint_label.show()
        else:
            self.provider_hint_label.hide()

        self.test_status_label.setText("")

    def _save_current_provider_fields(self) -> None:
        """将当前表单内容暂存到 working_config"""
        p_name = self.current_provider_name
        if p_name in self.working_config.providers:
            p_cfg = self.working_config.providers[p_name]
            p_cfg.api_key = self.key_edit.text().strip()
            p_cfg.model = self.model_edit.text().strip()
            p_cfg.base_url = self.url_edit.text().strip()
            index = self.provider_combo.findData(p_name)
            if index >= 0:
                self.provider_combo.setItemText(index, provider_menu_label(p_name, p_cfg))

    def select_provider(self, provider_name: str) -> None:
        self.switch_to_tab(0)
        index = self.provider_combo.findData(provider_name)
        if index >= 0:
            self.provider_combo.setCurrentIndex(index)

    def _on_provider_selection_changed(self, new_provider_name: str) -> None:
        if not new_provider_name or new_provider_name == self.current_provider_name:
            return
        self._save_current_provider_fields()
        self.current_provider_name = new_provider_name
        self._load_provider_fields(new_provider_name)

    def _on_set_default_clicked(self) -> None:
        self._save_current_provider_fields()
        if not is_configured(self.working_config.providers[self.current_provider_name]):
            self._update_default_button_state(self.working_config.default_provider == self.current_provider_name)
            self.test_status_label.setText("请先填写 API 密钥，再设为默认引擎。")
            return
        self.working_config.default_provider = self.current_provider_name
        self._update_default_button_state(True)

    def _update_default_button_state(self, is_default: bool) -> None:
        self.default_check.setChecked(is_default)
        if is_default:
            self.default_check.setText("★ 当前默认翻译引擎")
            self.default_check.setStyleSheet("color: #1a7f37; font-weight: bold;")
        else:
            self.default_check.setText("☆ 设为默认翻译引擎")
            self.default_check.setStyleSheet("color: #57606a;")

    def _on_test_connection_clicked(self) -> None:
        self._save_current_provider_fields()
        p_name = self.current_provider_name
        p_cfg = self.working_config.providers[p_name]

        self.test_btn.setEnabled(False)
        self.test_status_label.setText("⏳ 正在请求 API 连通性测试，请稍候...")
        self.test_status_label.setStyleSheet("color: #0969da; font-size: 12px;")

        def _worker():
            try:
                tr = create_translator(p_cfg)
                ok, msg = tr.test_connection()
                self.signals.finished.emit(ok, msg)
            except Exception as e:
                self.signals.finished.emit(False, str(e))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_test_finished(self, ok: bool, msg: str) -> None:
        self.test_btn.setEnabled(True)
        if ok:
            self.test_status_label.setText(f"✔ {msg}")
            self.test_status_label.setStyleSheet("color: #1a7f37; font-size: 12px; font-weight: bold;")
        else:
            self.test_status_label.setText(f"✖ {msg}")
            self.test_status_label.setStyleSheet("color: #cf222e; font-size: 12px;")

    # ==============================
    # 选项卡 2: 快捷键与取词设置
    # ==============================
    def _create_selection_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # 核心取词行为
        behavior_group = QGroupBox("取词行为", widget)
        b_layout = QVBoxLayout(behavior_group)
        b_layout.setSpacing(8)

        self.mouse_side_check = QCheckBox("启用鼠标侧键划词翻译 (前进/后退侧键)", behavior_group)
        self.mouse_side_check.setChecked(self.working_config.selection.enable_mouse_side_button)
        b_layout.addWidget(self.mouse_side_check)

        b_layout.addWidget(QLabel("取词模式：", behavior_group))
        self.selection_mode_combo = QComboBox(behavior_group)
        for mode, label in MODE_LABELS.items():
            self.selection_mode_combo.addItem(label, mode)
        self.selection_mode_combo.setCurrentIndex(
            self.selection_mode_combo.findData(self.working_config.selection.get_mode())
        )
        b_layout.addWidget(self.selection_mode_combo)
        self.selection_mode_hint = QLabel(behavior_group)
        self.selection_mode_hint.setWordWrap(True)
        self.selection_mode_combo.currentIndexChanged.connect(self._update_selection_mode_hint)
        self._update_selection_mode_hint()
        b_layout.addWidget(self.selection_mode_hint)

        layout.addWidget(behavior_group)

        # 热键配置
        hotkey_group = QGroupBox("全局快捷键", widget)
        h_layout = QVBoxLayout(hotkey_group)
        h_layout.setSpacing(10)

        # 主热键
        main_hotkey_layout = QHBoxLayout()
        main_hotkey_layout.addWidget(QLabel("主取词热键:", hotkey_group))
        self.main_hotkey_edit = QLineEdit(hotkey_group)
        self.main_hotkey_edit.setText(self.working_config.selection.hotkey)
        self.main_hotkey_edit.setPlaceholderText("<alt>+d")
        main_hotkey_layout.addWidget(self.main_hotkey_edit)
        h_layout.addLayout(main_hotkey_layout)

        # 备用热键列表
        h_layout.addWidget(QLabel("备用快捷键列表:", hotkey_group))
        self.extra_hotkeys_list = QListWidget(hotkey_group)
        self.extra_hotkeys_list.setMaximumHeight(80)
        for hk in self.working_config.selection.extra_hotkeys:
            self.extra_hotkeys_list.addItem(hk)
        h_layout.addWidget(self.extra_hotkeys_list)

        extra_btn_layout = QHBoxLayout()
        self.new_hotkey_edit = QLineEdit(hotkey_group)
        self.new_hotkey_edit.setPlaceholderText("如 <alt>+q")
        self.add_hotkey_btn = QPushButton("添加快捷键", hotkey_group)
        self.add_hotkey_btn.clicked.connect(self._on_add_extra_hotkey)

        self.del_hotkey_btn = QPushButton("删除选中", hotkey_group)
        self.del_hotkey_btn.clicked.connect(self._on_del_extra_hotkey)

        extra_btn_layout.addWidget(self.new_hotkey_edit)
        extra_btn_layout.addWidget(self.add_hotkey_btn)
        extra_btn_layout.addWidget(self.del_hotkey_btn)
        h_layout.addLayout(extra_btn_layout)

        layout.addWidget(hotkey_group)

        # 限制条件
        limits_group = QGroupBox("字符限制", widget)
        l_layout = QFormLayout(limits_group)
        self.min_len_spin = QSpinBox(limits_group)
        self.min_len_spin.setRange(1, 100)
        self.min_len_spin.setValue(self.working_config.selection.min_length)
        l_layout.addRow("最小有效取词字符数:", self.min_len_spin)

        self.max_len_spin = QSpinBox(limits_group)
        self.max_len_spin.setRange(100, 10000)
        self.max_len_spin.setSingleStep(500)
        self.max_len_spin.setValue(self.working_config.selection.max_length)
        l_layout.addRow("最大有效取词字符数:", self.max_len_spin)
        layout.addWidget(limits_group)

        layout.addStretch()
        return widget

    def _update_selection_mode_hint(self) -> None:
        self.selection_mode_hint.setText(MODE_DESCRIPTIONS[self.selection_mode_combo.currentData()])

    def _on_add_extra_hotkey(self) -> None:
        text = self.new_hotkey_edit.text().strip()
        if not text:
            return
        if not (text.startswith("<") and text.endswith(">")) and "+" in text:
            # 自动规整如 alt+q -> <alt>+q
            parts = [f"<{p.lower()}>" if not p.startswith("<") else p.lower() for p in text.split("+")]
            text = "+".join(parts)
        self.extra_hotkeys_list.addItem(text)
        self.new_hotkey_edit.clear()

    def _on_del_extra_hotkey(self) -> None:
        item = self.extra_hotkeys_list.currentItem()
        if item:
            self.extra_hotkeys_list.takeItem(self.extra_hotkeys_list.row(item))

    # ==============================
    # 选项卡 3: 外观与交互设置
    # ==============================
    def _create_ui_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        ui_group = QGroupBox("悬浮窗样式与视觉", widget)
        form_layout = QFormLayout(ui_group)
        form_layout.setContentsMargins(12, 16, 12, 16)
        form_layout.setSpacing(12)

        # 主题风格
        self.theme_combo = QComboBox(ui_group)
        for code, label in AVAILABLE_THEMES:
            self.theme_combo.addItem(label, code)
        curr_theme = getattr(self.working_config.ui, "theme", "auto")
        idx = self.theme_combo.findData(curr_theme)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)
        form_layout.addRow("界面主题:", self.theme_combo)

        # 透明度调节
        op_layout = QHBoxLayout()
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal, ui_group)
        self.opacity_slider.setRange(40, 100)
        curr_op = int(getattr(self.working_config.ui, "window_opacity", 0.95) * 100)
        self.opacity_slider.setValue(curr_op)

        self.opacity_label = QLabel(f"{curr_op}%", ui_group)
        self.opacity_label.setFixedWidth(36)
        self.opacity_slider.valueChanged.connect(lambda v: self.opacity_label.setText(f"{v}%"))

        op_layout.addWidget(self.opacity_slider)
        op_layout.addWidget(self.opacity_label)
        form_layout.addRow("窗口透明度:", op_layout)

        # 自动收起秒数
        self.auto_hide_spin = QSpinBox(ui_group)
        self.auto_hide_spin.setRange(0, 60)
        self.auto_hide_spin.setSuffix(" 秒 (0 表示不自动收起)")
        self.auto_hide_spin.setValue(getattr(self.working_config.ui, "auto_hide_seconds", 8))
        form_layout.addRow("自动收起等待:", self.auto_hide_spin)

        # 启动时自动展示悬浮窗
        self.open_on_startup_check = QCheckBox("启动应用时自动展示悬浮窗", ui_group)
        self.open_on_startup_check.setChecked(getattr(self.working_config.ui, "open_on_startup", True))
        form_layout.addRow("启动行为:", self.open_on_startup_check)

        self.auto_translate_input_check = QCheckBox("输入后自动翻译（停顿 600 毫秒）", ui_group)
        self.auto_translate_input_check.setChecked(self.working_config.ui.auto_translate_input)
        self.auto_translate_input_check.setToolTip("关闭后，按回车或点击翻译提交；划词与快捷键取词不受影响。")
        form_layout.addRow("手动输入:", self.auto_translate_input_check)

        layout.addWidget(ui_group)
        layout.addStretch()
        return widget

    # ==============================
    # 选项卡 4: 软件更新与关于
    # ==============================
    def _create_about_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # 顶部品牌横幅 (Logo + 名称 + 版本)
        banner_layout = QHBoxLayout()
        logo_label = QLabel(widget)
        icon_path = find_icon_path()
        if icon_path:
            logo_pix = QPixmap(str(icon_path)).scaled(
                52, 52, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            logo_label.setPixmap(logo_pix)
        banner_layout.addWidget(logo_label)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)
        app_name_label = QLabel("言蹊翻译 (YanXi Trans)", widget)
        app_name_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #1f2328;")
        self.ver_label = QLabel(f"当前版本: v{yanxi.__version__} · 轻量桌面划词翻译工具", widget)
        self.ver_label.setStyleSheet("font-size: 12px; color: #57606a;")
        title_layout.addWidget(app_name_label)
        title_layout.addWidget(self.ver_label)
        banner_layout.addLayout(title_layout)
        banner_layout.addStretch()
        layout.addLayout(banner_layout)

        # 在线版本更新分组框
        self.update_group = QGroupBox("在线版本更新", widget)
        up_layout = QVBoxLayout(self.update_group)
        up_layout.setContentsMargins(12, 14, 12, 14)
        up_layout.setSpacing(10)

        # 状态指示与检查按钮
        status_bar = QHBoxLayout()
        self.update_status_label = QLabel("可点击右侧按钮检测 GitHub 最新发布版本", self.update_group)
        self.update_status_label.setStyleSheet("font-size: 12px; color: #24292f;")
        self.check_update_btn = QPushButton("🔍 检查更新", self.update_group)
        self.check_update_btn.clicked.connect(self._check_update_async)
        status_bar.addWidget(self.update_status_label)
        status_bar.addStretch()
        status_bar.addWidget(self.check_update_btn)
        up_layout.addLayout(status_bar)

        # 更新日志展示区
        self.release_notes_edit = QTextEdit(self.update_group)
        self.release_notes_edit.setReadOnly(True)
        self.release_notes_edit.setPlaceholderText("检查更新后将在此处展示最新版本的更新说明与改进日志...")
        self.release_notes_edit.setMaximumHeight(110)
        self.release_notes_edit.setStyleSheet(
            "background-color: #f6f8fa; border: 1px solid #d0d7de; font-size: 12px; color: #24292f;"
        )
        up_layout.addWidget(self.release_notes_edit)

        # 前往下载按钮与自动检查选项
        action_bar = QHBoxLayout()
        self.auto_update_check = QCheckBox("启动应用时自动在后台检查更新", self.update_group)
        self.auto_update_check.setChecked(self.working_config.update.auto_check_update)

        self.download_btn = QPushButton("⚡ 前往下载最新版", self.update_group)
        self.download_btn.setEnabled(False)
        self.download_btn.clicked.connect(self._on_download_clicked)

        action_bar.addWidget(self.auto_update_check)
        action_bar.addStretch()
        action_bar.addWidget(self.download_btn)
        up_layout.addLayout(action_bar)

        layout.addWidget(self.update_group)

        # 开源与项目信息
        about_group = QGroupBox("开源主页与协议", widget)
        ab_layout = QVBoxLayout(about_group)
        ab_layout.setContentsMargins(12, 12, 12, 12)
        ab_layout.setSpacing(6)

        repo_link = QLabel(
            '<a href="https://github.com/Leonherben/yanxi-trans" style="color: #0969da; text-decoration: none;">'
            '👉 GitHub 仓库: https://github.com/Leonherben/yanxi-trans</a>',
            about_group,
        )
        repo_link.setOpenExternalLinks(True)
        ab_layout.addWidget(repo_link)

        desc_label = QLabel("名称取自“桃李不言，下自成蹊”。支持 Windows (x86_64) 与 Linux (X11)。采用 MIT 开源协议。", about_group)
        desc_label.setStyleSheet("font-size: 12px; color: #57606a;")
        ab_layout.addWidget(desc_label)

        layout.addWidget(about_group)
        layout.addStretch()
        return widget

    def _check_update_async(self) -> None:
        """异步拉取 GitHub 最新版本发布信息"""
        self.check_update_btn.setEnabled(False)
        self.check_update_btn.setText("⏳ 正在检查...")
        self.update_status_label.setText("正在连接 GitHub 获取最新版本信息...")

        def _worker():
            info = check_github_update()
            self.update_signals.finished.emit(info)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def _on_update_result(self, info: UpdateInfo) -> None:
        """接收后台更新检测结果并渲染界面"""
        self.check_update_btn.setEnabled(True)
        self.check_update_btn.setText("🔍 检查更新")
        self.latest_update_info = info

        if info.error_message:
            self.update_status_label.setText(f"❌ {info.error_message}")
            self.download_btn.setEnabled(False)
            return

        if info.has_update:
            self.update_status_label.setText(f"🎉 发现新版本: v{info.latest_version} (发布于 {info.published_at})")
            self.release_notes_edit.setPlainText(info.release_notes)
            self.download_btn.setEnabled(True)
            self.download_btn.setText(f"⚡ 下载 v{info.latest_version}")
        else:
            self.update_status_label.setText(f"✅ 当前已是最新版本 (v{info.current_version})")
            if info.release_notes:
                self.release_notes_edit.setPlainText(f"当前最新版本说明:\n{info.release_notes}")
            self.download_btn.setEnabled(False)

    def _on_download_clicked(self) -> None:
        """点击下载按钮在系统浏览器中打开更新包下载或 Release 页面"""
        if self.latest_update_info:
            open_release_page(self.latest_update_info)

    # ==============================
    # 保存与样式
    # ==============================
    def _on_save_clicked(self) -> None:
        self._save_current_provider_fields()

        # 收集取词配置
        sel = self.working_config.selection
        sel.enable_mouse_side_button = self.mouse_side_check.isChecked()
        sel.set_mode(self.selection_mode_combo.currentData())
        sel.hotkey = self.main_hotkey_edit.text().strip() or "<alt>+d"
        extra = []
        for i in range(self.extra_hotkeys_list.count()):
            extra.append(self.extra_hotkeys_list.item(i).text())
        sel.extra_hotkeys = extra
        sel.min_length = self.min_len_spin.value()
        sel.max_length = self.max_len_spin.value()

        # 收集界面配置
        ui = self.working_config.ui
        ui.theme = self.theme_combo.currentData()
        ui.window_opacity = round(self.opacity_slider.value() / 100.0, 2)
        ui.auto_hide_seconds = self.auto_hide_spin.value()
        ui.open_on_startup = self.open_on_startup_check.isChecked()
        ui.auto_translate_input = self.auto_translate_input_check.isChecked()

        # 收集更新配置
        self.working_config.update.auto_check_update = self.auto_update_check.isChecked()

        # 写回原始 config 并保存到磁盘
        self.config.default_provider = self.working_config.default_provider
        self.config.providers = self.working_config.providers
        self.config.selection = self.working_config.selection
        self.config.ui = self.working_config.ui
        self.config.update = self.working_config.update
        self.config.save()

        if self.on_save:
            self.on_save(self.config)

        self.accept()

    def switch_to_tab(self, index: int) -> None:
        """切换至指定选项卡 (0: 服务商, 1: 快捷键, 2: 外观, 3: 更新与关于)"""
        if 0 <= index < self.tab_widget.count():
            self.tab_widget.setCurrentIndex(index)

    def trigger_check_update(self) -> None:
        """从外部调用主动切换至更新选项卡并触发检查"""
        self.switch_to_tab(3)
        self._check_update_async()

    def _apply_dialog_style(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background-color: #f6f8fa;
            }
            QTabWidget::pane {
                border: 1px solid #d0d7de;
                border-radius: 6px;
                background-color: #ffffff;
                top: -1px;
            }
            QTabBar::tab {
                background-color: #eaeef2;
                border: 1px solid #d0d7de;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 6px 14px;
                margin-right: 2px;
                font-size: 13px;
                color: #24292f;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                font-weight: bold;
                border-bottom: 1px solid #ffffff;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #d0d7de;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 4px;
                color: #24292f;
            }
            QLineEdit, QComboBox, QSpinBox {
                border: 1px solid #d0d7de;
                border-radius: 4px;
                padding: 4px 8px;
                background-color: #ffffff;
                color: #24292f;
                font-size: 12px;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                border: 1px solid #0969da;
            }
            QPushButton {
                border: 1px solid #d0d7de;
                border-radius: 4px;
                padding: 5px 12px;
                background-color: #f6f8fa;
                color: #24292f;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #f3f4f6;
                border-color: #0969da;
            }
            QPushButton:default {
                background-color: #1f6feb;
                color: #ffffff;
                border-color: #1f6feb;
                font-weight: bold;
            }
            QPushButton:default:hover {
                background-color: #388bfd;
            }
        """)
