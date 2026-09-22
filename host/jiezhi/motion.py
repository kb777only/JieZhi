"""One motion language for the window.

The selection chip and its menu already fade and rise under the pointer. This
gives the window the same behaviour from the same three durations in theme.py,
so nothing in the app moves in a timing of its own invention.

Every helper here is a no-op when the motion preference is off. That keeps the
app's reduced-motion switch a single switch: a new animation cannot forget to
honour it, because it cannot start without asking.
"""
from __future__ import annotations

from PySide6.QtCore import (QAbstractAnimation, QEasingCurve, QParallelAnimationGroup,
                            QPoint, QPropertyAnimation, QTimer)
from PySide6.QtWidgets import QGraphicsOpacityEffect

from .theme import BASE, QUICK, RISE, SLOW

CURVE = QEasingCurve.Type.OutCubic


def moving(widget) -> bool:
    """The window's reduced-motion switch, read from wherever we happen to be."""
    window = widget.window()
    return bool(getattr(window, 'preferences', {}).get('motion', True))


def _keep(widget, animation):
    """Qt drops an animation that nothing holds, mid-flight and silently."""
    widget._motion = animation
    animation.start(QAbstractAnimation.DeletionPolicy.KeepWhenStopped)
    return animation


def fade_in(widget, duration=BASE, rise=0):
    """Fade a widget up, optionally from a few pixels below where it rests."""
    if not moving(widget):
        return None
    effect = QGraphicsOpacityEffect(widget); effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    group = QParallelAnimationGroup(widget)
    opacity = QPropertyAnimation(effect, b'opacity', group)
    opacity.setDuration(duration); opacity.setEasingCurve(CURVE)
    opacity.setStartValue(0.0); opacity.setEndValue(1.0)
    group.addAnimation(opacity)
    if rise:
        rest = widget.pos()
        slide = QPropertyAnimation(widget, b'pos', group)
        slide.setDuration(duration); slide.setEasingCurve(CURVE)
        slide.setStartValue(QPoint(rest.x(), rest.y() + rise)); slide.setEndValue(rest)
        group.addAnimation(slide)
    # The effect costs a render pass on every repaint, so it comes off again
    # the moment the fade is done rather than living on the widget for good.
    group.finished.connect(lambda: widget.setGraphicsEffect(None))
    return _keep(widget, group)


def reveal(widget, duration=BASE):
    """Open a panel by its own height, then hand the height back to the layout."""
    widget.setVisible(True)
    if not moving(widget):
        return None
    target = widget.sizeHint().height()
    animation = QPropertyAnimation(widget, b'maximumHeight', widget)
    animation.setDuration(duration); animation.setEasingCurve(CURVE)
    animation.setStartValue(0); animation.setEndValue(target)
    animation.finished.connect(lambda: widget.setMaximumHeight(16_777_215))
    return _keep(widget, animation)


def conceal(widget, duration=QUICK):
    """Close a panel the same way, and only hide it once it has closed."""
    if not moving(widget):
        widget.setVisible(False); return None
    animation = QPropertyAnimation(widget, b'maximumHeight', widget)
    animation.setDuration(duration); animation.setEasingCurve(CURVE)
    animation.setStartValue(widget.height()); animation.setEndValue(0)

    def done():
        widget.setVisible(False); widget.setMaximumHeight(16_777_215)
    animation.finished.connect(done)
    return _keep(widget, animation)


def present(dialog, duration=QUICK):
    """Show a modal dialog as a fade rather than as a bang."""
    if moving(dialog):
        dialog.setWindowOpacity(0.0)
        animation = QPropertyAnimation(dialog, b'windowOpacity', dialog)
        animation.setDuration(duration); animation.setEasingCurve(CURVE)
        animation.setStartValue(0.0); animation.setEndValue(1.0)
        dialog._motion = animation
        # exec() runs its own event loop, so the animation has to be armed for
        # the first turn of it rather than started here.
        QTimer.singleShot(0, animation.start)
    return dialog.exec()


def arrive(window, duration=SLOW):
    """The window itself, fading up once at launch."""
    if not moving(window):
        return None
    window.setWindowOpacity(0.0)
    animation = QPropertyAnimation(window, b'windowOpacity', window)
    animation.setDuration(duration); animation.setEasingCurve(CURVE)
    animation.setStartValue(0.0); animation.setEndValue(1.0)
    return _keep(window, animation)


__all__ = ['CURVE', 'RISE', 'arrive', 'conceal', 'fade_in', 'moving', 'present', 'reveal']
