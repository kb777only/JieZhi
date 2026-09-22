"""The window's numbers, held to the scale they were rebuilt on.

Spacing, type, radii, control heights, motion and menu counts are all built
from 3, 4 and 6. The values 1, 7 and 8 (and the 16 and 32 that doubling used
to produce) do not appear. The single exception is the hairline: a border is
either absent or one physical pixel, so 1px is allowed where a rule draws a
line and nowhere else.
"""
import re

from jiezhi import theme
from jiezhi.gui import NAV_GROUPS

SEEDS = (3, 4, 6)
HAIRLINE = ('border', 'outline', 'min-height', 'max-height')


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


def test_the_stylesheet_only_spends_a_pixel_on_hairlines():
    for dark in (False, True):
        sheet = theme.stylesheet(dark)
        for line in sheet.splitlines():
            for declaration in line.split(';'):
                for value in re.findall(r'(\d+)px', declaration):
                    value = int(value)
                    if value == 1:
                        assert any(word in declaration for word in HAIRLINE), \
                            f'a pixel is spent on something that is not a line: {declaration.strip()}'
                        continue
                    assert on_scale(value), f'{value}px is off the scale: {declaration.strip()}'


def test_the_menu_is_three_groups_of_three():
    assert len(NAV_GROUPS) == 3
    for title, entries in NAV_GROUPS:
        assert len(entries) == 3, f'{title} holds {len(entries)} destinations'
    pages = [page for _title, entries in NAV_GROUPS for _text, page in entries]
    assert len(set(pages)) == 9
