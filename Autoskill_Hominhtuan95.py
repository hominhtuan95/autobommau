"""Autoskill Hominhtuan95 - 10 skills + screen OCR Auto HP; no license, no auto train.
Windows 10/11, Python 3.10+. Game must be visible and in foreground for HP reading.
"""
import ctypes
import re
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

APP_NAME = 'Autoskill Hominhtuan95'
DEFAULTS = [5000, 300] + [1000] * 10
LABELS = ['Tab', 'Space'] + [f'Skill {i}' for i in range(1, 11)]
VKS = [0x09, 0x20] + list(range(0x31, 0x3A)) + [0x30]
WM_KEYDOWN, WM_KEYUP = 0x100, 0x101

if not hasattr(ctypes, 'windll'):
    raise SystemExit('Chương trình chỉ chạy trên Windows.')
user32 = ctypes.windll.user32
WND = ctypes.c_void_p
CALLBACK = ctypes.WINFUNCTYPE(ctypes.c_bool, WND, ctypes.c_void_p)
user32.EnumWindows.argtypes = [CALLBACK, ctypes.c_void_p]
user32.EnumWindows.restype = ctypes.c_bool
user32.IsWindowVisible.argtypes = [WND]
user32.IsWindowVisible.restype = ctypes.c_bool
user32.IsWindow.argtypes = [WND]
user32.IsWindow.restype = ctypes.c_bool
user32.IsIconic.argtypes = [WND]
user32.IsIconic.restype = ctypes.c_bool
user32.GetWindowTextLengthW.argtypes = [WND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [WND, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetForegroundWindow.restype = WND
user32.PostMessageW.argtypes = [WND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
user32.PostMessageW.restype = ctypes.c_bool

class POINT(ctypes.Structure):
    _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]


def get_hp(rect, screen):
    """Read current/max HP from an explicitly calibrated screen rectangle."""
    import pytesseract
    from PIL import Image, ImageOps, ImageEnhance, ImageFilter
    x1, y1, x2, y2 = rect
    shot = screen.grab({'left': x1, 'top': y1, 'width': x2-x1, 'height': y2-y1})
    img = Image.frombytes('RGB', shot.size, shot.rgb)
    img = ImageEnhance.Contrast(ImageOps.grayscale(img)).enhance(3)
    img = img.resize((img.width * 3, img.height * 3)).filter(ImageFilter.SHARPEN)
    raw = pytesseract.image_to_string(img, config='--psm 7 -c tessedit_char_whitelist=0123456789/')
    match = re.search(r'(\d{1,8})\s*/\s*(\d{1,8})', raw)
    if not match:
        return None
    current, maximum = map(int, match.groups())
    if maximum <= 0 or not 0 <= current <= maximum:
        return None
    return current, maximum


class AutoSkill:
    def __init__(self, root):
        self.root = root
        root.title(APP_NAME + ' - 10 Skill + Auto HP')
        root.geometry('490x760')
        root.minsize(450, 710)
        self.running = False
        self.closing = False
        self.stop_event = None
        self.hwnds = []
        self.hwnd = None
        self.calibrating = False
        self.hp_corners = {'tl': None, 'br': None}
        self.status = tk.StringVar(value='Đã dừng | F1 chỉ khi cửa sổ AutoSkill được chọn')
        self.hp_status = tk.StringVar(value='HP: chưa đọc')
        self.ms = [tk.StringVar(value=str(n)) for n in DEFAULTS]
        self.enabled = [tk.BooleanVar(value=True) for _ in DEFAULTS]
        self.hp_enabled = tk.BooleanVar(value=True)
        self.hp_threshold = tk.StringVar(value='30')
        self.hp_cooldown = tk.StringVar(value='2000')
        self.choice = tk.StringVar()

        ttk.Label(root, text=APP_NAME + ' | 10 SKILL + AUTO HP', font=('Segoe UI', 12, 'bold')).pack(pady=9)
        select = ttk.Frame(root)
        select.pack(fill='x', padx=12)
        self.selector = ttk.Combobox(select, textvariable=self.choice, state='readonly')
        self.selector.pack(side='left', fill='x', expand=True)
        ttk.Button(select, text='Làm mới', command=self.refresh).pack(side='left', padx=4)
        rows = ttk.LabelFrame(root, text='Auto Skill / Tab / Space')
        rows.pack(fill='x', padx=12, pady=9)
        rows.columnconfigure(0, weight=1)
        ttk.Label(rows, text='Phím').grid(row=0, column=0, sticky='w', padx=9)
        ttk.Label(rows, text='Chu kỳ (ms)').grid(row=0, column=1, sticky='e', padx=9)
        for i, label in enumerate(LABELS):
            if i == 11:
                label += ' (phím 0)'
            ttk.Checkbutton(rows, text=label, variable=self.enabled[i]).grid(row=i+1, column=0, sticky='w', padx=9, pady=2)
            ttk.Entry(rows, textvariable=self.ms[i], width=12, justify='right').grid(row=i+1, column=1, sticky='e', padx=9, pady=2)
        ttk.Label(rows, text='Chu kỳ mỗi phím: 50–180000 ms', foreground='#555').grid(row=13, column=0, columnspan=2, pady=5)

        hp = ttk.LabelFrame(root, text='Auto HP bằng hình ảnh (phím F4)')
        hp.pack(fill='x', padx=12, pady=5)
        ttk.Checkbutton(hp, text='Bật Auto HP', variable=self.hp_enabled).pack(anchor='w', padx=8, pady=3)
        settings = ttk.Frame(hp)
        settings.pack(fill='x', padx=8, pady=3)
        ttk.Label(settings, text='Bơm khi HP ≤').pack(side='left')
        ttk.Entry(settings, textvariable=self.hp_threshold, width=5).pack(side='left', padx=4)
        ttk.Label(settings, text='%    Nghỉ tối thiểu (ms)').pack(side='left')
        ttk.Entry(settings, textvariable=self.hp_cooldown, width=8).pack(side='left', padx=4)
        calibration = ttk.Frame(hp)
        calibration.pack(fill='x', padx=8, pady=4)
        ttk.Button(calibration, text='Lấy góc trên-trái HP', command=lambda: self.calibrate_hp('tl')).pack(side='left', expand=True, fill='x', padx=2)
        ttk.Button(calibration, text='Lấy góc dưới-phải HP', command=lambda: self.calibrate_hp('br')).pack(side='left', expand=True, fill='x', padx=2)
        ttk.Label(hp, textvariable=self.hp_status).pack(anchor='w', padx=8, pady=3)
        ttk.Label(hp, text='Mỗi lần bấm Lấy, có 4 giây để đưa chuột tới góc vùng chứa số Khí Huyết: hiện tại/tối đa.', wraplength=450, foreground='#555').pack(anchor='w', padx=8, pady=(0, 6))
        controls = ttk.Frame(root)
        controls.pack(fill='x', padx=12, pady=8)
        ttk.Button(controls, text='Chạy', command=self.start).pack(side='left', expand=True, fill='x', padx=3)
        ttk.Button(controls, text='Dừng', command=self.stop).pack(side='left', expand=True, fill='x', padx=3)
        ttk.Label(root, textvariable=self.status, wraplength=460).pack(pady=3)
        root.bind_all('<F1>', self.toggle_f1)
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh()

    def refresh(self):
        previous = self.hwnd
        found = []
        @CALLBACK
        def callback(hwnd, unused):
            if user32.IsWindowVisible(hwnd):
                n = user32.GetWindowTextLengthW(hwnd)
                if n:
                    buf = ctypes.create_unicode_buffer(n+1)
                    user32.GetWindowTextW(hwnd, buf, n+1)
                    if 'chien quoc' in buf.value.casefold() or 'chiến quốc' in buf.value.casefold():
                        found.append((int(hwnd), buf.value))
            return True
        user32.EnumWindows(callback, None)
        self.hwnds = found
        self.selector['values'] = [f'{hwnd} | {title[:42]}' for hwnd, title in found]
        if found:
            self.selector.current(next((i for i, (h, _) in enumerate(found) if h == previous), 0))
        else:
            self.choice.set('Không tìm thấy cửa sổ Chiến Quốc')

    def calibrate_hp(self, corner):
        if self.calibrating:
            return
        self.calibrating = True
        self.hp_status.set('Trong 4 giây, trỏ chuột tới góc ' + ('trên-trái' if corner == 'tl' else 'dưới-phải'))
        def capture():
            self.calibrating = False
            pt = POINT()
            if user32.GetCursorPos(ctypes.byref(pt)):
                self.hp_corners[corner] = (pt.x, pt.y)
                self.hp_status.set(f'Đã lưu {corner}: {pt.x}, {pt.y}')
            else:
                self.hp_status.set('Không lấy được vị trí chuột')
        self.root.after(4000, capture)

    def toggle_f1(self, event=None):
        if not self.closing:
            self.stop() if self.running else self.start()
        return 'break'

    @staticmethod
    def send_key(hwnd, vk, stop_event):
        if not user32.PostMessageW(hwnd, WM_KEYDOWN, vk, 0):
            return False
        interrupted = stop_event.wait(0.04)
        user32.PostMessageW(hwnd, WM_KEYUP, vk, 0)
        return not interrupted

    def start(self):
        if self.running or self.closing:
            return
        idx = self.selector.current()
        if idx < 0 or idx >= len(self.hwnds):
            messagebox.showwarning('Chọn game', 'Mở Chiến Quốc rồi bấm Làm mới.', parent=self.root)
            return
        try:
            delays = [int(v.get()) for v in self.ms]
            if any(not 50 <= d <= 180000 for d in delays):
                raise ValueError('Chu kỳ phím phải từ 50 đến 180000 ms')
            active = [v.get() for v in self.enabled]
            hp_config = None
            if self.hp_enabled.get():
                threshold = float(self.hp_threshold.get().replace(',', '.'))
                cooldown = int(self.hp_cooldown.get())
                if not 1 <= threshold <= 99 or cooldown < 2000:
                    raise ValueError('Ngưỡng HP: 1–99%; thời gian nghỉ tối thiểu 2000 ms')
                tl, br = self.hp_corners['tl'], self.hp_corners['br']
                if not tl or not br or br[0] <= tl[0] or br[1] <= tl[1]:
                    raise ValueError('Chưa chọn đủ 2 góc vùng số HP')
                import mss, pytesseract
                pytesseract.get_tesseract_version()
                hp_config = (threshold, cooldown / 1000.0, (*tl, *br))
            if not any(active) and not hp_config:
                raise ValueError('Hãy bật ít nhất một phím hoặc Auto HP')
        except Exception as exc:
            messagebox.showerror('Cấu hình chưa đúng', str(exc), parent=self.root)
            return
        hwnd = self.hwnds[idx][0]
        if not user32.IsWindow(hwnd):
            messagebox.showerror('Game đã đóng', 'Hãy bấm Làm mới.', parent=self.root)
            return
        self.hwnd = hwnd
        self.stop_event = threading.Event()
        self.running = True
        self.status.set(f'Đang chạy | HWND {hwnd}')
        threading.Thread(target=self.worker, args=(hwnd, [d/1000 for d in delays], active, hp_config, self.stop_event), daemon=True).start()

    def worker(self, hwnd, delays, active, hp_config, stop_event):
        try:
            screen = None
            if hp_config:
                import mss
                screen = mss.mss()
            due = [time.monotonic() + i * 0.04 for i in range(len(VKS))]
            next_hp = time.monotonic()
            last_press = -1e12
            errors = 0
            while not stop_event.is_set():
                if not user32.IsWindow(hwnd):
                    self.root.after(0, lambda: self.status.set('Game đã đóng'))
                    break
                now = time.monotonic()
                if hp_config and now >= next_hp:
                    next_hp = now + 0.8
                    threshold, cooldown, rect = hp_config
                    if user32.GetForegroundWindow() == hwnd and not user32.IsIconic(hwnd):
                        try:
                            result = get_hp(rect, screen)
                            if result:
                                errors = 0
                                current, maximum = result
                                percent = 100 * current / maximum
                                self.root.after(0, lambda c=current, m=maximum, p=percent: self.hp_status.set(f'HP: {c}/{m} ({p:.1f}%)'))
                                if percent <= threshold and now-last_press >= cooldown:
                                    if self.send_key(hwnd, 0x73, stop_event):  # F4
                                        last_press = time.monotonic()
                            else:
                                errors += 1
                                if errors % 5 == 1:
                                    self.root.after(0, lambda: self.hp_status.set('Không đọc được HP; không bơm máu'))
                        except Exception as exc:
                            errors += 1
                            if errors % 5 == 1:
                                self.root.after(0, lambda e=str(exc): self.hp_status.set('Lỗi OCR: ' + e[:70]))
                    else:
                        self.root.after(0, lambda: self.hp_status.set('Đưa game ra phía trước để đọc HP'))
                for i, vk in enumerate(VKS):
                    if stop_event.is_set():
                        break
                    if active[i] and now >= due[i]:
                        self.send_key(hwnd, vk, stop_event)
                        due[i] = time.monotonic() + delays[i]
                stop_event.wait(0.02)
        except Exception as exc:
            if not self.closing:
                self.root.after(0, lambda e=str(exc): self.status.set('Lỗi: ' + e[:100]))
        finally:
            if screen is not None:
                screen.close()
            if not self.closing:
                self.root.after(0, lambda: self.finish_worker(stop_event))

    def finish_worker(self, event):
        if self.stop_event is event:
            self.running = False
            if not self.status.get().startswith('Lỗi'):
                self.status.set('Đã dừng')

    def stop(self):
        if self.stop_event:
            self.stop_event.set()
        self.running = False
        if not self.closing:
            self.status.set('Đã dừng | F1 khi chọn cửa sổ AutoSkill')

    def close(self):
        self.closing = True
        self.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    AutoSkill(root)
    root.mainloop()

if __name__ == '__main__':
    main()
