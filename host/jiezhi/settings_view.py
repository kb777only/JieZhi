from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QGroupBox,QCheckBox,QComboBox,QScrollArea,QSpinBox
from .client import save_json
from .theme import stylesheet, LG

class SettingsView:
    def build_settings(self):
        from .gui import label,button,row,wide
        layout=self.page('Make yourself at home.', 'Your appearance, connections and defaults, in one place.')
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body=QWidget();col=QVBoxLayout(body);col.setContentsMargins(0,0,LG,LG);col.setSpacing(LG)
        box=QGroupBox('Appearance && workspace');form=QVBoxLayout(box)
        self.theme_choice=QComboBox();self.theme_choice.addItems(['Light','Dark']);self.theme_choice.setFixedWidth(144);self.theme_choice.setCurrentIndex(int(self.preferences.get('dark',False)))
        form.addLayout(row(label('Color theme','muted'),self.theme_choice,spacing=12))
        self.motion_choice=QCheckBox('Fluid gradient animations');self.motion_choice.setChecked(self.preferences.get('motion',True));form.addWidget(self.motion_choice)
        self.telemetry_choice=QCheckBox('Show live phone telemetry on every page');self.telemetry_choice.setChecked(self.preferences.get('telemetry',True));form.addWidget(self.telemetry_choice)
        form.addWidget(label('Turning telemetry off also stops background sensor polling. Reduced motion keeps the gradients still and opens the selection chip, its menu and its results instantly.','fine',True));col.addWidget(box)
        box=QGroupBox('Hugging Face account');form=QVBoxLayout(box);form.addWidget(label('Public model discovery works without an account. Sign in with a read token for your private or gated models.','fine',True));self.settings_account_label=label(self.account_label.text(),'status',True);form.addWidget(self.settings_account_label);form.addWidget(self.hub_account_panel);self.hub_account_panel.show();col.addWidget(box)
        self.build_desktop_settings(col)
        self.build_update_settings(col)
        box=QGroupBox('Phone && generation defaults');form=QVBoxLayout(box)
        self.auto_connect_choice=QCheckBox('Reconnect a previously paired USB phone on launch');self.auto_connect_choice.setChecked(self.preferences.get('auto_connect',True));form.addWidget(self.auto_connect_choice)
        self.default_context=QSpinBox();self.default_context.setFixedWidth(120);self.default_context.setRange(512,8192);self.default_context.setSingleStep(512);self.default_context.setValue(self.preferences.get('context',2048))
        form.addLayout(row(label('Default model context','muted'),self.default_context,spacing=12))
        form.addWidget(label('Defaults apply to the next model load. Active inference is unchanged. PC Assistant access controls remain beside its Start button so permissions are always visible.','fine',True))
        form.addLayout(row(button('Device setup',lambda:self.nav.setCurrentRow(2)),button('PC Assistant permissions',lambda:self.nav.setCurrentRow(6)),button('Runtime diagnostics',lambda:self.nav.setCurrentRow(3))));col.addWidget(box)
        col.addStretch();scroll.setWidget(body);layout.addWidget(scroll,1)
        self.theme_choice.currentIndexChanged.connect(self.settings_changed)
        self.motion_choice.toggled.connect(self.settings_changed);self.telemetry_choice.toggled.connect(self.settings_changed)
        self.auto_connect_choice.toggled.connect(self.settings_changed);self.default_context.valueChanged.connect(self.settings_changed)
        self.settings_index=self.pages.count()-1
    def open_settings(self):
        self.nav.setCurrentRow(self.settings_index)
    def settings_changed(self):
        self.preferences.update(dark=bool(self.theme_choice.currentIndex()),motion=self.motion_choice.isChecked(),telemetry=self.telemetry_choice.isChecked(),auto_connect=self.auto_connect_choice.isChecked(),context=self.default_context.value())
        save_json(self.preferences_path,self.preferences);self.context.setValue(self.preferences['context']);self.apply_appearance()
    def toggle_dark(self):self.theme_choice.setCurrentIndex(0 if self.theme_choice.currentIndex() else 1)
    def apply_appearance(self):
        self.context.setValue(self.preferences.get('context',2048))
        self.dark=self.preferences.get('dark',False);self.setStyleSheet(stylesheet(self.dark))
        self.theme_button.setText('☀' if self.dark else '☾');self.theme_button.setToolTip('Switch to light mode' if self.dark else 'Switch to dark mode')
        self.nav.recolour(self.dark);self.welcome_art.configure(self.dark,self.preferences.get('motion',True))
        visible=self.preferences.get('telemetry',True);self.telemetry_panel.setVisible(visible)
        if visible:self.telemetry_panel.timer.start()
        else:self.telemetry_panel.timer.stop()
        self.telemetry_panel.set_theme(self.dark)
        if hasattr(self,'desktop_popup'):self.desktop_popup.configure()
        if hasattr(self,'restyle_updates'):self.restyle_updates()
        if hasattr(self,'flow_canvas'):self.flow_canvas.set_theme(self.dark)
        self.render_chat();self.hub_repos.viewport().update();self.hub_files.viewport().update()
