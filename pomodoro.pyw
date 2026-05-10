"""
Pomodoro Timer - 番茄钟桌面应用
"""
import json
import os
import threading
import tkinter as tk
import winsound
from pathlib import Path

import customtkinter as ctk
from plyer import notification
from PIL import Image, ImageTk

CONFIG_DIR = Path(os.environ.get("APPDATA", ".")) / "PomodoroTimer"
CONFIG_FILE = CONFIG_DIR / "settings.json"
SOUND_FILE = CONFIG_DIR / "done.wav"

DEFAULT_SETTINGS = {
    "pomodoro": 25,
    "short_break": 5,
    "long_break": 15,
    "long_break_interval": 4,
    "always_on_top": False,
    "theme": "system",
    "sound_enabled": True,
    "wallpaper_pomodoro": "",
    "wallpaper_short_break": "",
    "wallpaper_long_break": "",
}

THEME_COLORS = {
    "pomodoro": {"fg": "#DC3545", "bg": "#2B0A0E", "progress": "#FF4757"},
    "short_break": {"fg": "#28A745", "bg": "#0B2B15", "progress": "#2ED573"},
    "long_break": {"fg": "#007BFF", "bg": "#082336", "progress": "#1E90FF"},
}

MODE_KEYS = ["pomodoro", "short_break", "long_break"]
MODE_LABELS = ["Pomodoro", "Short Break", "Long Break"]
MODE_STATUS = {
    "pomodoro": "\U0001f3af 专注时间",
    "short_break": "\U0001f33f 短休息",
    "long_break": "☕ 长休息",
}
MODE_NOTIFY = {
    "pomodoro": "专注时间到！休息一下吧 \U0001f33f",
    "short_break": "休息结束，继续专注 \U0001f680",
    "long_break": "长休息结束，准备下一轮 \U0001f4aa",
}


def _read_json(path, default=None):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


class Settings:
    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.data = dict(DEFAULT_SETTINGS)
        self._load()

    def _load(self):
        data = _read_json(CONFIG_FILE)
        if data:
            self.data.update(data)

    def save(self):
        _write_json(CONFIG_FILE, self.data)

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value


class PomodoroTimer:
    def __init__(self, settings: Settings, on_tick=None, on_finish=None):
        self.settings = settings
        self.on_tick = on_tick
        self.on_finish = on_finish
        self.mode = "pomodoro"
        self.remaining = 0
        self.total = 0
        self.running = False
        self.paused = False
        self._timer = None
        self.session_count = 0
        self._load_session()

    @property
    def current_duration(self):
        return self.settings[self.mode] * 60

    def reset(self, mode=None):
        if mode:
            self.mode = mode
        self.running = False
        self.paused = False
        self.remaining = self.current_duration
        self.total = self.current_duration
        self._cancel_timer()
        if self.on_tick:
            self.on_tick()

    def start(self):
        if self.remaining <= 0:
            self.reset()
        self.running = True
        self.paused = False
        self._tick()

    def pause(self):
        self.paused = True
        self.running = False

    def resume(self):
        self.paused = False
        self.running = True
        self._tick()

    def toggle(self):
        if not self.running and not self.paused:
            self.start()
        elif self.running:
            self.pause()
        else:
            self.resume()

    def cancel(self):
        self.running = False
        self.paused = False
        self._cancel_timer()

    def _cancel_timer(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _tick(self):
        if not self.running or self.paused:
            return
        if self.remaining > 0:
            self.remaining -= 1
            if self.on_tick:
                self.on_tick()
            self._timer = threading.Timer(1, self._tick)
            self._timer.daemon = True
            self._timer.start()
        else:
            self.running = False
            self._handle_finish()

    def _handle_finish(self):
        self.session_count += 1
        self._save_session()
        if self.on_finish:
            self.on_finish()

    def format_time(self):
        m, s = divmod(max(0, self.remaining), 60)
        return f"{m:02d}:{s:02d}"

    @property
    def progress(self):
        if self.total == 0:
            return 0
        return 1 - (self.remaining / self.total)

    def switch_mode(self, mode):
        self.mode = mode
        self.reset()

    def _save_session(self):
        _write_json(CONFIG_DIR / "session.json", {"count": self.session_count})

    def _load_session(self):
        data = _read_json(CONFIG_DIR / "session.json")
        if data:
            self.session_count = data.get("count", 0)


class PomodoroApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.settings = Settings()
        self.title("\U0001f345 番茄钟")
        self._wallpaper_image = None
        self._overlay_canvas = None
        self._overlay_rect = None
        self._setup_window()

        self.timer = PomodoroTimer(
            self.settings,
            on_tick=lambda: self.after(0, self._update_display),
            on_finish=self._on_timer_finish,
        )

        self._build_ui()
        self._update_theme()
        self.timer.reset("pomodoro")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Configure>", self._on_window_resize)

    def _setup_window(self):
        ctk.set_appearance_mode(self.settings["theme"])
        self.geometry("420+{}+{}".format(
            (self.winfo_screenwidth() - 420) // 2,
            (self.winfo_screenheight() - 520) // 2,
        ))
        self.minsize(380, 480)
        self.configure(fg_color="#1A1A2E")
        self.attributes("-topmost", self.settings["always_on_top"])

        # Background canvas — draws wallpaper image, NOT a child of any CTk frame
        self.bg_canvas = tk.Canvas(self, highlightthickness=0, bg="#1A1A2E")
        self.bg_canvas.pack(fill="both", expand=True)
        self._wallpaper_canvas_item = None

    def _build_ui(self):
        # Main container frame placed directly on the bg_canvas
        self.main = ctk.CTkFrame(self.bg_canvas, fg_color=None, corner_radius=0)
        self.main.pack(fill="both", expand=True, padx=20, pady=20)

        self.mode_frame = ctk.CTkFrame(self.main, fg_color=None)
        self.mode_frame.pack(pady=(0, 15))
        self.mode_selector = ctk.CTkSegmentedButton(
            self.mode_frame,
            values=MODE_LABELS,
            command=self._on_mode_change,
            selected_color="#DC3545",
            selected_hover_color="#C82333",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.mode_selector.pack()

        # Display area —— use a CTkFrame with None bg so the wallpaper shows through
        self.display_frame = ctk.CTkFrame(self.main, fg_color=None, corner_radius=20)
        self.display_frame.pack(fill="both", expand=True, pady=10)

        self.canvas_size = 260
        self.progress_canvas = tk.Canvas(
            self.display_frame,
            width=self.canvas_size,
            height=self.canvas_size,
            bg="#1A1A2E",
            highlightthickness=0,
        )
        self.progress_canvas.pack(pady=(20, 5))

        self.time_label = ctk.CTkLabel(
            self.display_frame,
            text="25:00",
            font=ctk.CTkFont(size=64, weight="bold"),
            text_color="white",
        )
        self.time_label.place(relx=0.5, rely=0.48, anchor="center")

        self.status_label = ctk.CTkLabel(
            self.display_frame,
            text="专注时间",
            font=ctk.CTkFont(size=16),
            text_color="#8892B0",
        )
        self.status_label.place(relx=0.5, rely=0.65, anchor="center")

        self.session_var = ctk.StringVar(value="☕ 已完成: 0 个番茄")
        self.session_label = ctk.CTkLabel(
            self.display_frame,
            textvariable=self.session_var,
            font=ctk.CTkFont(size=13),
            text_color="#6C7A9D",
        )
        self.session_label.place(relx=0.5, rely=0.78, anchor="center")

        self.control_frame = ctk.CTkFrame(self.main, fg_color=None)
        self.control_frame.pack(pady=(15, 5))

        btn_font = ctk.CTkFont(size=15, weight="bold")
        self.start_btn = ctk.CTkButton(
            self.control_frame,
            text="▶  开始",
            width=140,
            height=45,
            corner_radius=25,
            font=btn_font,
            command=self._on_start,
        )
        self.start_btn.pack(side="left", padx=6)

        self.reset_btn = ctk.CTkButton(
            self.control_frame,
            text="⟳  重置",
            width=100,
            height=45,
            corner_radius=25,
            font=btn_font,
            fg_color="#2D3A5C",
            hover_color="#3D4A6C",
            command=self._on_reset,
        )
        self.reset_btn.pack(side="left", padx=6)

        self.settings_btn = ctk.CTkButton(
            self.control_frame,
            text="⚙",
            width=45,
            height=45,
            corner_radius=25,
            font=ctk.CTkFont(size=18),
            fg_color="#2D3A5C",
            hover_color="#3D4A6C",
            command=self._open_settings,
        )
        self.settings_btn.pack(side="left", padx=6)

        self._draw_bg_circle()

    def _draw_bg_circle(self):
        w = self.canvas_size
        cx = cy = w // 2
        self.progress_canvas.create_arc(
            cx - 105, cy - 105, cx + 105, cy + 105,
            start=90, extent=360,
            outline="#2D3A5C", width=10, style="arc",
            tags="bg",
        )

    def _draw_progress(self, progress):
        self.progress_canvas.delete("progress")
        if progress <= 0:
            return
        w = self.canvas_size
        cx = cy = w // 2
        self.progress_canvas.create_arc(
            cx - 105, cy - 105, cx + 105, cy + 105,
            start=90, extent=-360 * progress,
            outline=self._current_color["progress"], width=10, style="arc",
            tags="progress",
        )

    @property
    def _current_color(self):
        return THEME_COLORS.get(self.timer.mode, THEME_COLORS["pomodoro"])

    def _update_display(self):
        self.time_label.configure(text=self.timer.format_time())
        self._draw_progress(self.timer.progress)
        self.session_var.set(f"☕ 已完成: {self.timer.session_count} 个番茄")

    def _load_wallpaper(self, path):
        if self._wallpaper_canvas_item:
            self.bg_canvas.delete(self._wallpaper_canvas_item)
            self._wallpaper_canvas_item = None
        self._wallpaper_image = None

        if path and os.path.isfile(path):
            try:
                img = Image.open(path)
                w = self.winfo_width() or 420
                h = self.winfo_height() or 520
                img = img.resize((w, h), Image.LANCZOS)
                self._wallpaper_image = ImageTk.PhotoImage(img)
                self._wallpaper_canvas_item = self.bg_canvas.create_image(
                    0, 0, anchor="nw", image=self._wallpaper_image
                )
                self.bg_canvas.tag_lower(self._wallpaper_canvas_item)
            except Exception:
                pass

        # Toggle semi-transparent overlay for text readability
        self._toggle_overlay(path and os.path.isfile(path))

    def _toggle_overlay(self, active):
        if self._overlay_rect:
            self.bg_canvas.delete(self._overlay_rect)
            self._overlay_rect = None
        if active:
            w = self.winfo_width() or 420
            h = self.winfo_height() or 520
            self._overlay_rect = self.bg_canvas.create_rectangle(
                0, 0, w, h,
                fill="#0A0A1E", stipple="gray25", tags="overlay",
            )
            self.bg_canvas.tag_lower(self._overlay_rect)
            if self._wallpaper_canvas_item:
                self.bg_canvas.tag_raise(self._wallpaper_canvas_item, self._overlay_rect)
        self.progress_canvas.configure(bg="#0A0A1E" if active else "#1A1A2E")

    def _on_window_resize(self, event):
        if event.widget is not self:
            return
        if getattr(self, '_resize_timer', None):
            self.after_cancel(self._resize_timer)
        self._resize_timer = self.after(200, self._reload_wallpaper)

    def _reload_wallpaper(self):
        self._load_wallpaper(self.settings.data.get(f"wallpaper_{self.timer.mode}", ""))

    def _on_timer_finish(self):
        self.after(0, self._on_finish_ui)

    def _on_finish_ui(self):
        self._update_display()
        self._notify_user()
        self._auto_switch_mode()

    def _notify_user(self):
        msg = MODE_NOTIFY.get(self.timer.mode, "时间到！")

        if self.settings["sound_enabled"]:
            self._play_sound()

        try:
            notification.notify(
                title="\U0001f345 番茄钟",
                message=msg,
                timeout=5,
            )
        except Exception:
            pass

        self.attributes("-topmost", True)
        self.after(2000, lambda: self.attributes(
            "-topmost", self.settings["always_on_top"]
        ))

    def _play_sound(self):
        def _play():
            try:
                winsound.PlaySound(str(SOUND_FILE), winsound.SND_FILENAME)
            except Exception:
                try:
                    for _ in range(3):
                        winsound.Beep(880, 300)
                except Exception:
                    pass
        threading.Thread(target=_play, daemon=True).start()

    def _auto_switch_mode(self):
        if self.timer.mode == "pomodoro":
            count_since_long = self.timer.session_count % self.settings["long_break_interval"]
            if count_since_long == 0:
                self._switch_to("long_break")
            else:
                self._switch_to("short_break")
        else:
            self._switch_to("pomodoro")
        self.timer.start()

    def _switch_to(self, mode):
        idx = MODE_KEYS.index(mode)
        self.mode_selector.set(MODE_LABELS[idx])
        self.timer.switch_mode(mode)
        self._update_theme()

    def _on_mode_change(self, value):
        mapping = {
            "Pomodoro": "pomodoro",
            "Short Break": "short_break",
            "Long Break": "long_break",
        }
        mode = mapping.get(value, "pomodoro")
        self.timer.switch_mode(mode)
        self._update_theme()

    def _update_theme(self):
        mode = self.timer.mode
        colors = THEME_COLORS[mode]
        self.mode_selector.configure(
            selected_color=colors["fg"],
            selected_hover_color=colors["fg"],
        )

        self.time_label.configure(text_color=colors["fg"])

        self.start_btn.configure(fg_color=colors["fg"], hover_color=colors["fg"])

        self.status_label.configure(text=MODE_STATUS[mode])
        self._load_wallpaper(self.settings.data.get(f"wallpaper_{mode}", ""))
        self._update_display()

    def _on_start(self):
        if self.timer.paused:
            self.timer.resume()
            self.start_btn.configure(text="⏸  暂停")
        elif self.timer.running:
            self.timer.pause()
            self.start_btn.configure(text="▶  继续")
        else:
            self.timer.start()
            self.start_btn.configure(text="⏸  暂停")

    def _on_reset(self):
        self.timer.reset()
        self.start_btn.configure(text="▶  开始")
        self._update_display()

    def _open_settings(self):
        SettingsDialog(self)

    def _on_close(self):
        self.timer.cancel()
        self.destroy()


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.settings = app.settings
        self.title("设置")
        self.geometry("380+{}+{}".format(
            app.winfo_x() + 20, app.winfo_y() + 80
        ))
        self.resizable(False, False)
        self.transient(app)
        self.grab_set()
        self._build()

    def _build(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        row = 0
        ctk.CTkLabel(frame, text="⏱  时长设置", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=row, column=0, columnspan=2, pady=(0, 10), sticky="w"
        )

        fields = [
            ("专注时间 (分钟):", "pomodoro"),
            ("短休息 (分钟):", "short_break"),
            ("长休息 (分钟):", "long_break"),
            ("长休息间隔 (番茄数):", "long_break_interval"),
        ]

        self.entries = {}
        for label, key in fields:
            row += 1
            ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(size=13)).grid(
                row=row, column=0, padx=(0, 10), pady=6, sticky="w"
            )
            var = ctk.StringVar(value=str(self.settings[key]))
            entry = ctk.CTkEntry(
                frame, width=80, textvariable=var,
                font=ctk.CTkFont(size=13), justify="center",
            )
            entry.grid(row=row, column=1, pady=6, sticky="e")
            self.entries[key] = var

        row += 1
        self.top_var = ctk.BooleanVar(value=self.settings["always_on_top"])
        ctk.CTkCheckBox(
            frame, text="窗口置顶", variable=self.top_var,
            font=ctk.CTkFont(size=13),
        ).grid(row=row, column=0, columnspan=2, pady=(10, 5), sticky="w")

        row += 1
        self.sound_var = ctk.BooleanVar(value=self.settings["sound_enabled"])
        ctk.CTkCheckBox(
            frame, text="完成时播放声音", variable=self.sound_var,
            font=ctk.CTkFont(size=13),
        ).grid(row=row, column=0, columnspan=2, pady=5, sticky="w")

        row += 1
        ctk.CTkLabel(frame, text="主题:", font=ctk.CTkFont(size=13)).grid(
            row=row, column=0, padx=(0, 10), pady=(10, 5), sticky="w"
        )
        theme_map = {"system": "跟随系统", "light": "浅色", "dark": "深色"}
        self.theme_var = ctk.StringVar(value=theme_map.get(self.settings["theme"], "跟随系统"))
        theme_menu = ctk.CTkOptionMenu(
            frame,
            values=["跟随系统", "浅色", "深色"],
            variable=self.theme_var,
            font=ctk.CTkFont(size=13),
        )
        theme_menu.grid(row=row, column=1, pady=(10, 5), sticky="e")

        row += 1
        ctk.CTkLabel(frame, text="🖼  自定义壁纸", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=row, column=0, columnspan=2, pady=(15, 5), sticky="w"
        )

        wallpapers = [
            ("专注模式:", "wallpaper_pomodoro"),
            ("短休息:", "wallpaper_short_break"),
            ("长休息:", "wallpaper_long_break"),
        ]
        self.wallpaper_vars = {}
        for label, key in wallpapers:
            row += 1
            ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(size=13)).grid(
                row=row, column=0, padx=(0, 10), pady=4, sticky="w"
            )
            var = ctk.StringVar(value=self.settings.data.get(key, ""))
            self.wallpaper_vars[key] = var
            btn = ctk.CTkButton(
                frame, text="选择图片...", width=80,
                font=ctk.CTkFont(size=11),
                command=lambda k=key, v=var: self._pick_wallpaper(k, v),
            )
            btn.grid(row=row, column=1, pady=4, sticky="e")
            clear_btn = ctk.CTkButton(
                frame, text="✕", width=30,
                fg_color="#5A3D3D", hover_color="#7A4D4D",
                font=ctk.CTkFont(size=13),
                command=lambda v=var: v.set(""),
            )
            clear_btn.grid(row=row, column=2, padx=(4, 0), pady=4, sticky="e")

        row += 1
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.grid(row=row, column=0, columnspan=3, pady=(20, 0))
        ctk.CTkButton(
            btn_frame, text="保存", width=100,
            command=self._save, font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_frame, text="取消", width=100,
            fg_color="#2D3A5C", hover_color="#3D4A6C",
            command=self.destroy, font=ctk.CTkFont(size=13),
        ).pack(side="left", padx=5)

    def _save(self):
        try:
            for key in MODE_KEYS:
                val = int(self.entries[key].get())
                if val < 1 or val > 999:
                    raise ValueError
                self.settings.data[key] = val

            interval = int(self.entries["long_break_interval"].get())
            if interval < 1:
                raise ValueError
            self.settings.data["long_break_interval"] = interval

            self.settings.data["always_on_top"] = self.top_var.get()
            self.settings.data["sound_enabled"] = self.sound_var.get()

            for key in ["wallpaper_pomodoro", "wallpaper_short_break", "wallpaper_long_break"]:
                self.settings.data[key] = self.wallpaper_vars[key].get()

            theme_map = {"跟随系统": "system", "浅色": "light", "深色": "dark"}
            new_theme = theme_map.get(self.theme_var.get(), "system")
            if new_theme != self.settings.data["theme"]:
                self.settings.data["theme"] = new_theme
                ctk.set_appearance_mode(new_theme)

            self.settings.save()
            self.app.attributes("-topmost", self.settings.data["always_on_top"])
            self.app.timer.reset()
            self.app._update_theme()
            self.destroy()
        except ValueError:
            import tkinter.messagebox as mb
            mb.showerror("输入错误", "请输入有效的正整数！", parent=self)

    def _pick_wallpaper(self, key, var):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            parent=self,
            title="选择壁纸图片",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.bmp *.gif"), ("所有文件", "*.*")],
        )
        if path:
            var.set(path)


if __name__ == "__main__":
    app = PomodoroApp()
    app.mainloop()
