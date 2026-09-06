"""Region picker and settings UI.

Tk 9.0 crashes on current macOS if AppKit already owns NSApplication
(`[NSApplication macOSVersion]: unrecognized selector`). rumps and ocrmac
both use AppKit, so this UI is AppKit/PyObjC rather than tkinter. Behavior
is unchanged: dim overlay, crosshair, drag a red rectangle, Esc cancels.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable

from numbers_logger.capture import refresh_screens, screen_containing
from numbers_logger.store import (
    MIN_AUTO_STOP_MINUTES,
    MIN_INTERVAL_SECONDS,
    Config,
    load_config,
    save_config,
)

MIN_SELECTION = 4
_NS: dict[str, Any] | None = None
_OverlayViewCls: Any = None
_SettingsControllerCls: Any = None


def run_picker() -> dict[str, float] | None:
    picker = RegionPicker()
    picker.start()
    _pump_until(lambda: picker.done)
    picker.teardown()
    return picker.result


def run_settings() -> bool:
    config = load_config()
    editor = SettingsPanel(config)
    editor.start()
    _pump_until(lambda: editor.done)
    editor.teardown()
    if editor.result is None:
        return False
    save_config(editor.result)
    return True


def run_picker_cli() -> int:
    _ensure_nsapp()
    result = run_picker()
    if result is None:
        return 1
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
    sys.stdout.flush()
    return 0


def run_settings_cli() -> int:
    _ensure_nsapp()
    return 0 if run_settings() else 1


def _load_ns() -> dict[str, Any]:
    global _NS, _OverlayViewCls, _SettingsControllerCls
    if _NS is not None:
        return _NS
    try:
        import objc
        from AppKit import (
            NSApp,
            NSAlert,
            NSAnyEventMask,
            NSApplication,
            NSApplicationActivationPolicyRegular,
            NSBackingStoreBuffered,
            NSBezierPath,
            NSButton,
            NSColor,
            NSCursor,
            NSEvent,
            NSFont,
            NSFontAttributeName,
            NSForegroundColorAttributeName,
            NSMakeRect,
            NSObject,
            NSOffState,
            NSOnState,
            NSOpenPanel,
            NSSavePanel,
            NSScreen,
            NSSwitchButton,
            NSTextField,
            NSView,
            NSWindow,
            NSWindowStyleMaskBorderless,
            NSWindowStyleMaskClosable,
            NSWindowStyleMaskTitled,
        )
        from Foundation import NSDate, NSDefaultRunLoopMode, NSString
    except ImportError as exc:
        print(
            "Missing dependency 'pyobjc-framework-cocoa'. Install with:\n"
            "  uv add pyobjc-framework-cocoa",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    try:
        from AppKit import NSEventTrackingRunLoopMode
    except ImportError:
        NSEventTrackingRunLoopMode = "NSEventTrackingRunLoopMode"

    try:
        from AppKit import NSScreenSaverWindowLevel as OVERLAY_LEVEL
    except ImportError:
        OVERLAY_LEVEL = 1000

    class OverlayView(NSView):
        def initWithOwner_(self, owner):
            self = objc.super(OverlayView, self).init()
            if self is None:
                return None
            self.owner = owner
            return self

        def acceptsFirstResponder(self) -> bool:
            return True

        def acceptsFirstMouse_(self, _event) -> bool:
            return True

        def resetCursorRects(self) -> None:
            self.addCursorRect_cursor_(self.bounds(), NSCursor.crosshairCursor())

        def mouseDown_(self, _event) -> None:
            loc = NSEvent.mouseLocation()
            self.owner.on_press(float(loc.x), float(loc.y))

        def mouseDragged_(self, _event) -> None:
            loc = NSEvent.mouseLocation()
            self.owner.on_drag(float(loc.x), float(loc.y))

        def mouseUp_(self, _event) -> None:
            loc = NSEvent.mouseLocation()
            self.owner.on_release(float(loc.x), float(loc.y))

        def keyDown_(self, event) -> None:
            if int(event.keyCode()) == 53:
                self.owner.cancel()

        def drawRect_(self, _rect) -> None:
            NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.32).setFill()
            NSBezierPath.fillRect_(self.bounds())
            sel = self.owner.cocoa_selection()
            if sel is None:
                return
            gx, gy, gw, gh = sel
            frame = self.window().frame()
            local = NSMakeRect(gx - frame.origin.x, gy - frame.origin.y, gw, gh)
            NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.06).setFill()
            NSBezierPath.fillRect_(local)
            NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.23, 0.19, 1.0).setStroke()
            path = NSBezierPath.bezierPathWithRect_(local)
            path.setLineWidth_(2.0)
            path.stroke()
            label = f"{int(round(gw))} × {int(round(gh))}"
            attrs = {
                NSFontAttributeName: NSFont.boldSystemFontOfSize_(13.0),
                NSForegroundColorAttributeName: NSColor.whiteColor(),
            }
            text = NSString.stringWithString_(label)
            size = text.sizeWithAttributes_(attrs)
            tx = local.origin.x + local.size.width - size.width - 6
            ty = local.origin.y + local.size.height + 6
            bounds = self.bounds()
            tx = min(max(8.0, tx), max(8.0, bounds.size.width - size.width - 8))
            ty = min(max(8.0, ty), max(8.0, bounds.size.height - size.height - 8))
            text.drawAtPoint_withAttributes_((tx, ty), attrs)

    class SettingsController(NSObject):
        def initWithPanel_(self, panel):
            self = objc.super(SettingsController, self).init()
            if self is None:
                return None
            self.panel = panel
            return self

        def browse_(self, sender) -> None:
            self.panel.browse_(sender)

        def cancel_(self, sender) -> None:
            self.panel.cancel_(sender)

        def save_(self, sender) -> None:
            self.panel.save_(sender)

        def windowShouldClose_(self, _sender) -> bool:
            self.panel.cancel_(None)
            return True

    _OverlayViewCls = OverlayView
    _SettingsControllerCls = SettingsController
    _NS = {
        "NSApp": NSApp,
        "NSAlert": NSAlert,
        "NSAnyEventMask": NSAnyEventMask,
        "NSApplication": NSApplication,
        "NSApplicationActivationPolicyRegular": NSApplicationActivationPolicyRegular,
        "NSBackingStoreBuffered": NSBackingStoreBuffered,
        "NSButton": NSButton,
        "NSColor": NSColor,
        "NSCursor": NSCursor,
        "NSDate": NSDate,
        "NSDefaultRunLoopMode": NSDefaultRunLoopMode,
        "NSEvent": NSEvent,
        "NSEventTrackingRunLoopMode": NSEventTrackingRunLoopMode,
        "NSMakeRect": NSMakeRect,
        "NSOffState": NSOffState,
        "NSOnState": NSOnState,
        "NSOpenPanel": NSOpenPanel,
        "NSSavePanel": NSSavePanel,
        "NSScreen": NSScreen,
        "NSSwitchButton": NSSwitchButton,
        "NSTextField": NSTextField,
        "NSWindow": NSWindow,
        "NSWindowStyleMaskBorderless": NSWindowStyleMaskBorderless,
        "NSWindowStyleMaskClosable": NSWindowStyleMaskClosable,
        "NSWindowStyleMaskTitled": NSWindowStyleMaskTitled,
        "OVERLAY_LEVEL": OVERLAY_LEVEL,
    }
    return _NS


class RegionPicker:
    def __init__(self) -> None:
        self.done = False
        self.result: dict[str, float] | None = None
        self.anchor: tuple[float, float] | None = None
        self.current: tuple[float, float] | None = None
        self._windows: list[Any] = []
        self._views: list[Any] = []
        self._monitor = None
        self._main_height = 0.0

    def start(self) -> None:
        ns = _load_ns()
        refresh_screens()
        screens = ns["NSScreen"].screens()
        if not screens:
            self.done = True
            return
        self._main_height = float(screens[0].frame().size.height)
        for screen in screens:
            frame = screen.frame()
            window = ns["NSWindow"].alloc().initWithContentRect_styleMask_backing_defer_(
                frame,
                ns["NSWindowStyleMaskBorderless"],
                ns["NSBackingStoreBuffered"],
                False,
            )
            window.setLevel_(int(ns["OVERLAY_LEVEL"]))
            window.setOpaque_(False)
            window.setBackgroundColor_(ns["NSColor"].clearColor())
            window.setHasShadow_(False)
            window.setIgnoresMouseEvents_(False)
            window.setAcceptsMouseMovedEvents_(True)
            window.setReleasedWhenClosed_(False)
            window.setCollectionBehavior_(1 | 256)
            view = _OverlayViewCls.alloc().initWithOwner_(self)
            view.setFrame_(ns["NSMakeRect"](0, 0, frame.size.width, frame.size.height))
            window.setContentView_(view)
            window.makeKeyAndOrderFront_(None)
            window.orderFrontRegardless()
            self._windows.append(window)
            self._views.append(view)
        if self._windows:
            self._windows[-1].makeFirstResponder_(self._views[-1])
        ns["NSCursor"].crosshairCursor().set()
        ns["NSApp"].activateIgnoringOtherApps_(True)
        self._monitor = _add_escape_monitor(self.cancel)

    def cocoa_selection(self) -> tuple[float, float, float, float] | None:
        if self.anchor is None or self.current is None:
            return None
        x0, y0 = self.anchor
        x1, y1 = self.current
        left, bottom = min(x0, x1), min(y0, y1)
        width, height = abs(x1 - x0), abs(y1 - y0)
        if width < 1 and height < 1:
            return None
        return left, bottom, width, height

    def on_press(self, x: float, y: float) -> None:
        self.anchor = (x, y)
        self.current = (x, y)
        self._redraw()

    def on_drag(self, x: float, y: float) -> None:
        if self.anchor is None:
            return
        self.current = (x, y)
        self._redraw()

    def on_release(self, x: float, y: float) -> None:
        if self.anchor is None:
            return
        self.current = (x, y)
        sel = self.cocoa_selection()
        self.anchor = None
        self.current = None
        if sel is None or sel[2] < MIN_SELECTION or sel[3] < MIN_SELECTION:
            self._redraw()
            return
        left, bottom, width, height = sel
        x_tl = left
        y_tl = self._main_height - (bottom + height)
        cx = x_tl + width / 2.0
        cy = y_tl + height / 2.0
        screens = refresh_screens()
        screen = screen_containing(cx, cy, screens) or (screens[0] if screens else None)
        scale = float(screen.scale) if screen is not None else 2.0
        self.result = {
            "x": float(round(x_tl, 2)),
            "y": float(round(y_tl, 2)),
            "width": float(round(width, 2)),
            "height": float(round(height, 2)),
            "scale": scale,
        }
        self.done = True

    def cancel(self) -> None:
        self.result = None
        self.done = True

    def teardown(self) -> None:
        _remove_monitor(self._monitor)
        self._monitor = None
        for window in self._windows:
            try:
                window.orderOut_(None)
                window.close()
            except Exception:
                pass
        self._windows.clear()
        self._views.clear()
        try:
            _load_ns()["NSCursor"].arrowCursor().set()
        except Exception:
            pass

    def _redraw(self) -> None:
        for view in self._views:
            view.setNeedsDisplay_(True)


class SettingsPanel:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.result: Config | None = None
        self.done = False
        self._window = None
        self._controller = None
        self._monitor = None
        self._fields: dict[str, Any] = {}

    def start(self) -> None:
        ns = _load_ns()
        width, height = 460.0, 340.0
        screen = ns["NSScreen"].mainScreen().frame()
        origin_x = screen.origin.x + (screen.size.width - width) / 2.0
        origin_y = screen.origin.y + (screen.size.height - height) / 2.0
        window = ns["NSWindow"].alloc().initWithContentRect_styleMask_backing_defer_(
            ns["NSMakeRect"](origin_x, origin_y, width, height),
            ns["NSWindowStyleMaskTitled"] | ns["NSWindowStyleMaskClosable"],
            ns["NSBackingStoreBuffered"],
            False,
        )
        window.setTitle_("Settings")
        window.setReleasedWhenClosed_(False)
        content = window.contentView()
        controller = _SettingsControllerCls.alloc().initWithPanel_(self)
        window.setDelegate_(controller)
        self._controller = controller

        def add_label(text: str, y: float) -> None:
            field = ns["NSTextField"].alloc().initWithFrame_(ns["NSMakeRect"](20, y, 150, 22))
            field.setStringValue_(text)
            field.setEditable_(False)
            field.setBezeled_(False)
            field.setDrawsBackground_(False)
            field.setSelectable_(False)
            content.addSubview_(field)

        def add_entry(value: str, y: float, key: str, w: float = 250.0) -> None:
            field = ns["NSTextField"].alloc().initWithFrame_(ns["NSMakeRect"](180, y, w, 22))
            field.setStringValue_(value)
            content.addSubview_(field)
            self._fields[key] = field

        add_label("Interval (seconds)", 280)
        add_entry(str(self.config.interval_seconds), 280, "interval")
        add_label("CSV folder", 240)
        add_entry(self.config.csv_path, 240, "csv", 190)

        browse = ns["NSButton"].alloc().initWithFrame_(ns["NSMakeRect"](378, 236, 64, 28))
        browse.setTitle_("Browse")
        browse.setBezelStyle_(1)
        browse.setTarget_(controller)
        browse.setAction_("browse:")
        content.addSubview_(browse)

        change = ns["NSButton"].alloc().initWithFrame_(ns["NSMakeRect"](20, 198, 420, 24))
        change.setButtonType_(ns["NSSwitchButton"])
        change.setTitle_("Log only when the number changes")
        change.setState_(ns["NSOnState"] if self.config.log_only_on_change else ns["NSOffState"])
        content.addSubview_(change)
        self._fields["change"] = change

        add_label("Min confidence (0–1)", 158)
        add_entry(str(self.config.min_confidence), 158, "confidence")

        auto_stop = ns["NSButton"].alloc().initWithFrame_(ns["NSMakeRect"](20, 118, 420, 24))
        auto_stop.setButtonType_(ns["NSSwitchButton"])
        auto_stop.setTitle_("Auto-stop recording")
        auto_stop.setState_(ns["NSOnState"] if self.config.auto_stop_enabled else ns["NSOffState"])
        content.addSubview_(auto_stop)
        self._fields["auto_stop"] = auto_stop

        add_label("After (minutes)", 78)
        add_entry(str(self.config.auto_stop_minutes), 78, "auto_stop_minutes")

        cancel = ns["NSButton"].alloc().initWithFrame_(ns["NSMakeRect"](268, 20, 80, 32))
        cancel.setTitle_("Cancel")
        cancel.setBezelStyle_(1)
        cancel.setTarget_(controller)
        cancel.setAction_("cancel:")
        content.addSubview_(cancel)

        save = ns["NSButton"].alloc().initWithFrame_(ns["NSMakeRect"](356, 20, 80, 32))
        save.setTitle_("Save")
        save.setBezelStyle_(1)
        save.setKeyEquivalent_("\r")
        save.setTarget_(controller)
        save.setAction_("save:")
        content.addSubview_(save)

        window.makeKeyAndOrderFront_(None)
        ns["NSApp"].activateIgnoringOtherApps_(True)
        self._window = window
        self._monitor = _add_escape_monitor(lambda: self.cancel_(None))

    def browse_(self, _sender) -> None:
        ns = _load_ns()
        panel = ns["NSOpenPanel"].openPanel()
        panel.setTitle_("CSV folder")
        panel.setCanChooseFiles_(False)
        panel.setCanChooseDirectories_(True)
        panel.setAllowsMultipleSelection_(False)
        panel.setCanCreateDirectories_(True)
        if int(panel.runModal()) == 1:
            url = panel.URL()
            if url is not None:
                self._fields["csv"].setStringValue_(str(url.path()))

    def cancel_(self, _sender) -> None:
        self.result = None
        self.done = True

    def save_(self, _sender) -> None:
        interval_text = str(self._fields["interval"].stringValue()).strip()
        confidence_text = str(self._fields["confidence"].stringValue()).strip()
        minutes_text = str(self._fields["auto_stop_minutes"].stringValue()).strip()
        csv_path = str(self._fields["csv"].stringValue()).strip()
        try:
            interval = float(interval_text)
        except ValueError:
            _alert("Interval must be a number.")
            return
        if interval < MIN_INTERVAL_SECONDS:
            _alert(f"Interval must be at least {MIN_INTERVAL_SECONDS} seconds.")
            return
        try:
            confidence = float(confidence_text)
        except ValueError:
            _alert("Min confidence must be a number between 0 and 1.")
            return
        if not 0.0 <= confidence <= 1.0:
            _alert("Min confidence must be between 0 and 1.")
            return
        try:
            minutes = float(minutes_text)
        except ValueError:
            _alert("Auto-stop duration must be a number of minutes.")
            return
        if minutes < MIN_AUTO_STOP_MINUTES:
            _alert(f"Auto-stop duration must be at least {MIN_AUTO_STOP_MINUTES:g} minutes.")
            return
        if not csv_path:
            _alert("CSV folder is required.")
            return
        ns = _load_ns()
        self.result = Config(
            interval_seconds=interval,
            csv_path=csv_path,
            log_only_on_change=bool(
                int(self._fields["change"].state()) == int(ns["NSOnState"])
            ),
            min_confidence=confidence,
            auto_stop_enabled=bool(
                int(self._fields["auto_stop"].state()) == int(ns["NSOnState"])
            ),
            auto_stop_minutes=minutes,
            region=self.config.region,
        )
        self.done = True

    def teardown(self) -> None:
        _remove_monitor(self._monitor)
        self._monitor = None
        if self._window is not None:
            try:
                self._window.orderOut_(None)
                self._window.close()
            except Exception:
                pass
            self._window = None
        self._controller = None


def _alert(message: str) -> None:
    ns = _load_ns()
    alert = ns["NSAlert"].alloc().init()
    alert.setMessageText_("Settings")
    alert.setInformativeText_(message)
    alert.addButtonWithTitle_("OK")
    alert.runModal()


def _add_escape_monitor(callback: Callable[[], None]) -> Any:
    ns = _load_ns()

    def handler(event):
        try:
            if int(event.keyCode()) == 53:
                callback()
        except Exception:
            pass
        return event

    try:
        return ns["NSEvent"].addLocalMonitorForEventsMatchingMask_handler_(1 << 10, handler)
    except Exception:
        return None


def _remove_monitor(monitor: Any) -> None:
    if monitor is None:
        return
    try:
        _load_ns()["NSEvent"].removeMonitor_(monitor)
    except Exception:
        pass


def _ensure_nsapp() -> None:
    ns = _load_ns()
    ns["NSApplication"].sharedApplication()
    ns["NSApp"].setActivationPolicy_(ns["NSApplicationActivationPolicyRegular"])
    ns["NSApp"].activateIgnoringOtherApps_(True)
    try:
        if not ns["NSApp"].isRunning():
            ns["NSApp"].finishLaunching()
    except Exception:
        pass


def _pump_until(is_done: Callable[[], bool]) -> None:
    ns = _load_ns()
    app = ns["NSApp"]
    modes = [ns["NSDefaultRunLoopMode"], ns["NSEventTrackingRunLoopMode"]]
    while not is_done():
        got_event = False
        for mode in modes:
            event = app.nextEventMatchingMask_untilDate_inMode_dequeue_(
                ns["NSAnyEventMask"],
                ns["NSDate"].dateWithTimeIntervalSinceNow_(0.03),
                mode,
                True,
            )
            if event is not None:
                app.sendEvent_(event)
                app.updateWindows()
                got_event = True
                break
        if not got_event:
            continue


if __name__ == "__main__":
    if "--settings" in sys.argv:
        raise SystemExit(run_settings_cli())
    raise SystemExit(run_picker_cli())
