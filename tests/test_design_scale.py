"""The window's numbers and colours, held to the rules they were rebuilt on.

Spacing, type, radii, control heights, motion and menu counts are all built
from 3, 4 and 6, and the values 1, 7 and 8 (with the 16 and 32 that doubling
used to produce) do not appear anywhere, lines included.

The palette is four hues: blue, purple, red and pink. There is no white, no
black and no neutral grey in the app, so every token is a tint or a shade
with a visible cast to it, and no module carries a colour of its own.
"""
import re
from pathlib import Path

from jiezhi import theme
from jiezhi.gui import NAV_GROUPS

SEEDS = (3, 4, 6)
PACKAGE = Path(theme.__file__).parent


def on_scale(value):
    return value in SEEDS or any(value % seed == 0 for seed in (3, 6)) or value % 12 == 0


def test_every_scale_constant_is_built_from_three_four_and_six():
    scales = {
        'spacing': (theme.XS, theme.SM, theme.MD, theme.LG, theme.XL, theme.XXL),
        'type': (theme.LABEL, theme.CAPTION, theme.SMALL, theme.BODY, theme.HEADING, theme.TITLE),
        'radius': (theme.R_CONTROL, theme.R_INPUT, theme.R_PANEL),
        'frame': (theme.CONTROL, theme.SIDEBAR),
        'motion': (theme.QUICK, theme.BASE, theme.SLOW, theme.RISE),
    }
    for name, values in scales.items():
        for value in values:
            assert on_scale(value), f'{name} carries {value}, which is not built from 3, 4 or 6'
            assert value not in (1, 7, 8, 16, 32), f'{name} carries the forbidden {value}'


def test_the_spacing_scale_has_six_steps_and_the_radius_scale_three():
    assert len({theme.XS, theme.SM, theme.MD, theme.LG, theme.XL, theme.XXL}) == 6
    assert len({theme.R_CONTROL, theme.R_INPUT, theme.R_PANEL}) == 3
    assert len({theme.QUICK, theme.BASE, theme.SLOW}) == 3


def test_the_type_scale_is_four_sizes_every_one_a_multiple_of_three():
    sizes = {theme.LABEL, theme.CAPTION, theme.SMALL, theme.BODY, theme.HEADING, theme.TITLE}
    assert len(sizes) == 4
    assert all(size % 3 == 0 for size in sizes)


def test_no_pixel_in_the_stylesheet_is_off_the_scale():
    for dark in (False, True):
        sheet = theme.stylesheet(dark)
        for line in sheet.splitlines():
            for declaration in line.split(';'):
                for value in re.findall(r'(\d+)px', declaration):
                    value = int(value)
                    assert value not in (1, 7, 8, 16, 32), \
                        f'{value}px is forbidden: {declaration.strip()}'
                    assert on_scale(value), f'{value}px is off the scale: {declaration.strip()}'


def cast(hexadecimal):
    """How far a colour is from grey, which is what white and black are too."""
    channels = [int(hexadecimal[i:i + 2], 16) for i in (1, 3, 5)]
    return max(channels) - min(channels)


def test_no_token_is_white_black_or_grey():
    for name, table in (('LIGHT', theme.LIGHT), ('DARK', theme.DARK)):
        for key, value in table.items():
            assert re.fullmatch(r'#[0-9a-f]{6}', value), f'{name}[{key}] is not a plain hex'
            assert cast(value) >= 12, \
                f'{name}[{key}] = {value} is grey, white or black. The palette is four hues.'


def test_no_module_carries_a_colour_of_its_own():
    for source in sorted(PACKAGE.glob('*.py')):
        text = source.read_text(encoding='utf-8')
        if source.name != 'theme.py':
            found = re.findall(r'#[0-9a-fA-F]{6}\b', text)
            assert not found, f'{source.name} carries its own colours: {found}'
        for word in ("'white'", '"white"', "'black'", '"black'):
            assert word not in text, f'{source.name} names {word}'


def test_the_menu_is_three_groups_of_three():
    assert len(NAV_GROUPS) == 3
    for title, entries in NAV_GROUPS:
        assert len(entries) == 3, f'{title} holds {len(entries)} destinations'
    pages = [page for _title, entries in NAV_GROUPS for _text, page in entries]
    assert len(set(pages)) == 9
