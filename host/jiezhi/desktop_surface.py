"""Small X11/AT-SPI adapters. Read pointer/selection state, never keyboard input."""
import ctypes as C
import ctypes.util
import time
import subprocess
import json
import sys
from pathlib import Path


class X11Pointer:
    def __init__(self):
        self.lib=C.CDLL(ctypes.util.find_library('X11'))
        self.lib.XOpenDisplay.argtypes=[C.c_char_p];self.lib.XOpenDisplay.restype=C.c_void_p
        self.lib.XDefaultRootWindow.argtypes=[C.c_void_p];self.lib.XDefaultRootWindow.restype=C.c_ulong
        self.lib.XQueryPointer.argtypes=[C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_uint)]
        self.lib.XCloseDisplay.argtypes=[C.c_void_p]
        self.display=self.lib.XOpenDisplay(None)
        if not self.display:raise RuntimeError('X11 display is unavailable')
        self.root=self.lib.XDefaultRootWindow(self.display)
    def state(self):
        root=C.c_ulong();child=C.c_ulong();x=C.c_int();y=C.c_int();wx=C.c_int();wy=C.c_int();mask=C.c_uint()
        ok=self.lib.XQueryPointer(self.display,self.root,C.byref(root),C.byref(child),C.byref(x),C.byref(y),C.byref(wx),C.byref(wy),C.byref(mask))
        return (x.value,y.value,mask.value) if ok else None
    def dismiss_context_menu(self):
        # Called only after the user deliberately hovers our icon for 350 ms.
        xtst=C.CDLL(ctypes.util.find_library('Xtst'))
        self.lib.XKeysymToKeycode.argtypes=[C.c_void_p,C.c_ulong];self.lib.XKeysymToKeycode.restype=C.c_uint
        xtst.XTestFakeKeyEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
        key=self.lib.XKeysymToKeycode(self.display,0xff1b)
        xtst.XTestFakeKeyEvent(self.display,key,1,0);xtst.XTestFakeKeyEvent(self.display,key,0,0)
        self.lib.XFlush.argtypes=[C.c_void_p];self.lib.XFlush(self.display)
    def close(self):
        if self.display:self.lib.XCloseDisplay(self.display);self.display=None


class Rect(C.Structure):
    _fields_=[('x',C.c_int),('y',C.c_int),('width',C.c_int),('height',C.c_int)]


def accessible_image_rect(x,y):
    """Return only an exposed image's on-screen bounds; otherwise ask for an area."""
    try:
        check=subprocess.run(['gdbus','call','--session','--dest','org.a11y.Bus','--object-path','/org/a11y/bus','--method','org.a11y.Bus.GetAddress'],capture_output=True,timeout=1)
        if check.returncode:return None
    except (OSError,subprocess.TimeoutExpired):return None
    lib=C.CDLL(ctypes.util.find_library('atspi'));glib=C.CDLL(ctypes.util.find_library('glib-2.0'));gobj=C.CDLL(ctypes.util.find_library('gobject-2.0'))
    def fn(name,args,result):
        f=getattr(lib,name);f.argtypes=args;f.restype=result;return f
    ptr=C.c_void_p;integer=C.c_int
    fn('atspi_init',[],integer)();fn('atspi_set_timeout',[integer,integer],None)(350,350)
    desktop=fn('atspi_get_desktop',[integer],ptr)(0)
    if not desktop:return None
    count=fn('atspi_accessible_get_child_count',[ptr,ptr],integer)
    child=fn('atspi_accessible_get_child_at_index',[ptr,integer,ptr],ptr)
    component=fn('atspi_accessible_get_component_iface',[ptr],ptr)
    point=fn('atspi_component_get_accessible_at_point',[ptr,integer,integer,integer,ptr],ptr)
    image=fn('atspi_accessible_get_image_iface',[ptr],ptr)
    bounds=fn('atspi_image_get_image_extents',[ptr,integer,ptr],C.POINTER(Rect))
    glib.g_free.argtypes=[ptr];gobj.g_object_unref.argtypes=[ptr]
    held=[desktop];end=time.monotonic()+1.5
    def keep(p):
        if p:held.append(p)
        return p
    try:
        for i in range(min(30,max(0,count(desktop,None)))):
            if time.monotonic()>end:break
            app=keep(child(desktop,i,None))
            if not app:continue
            for j in range(min(12,max(0,count(app,None)))):
                if time.monotonic()>end:return None
                node=keep(child(app,j,None));seen=set()
                for _ in range(15):
                    if not node or node in seen:break
                    seen.add(node);img=keep(image(node))
                    if img:
                        r=bounds(img,0,None)
                        if r:
                            q=r.contents;result=(q.x,q.y,q.width,q.height);glib.g_free(r)
                            if result[2]>4 and result[3]>4 and result[0]<=x<result[0]+result[2] and result[1]<=y<result[1]+result[3]:return result
                    comp=keep(component(node))
                    if not comp:break
                    node=keep(point(comp,x,y,0,None))
        return None
    finally:
        for obj in reversed(held):gobj.g_object_unref(obj)


def probe_image_rect(x,y):
    # Accessibility bridges are optional and some abort on initialization errors.
    # Keep their native calls outside the host process.
    command=[sys.executable] if getattr(sys,'frozen',False) else [sys.executable,str(Path(__file__).resolve().parents[1]/'main.py')]
    try:
        result=subprocess.run([*command,'--probe-image',str(x),str(y)],capture_output=True,text=True,timeout=3)
        value=json.loads(result.stdout) if result.returncode==0 else None
        return value if isinstance(value,list) and len(value)==4 and all(type(n) is int for n in value) else None
    except (OSError,ValueError,subprocess.TimeoutExpired):return None
