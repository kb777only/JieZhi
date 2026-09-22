"""One spacing scale, one type scale, one radius scale, one control height.

Every screen snaps to the values below. Nothing in the app should introduce a
number that is not here: a bespoke margin on one page is what made the window
read as nine unrelated layouts instead of one.

Every number in this file is 3, 4 or 6, or a multiple of them. The scales were
rebuilt on that footing, so 16 and 32 are gone and the ladders climb in sixes
and twelves instead of doubling. That includes the lines: no rule in
the sheet draws a single-pixel hairline. A panel is told apart from the window by its fill, and a
control carries a 3px edge that is already there when it is at rest, so
focusing it recolours that edge rather than adding one and shifting the text.

The palette is a pair of token tables rather than the hex-substitution pass it
replaced, so a colour added to the stylesheet can no longer stay light when the
window turns dark.
"""
from __future__ import annotations

from pathlib import Path

from .client import CACHE

# Spacing. Gutters and gaps come from here and nowhere else. Six steps: the
# two seeds, then fours and sixes of them.
XS, SM, MD, LG, XL, XXL = 4, 6, 12, 18, 24, 36

# Type. Point sizes are avoided; the whole app is set in pixels. Four sizes,
# every one of them a multiple of three: fine print, body, heading, title.
LABEL, CAPTION, SMALL, BODY, HEADING, TITLE = 12, 12, 15, 15, 18, 24

# Radius. Controls, inputs and the panels that hold them, climbing in sixes.
R_CONTROL, R_INPUT, R_PANEL = 6, 12, 18

# One height for buttons, combo boxes, spin boxes and single-line fields.
CONTROL = 36

SIDEBAR = 240

# Motion. Three durations and one distance, so the whole app moves in one
# language. Anything that opens under the pointer uses QUICK; anything the
# window does to itself uses BASE; only a whole page gets SLOW.
QUICK, BASE, SLOW = 96, 144, 216
RISE = 12

# The palette runs blue, then purple, then red, then pink, in that order of
# priority, and it is the whole palette: there is no white, no black and no
# neutral grey anywhere in the app. Every surface, every line and every piece
# of text is a tint or a shade of one of these four hues, so light mode is a
# pale blue-violet room and dark mode a deep one. Blue carries every action
# and every selection; purple is the second voice and shades what the app
# itself is doing; red stays semantic and means destructive or hot; pink is
# the smallest touch, for things worth noticing that are not actions.
LIGHT = {
    'ground': '#dde3f9',
    'panel': '#ccd5f4',
    'surface': '#ece9fb',
    'surface_alt': '#e0dcf7',
    'line': '#c3c9ee',
    'line_strong': '#a9b2e4',
    'ink': '#241a4a',
    'ink_2': '#4a4180',
    'ink_3': '#6f68a3',

    # 1 · blue
    'accent': '#3a5fe0',
    'accent_hover': '#2f52d4',
    'accent_press': '#2643b6',
    'on_accent': '#eef1ff',
    'accent_text': '#2f4fd0',
    'accent_soft': '#d9e0fb',
    'accent_line': '#b3c0f4',

    # 2 · purple
    'violet': '#7a4fd4',
    'violet_text': '#6438c0',
    'violet_soft': '#e6dcfb',
    'violet_line': '#cbb6f3',

    # 3 · red
    'danger': '#d13b3b',
    'danger_text': '#b82f33',
    'danger_soft': '#fadfe0',
    'danger_line': '#f0b9bb',

    # 4 · pink
    'pink': '#cf4b96',
    'pink_text': '#b93a84',
    'pink_soft': '#fbdcee',
    'pink_line': '#f2b8dd',

    'ok': '#2f4fd0',
    'ok_soft': '#d9e0fb',
    'warn': '#b93a84',
    'disabled': '#d5d2ee',
    'disabled_ink': '#918ab8',
    'selection': '#c6d2f8',
    'scroll': '#aeb6e2',
    'shadow_line': '#d5dbf5',
}

DARK = {
    'ground': '#14122b',
    'panel': '#1c1838',
    'surface': '#241f46',
    'surface_alt': '#2c2653',
    'line': '#3b3470',
    'line_strong': '#4e4690',
    'ink': '#e6e3fb',
    'ink_2': '#b3adde',
    'ink_3': '#8a83bd',

    # 1 · blue
    'accent': '#5d7cf5',
    'accent_hover': '#7089f8',
    'accent_press': '#4a68e0',
    'on_accent': '#eef1ff',
    'accent_text': '#9db0ff',
    'accent_soft': '#26305c',
    'accent_line': '#3f4f96',

    # 2 · purple
    'violet': '#9a6ef0',
    'violet_text': '#c3a8ff',
    'violet_soft': '#2d2356',
    'violet_line': '#4d3d8c',

    # 3 · red
    'danger': '#e56066',
    'danger_text': '#f59499',
    'danger_soft': '#45222e',
    'danger_line': '#7a3a44',

    # 4 · pink
    'pink': '#e668b0',
    'pink_text': '#f79fd2',
    'pink_soft': '#3e2040',
    'pink_line': '#77396a',

    'ok': '#9db0ff',
    'ok_soft': '#26305c',
    'warn': '#f79fd2',
    'disabled': '#241f42',
    'disabled_ink': '#6a64a0',
    'selection': '#33407a',
    'scroll': '#453e80',
    'shadow_line': '#2c2653',
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
    points = '3,6.6 6,3.6 9,6.6' if up else '3,4.5 6,7.5 9,4.5'
    return _icon(
        ('chevron-up-' if up else 'chevron-down-') + color.lstrip('#'),
        f'<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
        f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round"/></svg>',
    )


def _tick(color: str) -> str:
    return _icon(
        'tick-' + color.lstrip('#'),
        f'<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
        f'<polyline points="2.7,6.3 5.1,8.7 9.3,3.6" fill="none" stroke="{color}" stroke-width="2" '
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
QLabel#brand {{ color: {accent_text}; font-size: {title}px; font-weight: 600; }}
QLabel#title {{ font-size: {title}px; font-weight: 600; color: {ink}; }}
QLabel#subtitle {{ font-size: {small}px; color: {ink_2}; }}
QLabel#muted {{ color: {ink_3}; font-size: {caption}px; }}
QLabel#section {{ color: {ink_3}; font-size: {label}px; font-weight: 600; letter-spacing: 3px; }}
QLabel#fine {{ color: {ink_3}; font-size: {label}px; }}
QLabel#badge {{ color: {accent_text}; background: {accent_soft}; border: 3px solid {accent_line};
  border-radius: {r_control}px; padding: 6px {md}px; font-size: {small}px; }}
QLabel#empty {{ color: {ink_3}; font-size: {small}px; padding: {lg}px {md}px; }}
QLabel#status {{ color: {ink_2}; font-size: {small}px; }}
QLabel#strong {{ color: {ink}; font-size: {body}px; font-weight: 600; }}
QLabel#metric {{ color: {ink}; font-size: {heading}px; font-weight: 600; }}

/* Panels. Three surfaces, no more: the window, a panel, a card. */
QWidget#sidebar {{ background: {panel}; border-radius: {r_panel}px; }}
QWidget#card {{ background: {surface}; border: 0; border-radius: {r_input}px; }}
/* A panel that floats over the page keeps an edge, since it has no room
   around it to be told apart by fill alone. */
QWidget#toast {{ background: {surface}; border: 3px solid {accent_line};
  border-radius: {r_input}px; }}
QWidget#band {{ background: transparent; }}
QFrame#rule {{ background: {line}; border: 0; max-height: 3px; min-height: 3px; }}

/* Buttons. One height, one radius, one primary per row. */
QPushButton {{ background: {surface}; color: {ink}; border: 3px solid {line_strong};
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
QListWidget {{ background: {surface}; border: 3px solid {line}; border-radius: {r_input}px;
  padding: {xs}px; outline: none; }}
QListWidget::item {{ padding: {sm}px {md}px; border-radius: {r_control}px; margin: 3px; color: {ink}; }}
QListWidget::item:hover {{ background: {surface_alt}; }}
QListWidget::item:selected {{ background: {accent_soft}; color: {accent_text}; }}
QListWidget#navigation {{ background: transparent; border: 0; padding: 0; font-size: {body}px; }}
QListWidget#navigation::item {{ padding: {sm}px {md}px; margin: 3px 0; color: {ink_2}; }}
QListWidget#navigation::item:hover {{ background: {accent_soft}; color: {ink}; }}
QListWidget#navigation::item:selected {{ background: {surface}; color: {accent_text}; font-weight: 600; }}
QListWidget#plain {{ background: transparent; border: 0; padding: 0; }}

/* Text surfaces. */
QTextBrowser, QPlainTextEdit, QLineEdit {{ background: {surface}; border: 3px solid {line};
  border-radius: {r_input}px; padding: {sm}px {md}px; color: {ink};
  selection-background-color: {selection}; selection-color: {ink}; }}
QTextBrowser {{ padding: {lg}px; }}
QLineEdit {{ min-height: {control}px; max-height: {control}px; padding: 0 {md}px;
  border-radius: {r_control}px; }}
QPlainTextEdit:focus, QLineEdit:focus, QTextBrowser:focus {{ border-color: {accent}; }}
QPlainTextEdit#flat, QTextBrowser#flat, QLineEdit#flat {{ border: 0; background: transparent; padding: 0; }}
QPlainTextEdit#console {{ background: {surface_alt}; font-family: "Noto Sans Mono", monospace;
  font-size: {small}px; color: {ink_2}; }}

/* Pickers. The arrows are drawn rather than left to the platform style. */
QComboBox, QSpinBox, QDoubleSpinBox {{ background: {surface}; color: {ink}; border: 3px solid {line_strong};
  border-radius: {r_control}px; padding: 0 {sm}px; min-height: {control}px; font-size: {small}px; }}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: {accent_line}; }}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {accent}; }}
QComboBox:disabled, QSpinBox:disabled {{ background: {disabled}; color: {disabled_ink}; border-color: {line}; }}
QComboBox::drop-down {{ border: 0; width: {lg}px; }}
QComboBox::down-arrow {{ image: {chevron}; width: 12px; height: 12px; }}
QComboBox::down-arrow:disabled {{ image: {chevron_off}; }}
QComboBox QAbstractItemView {{ background: {surface}; border: 3px solid {line}; border-radius: {r_input}px;
  padding: {xs}px; selection-background-color: {accent_soft}; selection-color: {accent_text}; outline: none; }}
/* Origin padding rather than border, so the button sits inside the hairline
   instead of being nudged off it by a margin. */
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: padding; subcontrol-position: top right;
  width: {lg}px; border: 0; border-top-right-radius: {r_control}px; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: padding; subcontrol-position: bottom right;
  width: {lg}px; border: 0; border-bottom-right-radius: {r_control}px; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {accent_soft}; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: {chevron_up}; width: 12px; height: 12px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: {chevron}; width: 12px; height: 12px; }}

/* Check boxes. The global QWidget rule routes these through the stylesheet
   engine, which draws no indicator of its own unless one is declared here. */
QCheckBox {{ background: transparent; color: {ink}; spacing: {sm}px; font-size: {small}px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border: 3px solid {line_strong};
  border-radius: {r_control}px; background: {surface}; }}
QCheckBox::indicator:hover {{ border-color: {accent}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; image: {tick}; }}
QCheckBox::indicator:disabled {{ background: {disabled}; border-color: {line}; }}
QRadioButton {{ background: transparent; color: {ink}; spacing: {sm}px; font-size: {small}px; }}
QRadioButton::indicator {{ width: 18px; height: 18px; border: 3px solid {line_strong};
  border-radius: 9px; background: {surface}; }}
QRadioButton::indicator:checked {{ background: {accent}; border: 6px solid {accent_line}; }}

/* Grouping. The title sits on the rule, not floating above a second border. */
QGroupBox {{ background: {surface}; border: 3px solid {line}; border-radius: {r_input}px;
  margin-top: {md}px; padding: {xl}px {lg}px {lg}px; font-size: {small}px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: {lg}px;
  padding: 0 {sm}px; color: {ink_2}; }}

QProgressBar {{ min-height: 6px; max-height: 6px; border: 0; border-radius: 3px;
  background: {line}; text-align: center; font-size: {label}px; color: transparent; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 3px; }}

QStatusBar {{ background: {ground}; color: {ink_3}; font-size: {caption}px; padding: {xs}px {lg}px; }}
QStatusBar::item {{ border: 0; }}

QScrollBar:vertical {{ width: {sm}px; background: transparent; margin: {xs}px 0; }}
QScrollBar::handle:vertical {{ background: {scroll}; min-height: {xl}px; border-radius: 3px; }}
QScrollBar::handle:vertical:hover {{ background: {ink_3}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ height: {sm}px; background: transparent; margin: 0 {xs}px; }}
QScrollBar::handle:horizontal {{ background: {scroll}; min-width: {xl}px; border-radius: 3px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QSplitter::handle {{ background: transparent; width: {lg}px; }}
QScrollArea {{ background: transparent; border: 0; }}
QGraphicsView {{ border: 3px solid {line}; border-radius: {r_input}px; }}
QTabWidget::pane {{ border: 0; }}
QToolTip {{ color: {ink}; background: {surface}; border: 3px solid {line}; border-radius: {r_control}px;
  padding: {sm}px {md}px; font-size: {caption}px; }}
QMenu {{ background: {surface}; border: 3px solid {line}; border-radius: {r_control}px; padding: {xs}px; }}
QMenu::item {{ padding: {sm}px {md}px; border-radius: {r_control}px; }}
QMenu::item:selected {{ background: {accent_soft}; color: {accent_text}; }}
"""
