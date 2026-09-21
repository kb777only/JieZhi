"""One spacing scale, one type scale, one radius scale, one control height.

Every screen snaps to the values below. Nothing in the app should introduce a
number that is not here: a bespoke margin on one page is what made the window
read as nine unrelated layouts instead of one.

The palette is a pair of token tables rather than the hex-substitution pass it
replaced, so a colour added to the stylesheet can no longer stay light when the
window turns dark.
"""
from __future__ import annotations

from pathlib import Path

from .client import CACHE

# Spacing. Gutters and gaps come from here and nowhere else.
XS, SM, MD, LG, XL, XXL = 4, 8, 12, 16, 24, 32

# Type. Point sizes are avoided; the whole app is set in pixels.
LABEL, CAPTION, SMALL, BODY, HEADING, TITLE = 11, 12, 13, 14, 16, 22

# Radius. Controls, inputs and the panels that hold them.
R_CONTROL, R_INPUT, R_PANEL = 6, 10, 14

# One height for buttons, combo boxes, spin boxes and single-line fields.
CONTROL = 32

SIDEBAR = 224

LIGHT = {
    'ground': '#eef1f6',
    'panel': '#e4e9f3',
    'surface': '#ffffff',
    'surface_alt': '#f4f6fb',
    'line': '#dce1ec',
    'line_strong': '#c6cede',
    'ink': '#1b2331',
    'ink_2': '#4d5768',
    'ink_3': '#7a8596',
    'accent': '#3a5fe0',
    'accent_hover': '#3053d2',
    'accent_press': '#2946b8',
    'on_accent': '#ffffff',
    'accent_text': '#2f55d4',
    'accent_soft': '#e6ebfb',
    'accent_line': '#bdcbf3',
    'danger': '#bd4630',
    'danger_soft': '#fae9e4',
    'ok': '#1f7a63',
    'ok_soft': '#e1efeb',
    'warn': '#9a6413',
    'disabled': '#e9ecf3',
    'disabled_ink': '#a5adbd',
    'selection': '#d5e0fb',
    'scroll': '#c2cbdd',
    'shadow_line': '#e7ebf4',
}

DARK = {
    'ground': '#10141d',
    'panel': '#171d28',
    'surface': '#1b2230',
    'surface_alt': '#222a39',
    'line': '#2c3547',
    'line_strong': '#3b4659',
    'ink': '#e7ecf5',
    'ink_2': '#aab4c6',
    'ink_3': '#7f8a9e',
    'accent': '#4d70ea',
    'accent_hover': '#5b7cf0',
    'accent_press': '#3f60d4',
    'on_accent': '#ffffff',
    'accent_text': '#93aaff',
    'accent_soft': '#202b47',
    'accent_line': '#3b4d7d',
    'danger': '#e08a72',
    'danger_soft': '#33211d',
    'ok': '#79c9b0',
    'ok_soft': '#16291f',
    'warn': '#d3a25c',
    'disabled': '#1d2432',
    'disabled_ink': '#5c6679',
    'selection': '#2b3c62',
    'scroll': '#38435a',
    'shadow_line': '#222a39',
}


def tokens(dark: bool) -> dict:
    return DARK if dark else LIGHT


def _icon(name: str, body: str) -> str:
    """Write a themed glyph next to the cache and hand back a stylesheet url.

    Qt cannot recolour an svg through a stylesheet, so each arrow and tick is
    written once per colour. Paths are quoted for stylesheet parsing.
    """
    directory = CACHE / 'icons'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{name}.svg'
    if not path.exists():
        path.write_text(body, encoding='utf-8')
    return 'url("' + str(path).replace('\\', '/') + '")'


def _chevron(color: str, up: bool = False) -> str:
    points = '3,7.5 7,3.5 11,7.5' if up else '3,4.5 7,8.5 11,4.5'
    return _icon(
        ('chevron-up-' if up else 'chevron-down-') + color.lstrip('#'),
        f'<svg xmlns="http://www.w3.org/2000/svg" width="14" height="12" viewBox="0 0 14 12">'
        f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="1.6" '
        f'stroke-linecap="round" stroke-linejoin="round"/></svg>',
    )


def _tick(color: str) -> str:
    return _icon(
        'tick-' + color.lstrip('#'),
        f'<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14">'
        f'<polyline points="3,7.4 5.9,10.2 11,4.2" fill="none" stroke="{color}" stroke-width="1.9" '
        f'stroke-linecap="round" stroke-linejoin="round"/></svg>',
    )


def stylesheet(dark: bool = False) -> str:
    t = dict(tokens(dark))
    t.update(
        xs=XS, sm=SM, md=MD, lg=LG, xl=XL, control=CONTROL,
        label=LABEL, caption=CAPTION, small=SMALL, body=BODY, heading=HEADING, title=TITLE,
        r_control=R_CONTROL, r_input=R_INPUT, r_panel=R_PANEL,
        chevron=_chevron(t['ink_2']), chevron_up=_chevron(t['ink_2'], up=True),
        chevron_off=_chevron(t['disabled_ink']), tick=_tick(t['on_accent']),
    )
    return TEMPLATE.format(**t)


TEMPLATE = """
QWidget {{ background: {ground}; color: {ink}; font-size: {body}px; font-family: "Noto Sans", "Inter", sans-serif; }}
QMainWindow, QDialog {{ background: {ground}; }}
QLabel {{ background: transparent; color: {ink}; }}

/* Type scale. Every label in the app carries one of these object names. */
QLabel#brand {{ color: {accent_text}; font-size: 20px; font-weight: 700; }}
QLabel#title {{ font-size: {title}px; font-weight: 700; color: {ink}; }}
QLabel#subtitle {{ font-size: {small}px; color: {ink_2}; }}
QLabel#muted {{ color: {ink_3}; font-size: {caption}px; }}
QLabel#section {{ color: {ink_3}; font-size: {label}px; font-weight: 600; letter-spacing: 1px; }}
QLabel#fine {{ color: {ink_3}; font-size: {label}px; }}
QLabel#badge {{ color: {accent_text}; background: {accent_soft}; border: 1px solid {accent_line};
  border-radius: {r_control}px; padding: 6px {md}px; font-size: {small}px; }}
QLabel#empty {{ color: {ink_3}; font-size: {small}px; padding: {lg}px {md}px; }}
QLabel#status {{ color: {ink_2}; font-size: {small}px; }}
QLabel#strong {{ color: {ink}; font-size: {body}px; font-weight: 600; }}
QLabel#metric {{ color: {ink}; font-size: {heading}px; font-weight: 600; }}

/* Panels. Three surfaces, no more: the window, a panel, a card. */
QWidget#sidebar {{ background: {panel}; border-radius: {r_panel}px; }}
QWidget#card {{ background: {surface}; border: 1px solid {line}; border-radius: {r_input}px; }}
QWidget#band {{ background: transparent; }}
QFrame#rule {{ background: {line}; border: 0; max-height: 1px; min-height: 1px; }}

/* Buttons. One height, one radius, one primary per row. */
QPushButton {{ background: {surface}; color: {ink}; border: 1px solid {line_strong};
  border-radius: {r_control}px; padding: 0 {md}px; min-height: {control}px; font-size: {small}px; font-weight: 500; }}
QPushButton:hover {{ background: {accent_soft}; border-color: {accent_line}; }}
QPushButton:pressed {{ background: {selection}; }}
QPushButton:disabled {{ color: {disabled_ink}; background: {disabled}; border-color: {line}; }}
QPushButton#primary {{ background: {accent}; color: {on_accent}; border-color: {accent}; font-weight: 600; }}
QPushButton#primary:hover {{ background: {accent_hover}; border-color: {accent_hover}; }}
QPushButton#primary:pressed {{ background: {accent_press}; border-color: {accent_press}; }}
QPushButton#primary:disabled {{ background: {disabled}; color: {disabled_ink}; border-color: {line}; }}
QPushButton#quiet {{ background: transparent; border-color: transparent; color: {ink_2}; }}
QPushButton#quiet:hover {{ background: {accent_soft}; color: {accent_text}; }}
QPushButton#danger {{ color: {danger}; }}
QPushButton#danger:hover {{ background: {danger_soft}; border-color: {danger}; }}
QPushButton#corner {{ font-size: {heading}px; padding: 0; min-width: {control}px; max-width: {control}px;
  min-height: {control}px; max-height: {control}px; }}

/* Lists. The row is the object; selection colours the row, not the text alone. */
QListWidget {{ background: {surface}; border: 1px solid {line}; border-radius: {r_input}px;
  padding: {xs}px; outline: none; }}
QListWidget::item {{ padding: {sm}px {md}px; border-radius: {r_control}px; margin: 1px; color: {ink}; }}
QListWidget::item:hover {{ background: {surface_alt}; }}
QListWidget::item:selected {{ background: {accent_soft}; color: {accent_text}; }}
QListWidget#navigation {{ background: transparent; border: 0; padding: 0; font-size: {body}px; }}
QListWidget#navigation::item {{ padding: {sm}px {md}px; margin: 1px 0; color: {ink_2}; }}
QListWidget#navigation::item:hover {{ background: {accent_soft}; color: {ink}; }}
QListWidget#navigation::item:selected {{ background: {surface}; color: {accent_text}; font-weight: 600; }}
QListWidget#plain {{ background: transparent; border: 0; padding: 0; }}

/* Text surfaces. */
QTextBrowser, QPlainTextEdit, QLineEdit {{ background: {surface}; border: 1px solid {line};
  border-radius: {r_input}px; padding: {sm}px {md}px; color: {ink};
  selection-background-color: {selection}; selection-color: {ink}; }}
QTextBrowser {{ padding: {lg}px; }}
QLineEdit {{ min-height: {control}px; border-radius: {r_control}px; }}
QPlainTextEdit:focus, QLineEdit:focus, QTextBrowser:focus {{ border-color: {accent}; }}
QPlainTextEdit#flat, QTextBrowser#flat, QLineEdit#flat {{ border: 0; background: transparent; padding: 0; }}
QPlainTextEdit#console {{ background: {surface_alt}; font-family: "Noto Sans Mono", monospace;
  font-size: {small}px; color: {ink_2}; }}

/* Pickers. The arrows are drawn rather than left to the platform style. */
QComboBox, QSpinBox, QDoubleSpinBox {{ background: {surface}; color: {ink}; border: 1px solid {line_strong};
  border-radius: {r_control}px; padding: 0 {sm}px; min-height: {control}px; font-size: {small}px; }}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: {accent_line}; }}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {accent}; }}
QComboBox:disabled, QSpinBox:disabled {{ background: {disabled}; color: {disabled_ink}; border-color: {line}; }}
QComboBox::drop-down {{ border: 0; width: {lg}px; }}
QComboBox::down-arrow {{ image: {chevron}; width: 14px; height: 12px; }}
QComboBox::down-arrow:disabled {{ image: {chevron_off}; }}
QComboBox QAbstractItemView {{ background: {surface}; border: 1px solid {line}; border-radius: {r_control}px;
  padding: {xs}px; selection-background-color: {accent_soft}; selection-color: {accent_text}; outline: none; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right;
  width: {lg}px; border: 0; border-top-right-radius: {r_control}px; margin: 1px 1px 0 0; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right;
  width: {lg}px; border: 0; border-bottom-right-radius: {r_control}px; margin: 0 1px 1px 0; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {accent_soft}; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: {chevron_up}; width: 14px; height: 12px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: {chevron}; width: 14px; height: 12px; }}

/* Check boxes. The global QWidget rule routes these through the stylesheet
   engine, which draws no indicator of its own unless one is declared here. */
QCheckBox {{ background: transparent; color: {ink}; spacing: {sm}px; font-size: {small}px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {line_strong};
  border-radius: {xs}px; background: {surface}; }}
QCheckBox::indicator:hover {{ border-color: {accent}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; image: {tick}; }}
QCheckBox::indicator:disabled {{ background: {disabled}; border-color: {line}; }}
QRadioButton {{ background: transparent; color: {ink}; spacing: {sm}px; font-size: {small}px; }}
QRadioButton::indicator {{ width: 16px; height: 16px; border: 1px solid {line_strong};
  border-radius: 9px; background: {surface}; }}
QRadioButton::indicator:checked {{ background: {accent}; border: 5px solid {surface};
  outline: 1px solid {accent}; }}

/* Grouping. The title sits on the rule, not floating above a second border. */
QGroupBox {{ background: {surface}; border: 1px solid {line}; border-radius: {r_input}px;
  margin-top: {md}px; padding: {xl}px {lg}px {lg}px; font-size: {small}px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: {lg}px;
  padding: 0 {sm}px; color: {ink_2}; }}

QProgressBar {{ min-height: 6px; max-height: 6px; border: 0; border-radius: 3px;
  background: {line}; text-align: center; font-size: {label}px; color: transparent; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 3px; }}

QStatusBar {{ background: {ground}; color: {ink_3}; font-size: {caption}px; padding: {xs}px {lg}px; }}
QStatusBar::item {{ border: 0; }}

QScrollBar:vertical {{ width: {sm}px; background: transparent; margin: {xs}px 0; }}
QScrollBar::handle:vertical {{ background: {scroll}; min-height: {xl}px; border-radius: {xs}px; }}
QScrollBar::handle:vertical:hover {{ background: {ink_3}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ height: {sm}px; background: transparent; margin: 0 {xs}px; }}
QScrollBar::handle:horizontal {{ background: {scroll}; min-width: {xl}px; border-radius: {xs}px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QSplitter::handle {{ background: transparent; width: {lg}px; }}
QScrollArea {{ background: transparent; border: 0; }}
QGraphicsView {{ border: 1px solid {line}; border-radius: {r_input}px; }}
QTabWidget::pane {{ border: 0; }}
QToolTip {{ color: {ink}; background: {surface}; border: 1px solid {line}; border-radius: {r_control}px;
  padding: {sm}px {md}px; font-size: {caption}px; }}
QMenu {{ background: {surface}; border: 1px solid {line}; border-radius: {r_control}px; padding: {xs}px; }}
QMenu::item {{ padding: {sm}px {md}px; border-radius: {xs}px; }}
QMenu::item:selected {{ background: {accent_soft}; color: {accent_text}; }}
"""
