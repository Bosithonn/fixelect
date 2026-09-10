"""
Minimalist, modern Windows 11 Fluent Dark UI for Fixelect.
Features:
- Anti-aliased curved buttons, pill badges, and Fluent card containers
- Razor-sharp native Segoe UI typography with Per-Monitor High-DPI V2 ClearType rendering
- SetupWindow: 680px wide hardware auto-detection, interactive model selection, and live downloader
- DashboardWindow: 750px wide dual uniform mode cards, live playground, and preferences
"""

import ctypes
import os
import pathlib
import queue
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
import math
from PIL import Image, ImageDraw, ImageTk, ImageFont

# Ensure tools directory is in sys.path
_tools_dir = pathlib.Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from config import (
    load_config,
    save_config,
    is_auto_start_enabled,
    set_auto_start,
    get_resource_path,
    get_hotkey_keycaps,
    get_hotkey_label,
)
from hardware import detect_hardware
from downloader import MODELS, download_model, resolve_model

# Enable AppUserModelID, High-DPI Awareness and Dark Mode preferences immediately
if sys.platform == "win32":
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Fixelect.App.1.0")
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    try:
        uxtheme = ctypes.windll.uxtheme
        SetPreferredAppMode = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int)((135, uxtheme))
        SetPreferredAppMode(2)  # ForceDark
        FlushMenuThemes = ctypes.WINFUNCTYPE(None)((136, uxtheme))
        FlushMenuThemes()
    except Exception:
        pass

# Color Palette: Deep Midnight Navy & Brand Electric Blue (matched to official brand logo)
BG_DARK = "#070B19"
SURFACE_CARD = "#0F162E"
SURFACE_CARD_HOVER = "#151F42"
BORDER_COLOR = "#1D2852"
BORDER_HIGHLIGHT = "#2D3E7A"
ACCENT_BLUE = "#1D68FE"        # Brand electric blue
ACCENT_BLUE_HOVER = "#2D74FE"
ACCENT_BLUE_ACTIVE = "#1554D6"
BRAND_RED = "#FF334B"          # Brand coral red
BRAND_RED_HOVER = "#FF4D62"
BRAND_RED_ACTIVE = "#E0253C"
ACCENT_GREEN = "#10B981"
ACCENT_GREEN_BG = "#0B261E"
ACCENT_GREEN_BORDER = "#125940"
TEXT_PRIMARY = "#FFFFFF"
TEXT_MUTED = "#8E9BB5"
TEXT_DIM = "#5F6C87"
BADGE_BG = "#162042"
BADGE_BORDER = "#223260"
ENTRY_BG = "#0A1024"
ENTRY_BORDER = "#1D2852"

# Premium Native Typography (Segoe UI with native ClearType subpixel rendering)
FONT_APP_TITLE = ("Segoe UI", 16, "bold")
FONT_TITLE = ("Segoe UI", 13, "bold")
FONT_HEADING = ("Segoe UI Semibold", 11)
FONT_SUBTITLE = ("Segoe UI", 9)
FONT_BODY = ("Segoe UI", 9)
FONT_BODY_BOLD = ("Segoe UI Semibold", 9)
FONT_SMALL = ("Segoe UI", 8)
FONT_SMALL_BOLD = ("Segoe UI Semibold", 8)
FONT_MONO = ("Consolas", 9, "bold")


def enable_dark_titlebar(hwnd):
    """Enable Windows 10/11 native immersive dark titlebar."""
    if sys.platform != "win32":
        return
    try:
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        val = ctypes.c_int(1)
        res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(val), ctypes.sizeof(val)
        )
        if res != 0:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 19, ctypes.byref(val), ctypes.sizeof(val)
            )
    except Exception:
        pass


def apply_window_icon(root_window):
    """
    Apply official Fixelect brand icon to window titlebar, taskbar, Alt-Tab,
    and override the Win32 window class icon to completely prevent the default
    Tkinter blue feather icon from showing on Windows 10/11 taskbars.
    """
    ico_path = get_resource_path("resources/app_icon.ico")
    png_path = get_resource_path("resources/app_icon.png")

    # 1. Tkinter standard icon methods
    if ico_path.is_file():
        try:
            root_window.iconbitmap(str(ico_path))
        except Exception:
            pass

    if png_path.is_file():
        try:
            photo = ImageTk.PhotoImage(file=str(png_path))
            root_window._brand_icon_ref = photo  # keep reference alive to prevent GC
            root_window.wm_iconphoto(True, photo)
        except Exception:
            pass

    # 2. Win32 deep integration (sets taskbar, titlebar, and overwrites Tk class icon)
    if sys.platform == "win32" and ico_path.is_file():
        try:
            user32 = ctypes.windll.user32
            WM_SETICON = 0x0080
            ICON_SMALL = 0
            ICON_BIG = 1
            GCLP_HICON = -14
            GCLP_HICONSM = -34

            # Force process AppUserModelID if not already set
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Fixelect.App.1.0")
            except Exception:
                pass

            root_window.update_idletasks()
            hwnd = root_window.winfo_id()
            parent_hwnd = user32.GetParent(hwnd) or hwnd

            h16 = user32.LoadImageW(0, str(ico_path), 1, 16, 16, 0x00000010)
            h32 = user32.LoadImageW(0, str(ico_path), 1, 32, 32, 0x00000010)
            if not h32:
                h32 = user32.LoadImageW(0, str(ico_path), 1, 0, 0, 0x00000010 | 0x00000040)
            if not h16:
                h16 = user32.LoadImageW(0, str(ico_path), 1, 0, 0, 0x00000010 | 0x00000040)

            for target in (hwnd, parent_hwnd):
                if target:
                    if h32:
                        user32.SendMessageW(target, WM_SETICON, ICON_BIG, h32)
                    if h16:
                        user32.SendMessageW(target, WM_SETICON, ICON_SMALL, h16)
                    # CRITICAL: Overwrite the TkTopLevel class icon so Windows Taskbar NEVER shows the feather!
                    try:
                        if h32:
                            user32.SetClassLongPtrW(target, GCLP_HICON, h32)
                        if h16:
                            user32.SetClassLongPtrW(target, GCLP_HICONSM, h16)
                    except Exception:
                        try:
                            if h32:
                                user32.SetClassLongA(target, GCLP_HICON, h32)
                            if h16:
                                user32.SetClassLongA(target, GCLP_HICONSM, h16)
                        except Exception:
                            pass
        except Exception:
            pass



class CurvedButton(tk.Label):
    """
    Curved anti-aliased pill/rounded button.
    Renders 3x supersampled backgrounds via Pillow for razor-sharp, smooth curves.
    Supports icon="gear" with mathematically centered vector gear + text rendering.
    """
    def __init__(self, parent, text="", command=None, width=160, height=36, radius=10,
                 bg_color=ACCENT_BLUE, hover_color=ACCENT_BLUE_HOVER, active_color=ACCENT_BLUE_ACTIVE,
                 disabled_bg="#12182E", text_color="#FFFFFF", disabled_fg="#4E5A74",
                 font=FONT_BODY_BOLD, border_color=None, border_width=1,
                 parent_bg=BG_DARK, cursor="hand2", icon=None, **kwargs):
        self.btn_text = text
        self.command = command
        self.btn_w = width
        self.btn_h = height
        self.radius = radius
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.active_color = active_color
        self.disabled_bg = disabled_bg
        self.text_color = text_color
        self.disabled_fg = disabled_fg
        self.font = font
        self.border_color = border_color
        self.border_width = border_width
        self.parent_bg = parent_bg
        self.icon = icon
        self._state = tk.NORMAL
        self._is_pressed = False

        self._render_images()
        super().__init__(
            parent,
            image=self._img_normal,
            text="" if self.icon else text,
            compound="center",
            fg=self.text_color,
            font=font,
            bg=parent_bg,
            cursor=cursor,
            **kwargs
        )

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _make_round_rect(self, fill, outline, fg_color=None):
        if fg_color is None:
            fg_color = self.text_color
        scale = 3
        sw, sh = int(self.btn_w * scale), int(self.btn_h * scale)
        img = Image.new("RGBA", (sw, sh), self.parent_bg)
        draw = ImageDraw.Draw(img)
        bw = int(self.border_width * scale) if outline else 0
        draw.rounded_rectangle(
            [0, 0, sw - 1, sh - 1],
            radius=int(self.radius * scale),
            fill=fill,
            outline=outline or fill,
            width=bw,
        )

        if self.icon == "gear" and self.btn_text:
            font_size = 9
            if isinstance(self.font, tuple) and len(self.font) >= 2:
                font_size = self.font[1]
            try:
                pil_font = ImageFont.truetype("seguisb.ttf", int(font_size * scale))
            except Exception:
                try:
                    pil_font = ImageFont.truetype("segoeuib.ttf", int(font_size * scale))
                except Exception:
                    pil_font = ImageFont.load_default()

            bbox = draw.textbbox((0, 0), self.btn_text, font=pil_font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]

            gear_size = int(13 * scale)
            gap = int(8 * scale)
            total_w = gear_size + gap + tw
            start_x = (sw - total_w) / 2

            cx = start_x + gear_size / 2
            cy = sh / 2
            r_outer = gear_size / 2
            r_inner = r_outer * 0.72
            r_hole = r_outer * 0.35

            teeth = 8
            for i in range(teeth):
                angle = i * (2 * math.pi / teeth)
                tx = cx + (r_outer + 1.5 * scale) * math.cos(angle)
                ty = cy + (r_outer + 1.5 * scale) * math.sin(angle)
                draw.line(
                    [(cx + r_inner * math.cos(angle), cy + r_inner * math.sin(angle)), (tx, ty)],
                    fill=fg_color,
                    width=int(2.2 * scale)
                )

            draw.ellipse(
                [cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner],
                fill=fill,
                outline=fg_color,
                width=int(1.5 * scale)
            )
            draw.ellipse(
                [cx - r_hole, cy - r_hole, cx + r_hole, cy + r_hole],
                fill=fill,
                outline=fg_color,
                width=int(1.2 * scale)
            )

            text_x = start_x + gear_size + gap
            text_y = cy - th / 2 - bbox[1]
            draw.text((text_x, text_y), self.btn_text, font=pil_font, fill=fg_color)

        img = img.resize((self.btn_w, self.btn_h), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(img)

    def _render_images(self):
        self._img_normal = self._make_round_rect(self.bg_color, self.border_color, self.text_color)
        self._img_hover = self._make_round_rect(self.hover_color, self.border_color, self.text_color)
        self._img_active = self._make_round_rect(self.active_color, self.border_color, self.text_color)
        self._img_disabled = self._make_round_rect(self.disabled_bg, None, self.disabled_fg)

    def _on_enter(self, e):
        if self._state == tk.NORMAL:
            self.configure(image=self._img_hover)

    def _on_leave(self, e):
        self._is_pressed = False
        if self._state == tk.NORMAL:
            self.configure(image=self._img_normal)

    def _on_press(self, e):
        if self._state == tk.NORMAL:
            self._is_pressed = True
            self.configure(image=self._img_active)

    def _on_release(self, e):
        if self._state == tk.NORMAL and self._is_pressed:
            self._is_pressed = False
            self.configure(image=self._img_hover)
            if self.command:
                self.command()

    def set_text(self, text):
        self.btn_text = text
        if self.icon:
            self._render_images()
            if self._state == tk.NORMAL:
                self.configure(image=self._img_normal)
            else:
                self.configure(image=self._img_disabled)
        else:
            self.configure(text=text)

    def set_state(self, state):
        self._state = state
        if state == tk.DISABLED:
            self.configure(image=self._img_disabled, fg=self.disabled_fg, cursor="arrow")
        else:
            self.configure(image=self._img_normal, fg=self.text_color, cursor="hand2")

    def update_style(self, text=None, bg_color=None, hover_color=None, border_color=None):
        if text is not None:
            self.btn_text = text
            if not self.icon:
                self.configure(text=text)
        if bg_color is not None:
            self.bg_color = bg_color
        if hover_color is not None:
            self.hover_color = hover_color
        if border_color is not None:
            self.border_color = border_color
        self._render_images()
        if self._state == tk.NORMAL:
            self.configure(image=self._img_normal)



class FluentCard(tk.Frame):
    """
    Rock-solid Fluent card container based on tk.Frame.
    Guarantees 100% reliable layout propagation with zero collapse risk.
    """
    def __init__(self, parent, bg_color=SURFACE_CARD, border_color=BORDER_COLOR,
                 border_width=1, padx=16, pady=12, **kwargs):
        super().__init__(
            parent,
            bg=bg_color,
            highlightbackground=border_color,
            highlightcolor=border_color,
            highlightthickness=border_width,
            padx=padx,
            pady=pady,
            **kwargs
        )
        self.bg_color = bg_color
        self.border_color = border_color
        self.border_width = border_width

    def set_border(self, border_color, border_width=1, bg_color=None):
        self.border_color = border_color
        self.border_width = border_width
        self.configure(highlightbackground=border_color, highlightcolor=border_color, highlightthickness=border_width)
        if bg_color:
            self.bg_color = bg_color
            self.configure(bg=bg_color)
            for child in self.winfo_children():
                try:
                    if child.cget("bg") != BG_DARK and not isinstance(child, (CurvedButton, CurvedBadge, KeyCap)):
                        child.configure(bg=bg_color)
                except Exception:
                    pass


class CurvedBadge(tk.Label):
    """Small curved pill badge for status, sizes, or tags."""
    def __init__(self, parent, text="", bg_color=BADGE_BG, fg_color=TEXT_PRIMARY,
                 border_color=BADGE_BORDER, radius=8, height=22, min_width=45,
                 font=FONT_SMALL_BOLD, parent_bg=SURFACE_CARD, **kwargs):
        self.badge_text = text
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.border_color = border_color
        self.radius = radius
        self.h = height
        self.font = font
        self.parent_bg = parent_bg

        scale = 3
        try:
            f = tkfont.Font(font=font)
            text_w = f.measure(text)
        except Exception:
            text_w = len(text) * 7
        self.w = max(min_width, text_w + 18)

        img = Image.new("RGBA", (self.w * scale, self.h * scale), self.parent_bg)
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            [0, 0, self.w * scale - 1, self.h * scale - 1],
            radius=self.radius * scale,
            fill=self.bg_color,
            outline=self.border_color or self.bg_color,
            width=scale if self.border_color else 0,
        )
        img = img.resize((self.w, self.h), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(img)

        super().__init__(
            parent,
            image=self._photo,
            text=text,
            compound="center",
            fg=fg_color,
            font=font,
            bg=parent_bg,
            **kwargs
        )


class KeyCap(CurvedBadge):
    """Keyboard key indicator with rounded pill styling."""
    def __init__(self, parent, key_text="", parent_bg=SURFACE_CARD):
        super().__init__(
            parent,
            text=f" {key_text} ",
            bg_color="#182244",
            fg_color="#FFFFFF",
            border_color="#2A3866",
            radius=6,
            height=22,
            min_width=32,
            font=FONT_MONO,
            parent_bg=parent_bg,
        )


class CurvedProgressBar(tk.Frame):
    """Curved anti-aliased progress bar."""
    def __init__(self, parent, height=12, bg_color=ENTRY_BG, border_color=BORDER_COLOR,
                 fill_color=ACCENT_BLUE, parent_bg=BG_DARK, **kwargs):
        super().__init__(parent, bg=parent_bg, **kwargs)
        self.bar_h = height
        self.bg_color = bg_color
        self.border_color = border_color
        self.fill_color = fill_color
        self.parent_bg = parent_bg
        self.pct = 0.0

        self.canvas = tk.Canvas(self, height=height, bg=parent_bg, highlightthickness=0)
        self.canvas.pack(fill=tk.X, expand=True)
        self.canvas.bind("<Configure>", self._on_resize)
        self._cached_w = 0
        self._bg_photo = None

    def _on_resize(self, event):
        w = event.width
        if w < 10 or w == self._cached_w:
            return
        self._cached_w = w
        self._draw_bar()

    def set_progress(self, pct):
        self.pct = max(0.0, min(1.0, pct))
        self._draw_bar()

    def _draw_bar(self):
        w = self._cached_w
        h = self.bar_h
        if w < 10:
            return

        scale = 3
        sw, sh = w * scale, h * scale
        img = Image.new("RGBA", (sw, sh), self.parent_bg)
        draw = ImageDraw.Draw(img)
        radius = (sh // 2)

        # Draw track
        draw.rounded_rectangle([0, 0, sw - 1, sh - 1], radius=radius, fill=self.bg_color,
                               outline=self.border_color, width=scale)

        # Draw fill
        fill_w = int(sw * self.pct)
        if fill_w > radius * 2:
            draw.rounded_rectangle([0, 0, fill_w - 1, sh - 1], radius=radius, fill=self.fill_color)
        elif fill_w > 0:
            draw.rounded_rectangle([0, 0, fill_w - 1, sh - 1], radius=max(2, fill_w // 2), fill=self.fill_color)

        img = img.resize((w, h), Image.Resampling.LANCZOS)
        self._bg_photo = ImageTk.PhotoImage(img)
        self.canvas.delete("pbar")
        self.canvas.create_image(0, 0, anchor="nw", image=self._bg_photo, tags="pbar")


class SetupWindow:
    """
    First-run Onboarding & Model Downloader window.
    Supports both standalone (first run) and modal invocation from DashboardWindow.
    Detects hardware, allows 1-click model selection, and downloads with live progress.
    """

    def __init__(self, parent=None, on_complete=None):
        self.parent = parent
        self.on_complete = on_complete

        if parent:
            self.root = tk.Toplevel(parent)
            self.root.transient(parent)
        else:
            self.root = tk.Tk()

        self.root.title("Fixelect — Initial Setup")
        self.root.geometry("720x760")
        self.root.resizable(False, False)
        self.root.configure(bg=BG_DARK)

        # Center on screen or relative to parent
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        cx = (sw - 720) // 2
        cy = (sh - 760) // 2
        self.root.geometry(f"720x760+{cx}+{cy}")

        # Windows 11 Dark Titlebar & Official Brand Icon
        hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        enable_dark_titlebar(hwnd)
        apply_window_icon(self.root)
        self.root.bind("<Escape>", lambda e: self._finish() if not self.is_downloading else None)

        self.hw = detect_hardware()
        cfg = load_config()
        initial_profile = cfg.get("model_profile", self.hw.get("recommended_model", "3b"))
        self.selected_profile = tk.StringVar(value=initial_profile)
        self.is_downloading = False
        self.progress_queue = queue.Queue()
        self._after_id = None

        self._build_ui()
        self._poll_progress()

    def _poll_progress(self):
        if not self.root:
            return
        try:
            while True:
                kind, payload = self.progress_queue.get_nowait()
                if kind == "progress":
                    d, t, s = payload
                    self._update_progress(d, t, s)
                elif kind == "complete":
                    self._on_download_complete()
                elif kind == "error":
                    e = payload
                    self.is_downloading = False
                    self.progress_label.config(text=f"Download error: {e}", fg="#EF4444")
                    self.btn_action.set_text("Retry Download")
                    self.btn_action.set_state(tk.NORMAL)
        except queue.Empty:
            pass
        except Exception:
            pass

        if self.root:
            try:
                self._after_id = self.root.after(40, self._poll_progress)
            except Exception:
                pass

    def _build_ui(self):
        main_frame = tk.Frame(self.root, bg=BG_DARK, padx=24, pady=16)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Brand Logo Header
        logo_path = get_resource_path("resources/brand_logo_setup.png")
        if not logo_path.is_file():
            logo_path = get_resource_path("resources/brand_logo_dashboard.png")
        if logo_path.is_file():
            try:
                self.logo_img = ImageTk.PhotoImage(Image.open(logo_path))
                tk.Label(
                    main_frame,
                    image=self.logo_img,
                    bg=BG_DARK,
                ).pack(anchor="center", pady=(0, 4))
            except Exception:
                tk.Label(
                    main_frame,
                    text="Fixelect",
                    font=FONT_APP_TITLE,
                    fg=TEXT_PRIMARY,
                    bg=BG_DARK,
                ).pack(anchor="center", pady=(0, 4))
        else:
            tk.Label(
                main_frame,
                text="Fixelect",
                font=FONT_APP_TITLE,
                fg=TEXT_PRIMARY,
                bg=BG_DARK,
            ).pack(anchor="center", pady=(0, 4))

        tk.Label(
            main_frame,
            text="Zero-dependency local AI grammar correction & executive polish.",
            font=FONT_SUBTITLE,
            fg=TEXT_MUTED,
            bg=BG_DARK,
        ).pack(anchor="center", pady=(0, 10))

        # Hardware Detection Card (FluentCard)
        self.hw_card = FluentCard(main_frame, padx=16, pady=8)
        self.hw_card.pack(fill=tk.X, pady=(0, 10))

        backend = self.hw["backend"].upper()
        device_name = self.hw["gpu_name"]
        vram = f" • {self.hw['vram_gb']} GB VRAM" if self.hw.get("vram_gb") else ""
        ram = f" • {self.hw['ram_gb']} GB RAM"

        tk.Label(
            self.hw_card,
            text=f"⚡ Hardware Detected: {device_name}",
            font=FONT_BODY_BOLD,
            fg=ACCENT_GREEN,
            bg=SURFACE_CARD,
        ).pack(anchor="w")

        tk.Label(
            self.hw_card,
            text=f"Backend: {backend}{vram}{ram} • Zero cloud transmission",
            font=FONT_BODY,
            fg=TEXT_MUTED,
            bg=SURFACE_CARD,
        ).pack(anchor="w", pady=(2, 0))

        # Model Recommendation Section Header
        tk.Label(
            main_frame,
            text="SELECT INFERENCE MODEL (CLICK CARD TO SWITCH):",
            font=FONT_BODY_BOLD,
            fg=TEXT_MUTED,
            bg=BG_DARK,
        ).pack(anchor="w", pady=(0, 6))

        # Scrollable Cards Area
        cards_container = tk.Frame(main_frame, bg=BG_DARK)
        cards_container.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        canvas = tk.Canvas(
            cards_container,
            bg=BG_DARK,
            highlightthickness=0,
            bd=0,
        )
        scrollbar = tk.Scrollbar(cards_container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.cards_frame = tk.Frame(canvas, bg=BG_DARK)
        cards_window = canvas.create_window((0, 0), window=self.cards_frame, anchor="nw")

        def _on_canvas_configure(event):
            canvas.itemconfig(cards_window, width=event.width)

        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        self.cards_frame.bind("<Configure>", _on_frame_configure)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_mousewheel(widget):
            widget.bind("<MouseWheel>", _on_mousewheel)
            for child in widget.winfo_children():
                _bind_mousewheel(child)

        canvas.bind("<MouseWheel>", _on_mousewheel)

        self.card_widgets = {}
        curr_p = self.selected_profile.get()

        for k, spec in MODELS.items():
            is_sel = (curr_p == k)
            card = FluentCard(
                self.cards_frame,
                border_color=ACCENT_BLUE if is_sel else BORDER_COLOR,
                border_width=2 if is_sel else 1,
                bg_color=SURFACE_CARD_HOVER if is_sel else SURFACE_CARD,
                padx=16,
                pady=10,
                cursor="hand2",
            )
            card.pack(fill=tk.X, pady=(0, 8))

            row = tk.Frame(card, bg=card.bg_color, cursor="hand2")
            row.pack(fill=tk.X)

            # Badges packed from right to left
            is_ready = resolve_model(k) is not None
            if is_ready:
                CurvedBadge(row, text="✓ READY ON DISK", bg_color=ACCENT_GREEN_BG,
                            fg_color=ACCENT_GREEN, border_color=ACCENT_GREEN_BORDER,
                            radius=7, height=22, min_width=115, parent_bg=card.bg_color).pack(side=tk.RIGHT, padx=(6, 0))

            if k == self.hw.get("recommended_model"):
                rec_label = "RECOMMENDED (GPU)" if self.hw.get("is_gpu") else "RECOMMENDED (CPU)"
                CurvedBadge(row, text=rec_label, bg_color=ACCENT_GREEN_BG,
                            fg_color=ACCENT_GREEN, border_color=ACCENT_GREEN_BORDER,
                            radius=7, height=22, min_width=140, parent_bg=card.bg_color).pack(side=tk.RIGHT, padx=(6, 0))
            elif spec.get("badge_rec"):
                CurvedBadge(row, text=spec["badge_rec"], bg_color=BADGE_BG,
                            fg_color=TEXT_MUTED, border_color=BADGE_BORDER,
                            radius=7, height=22, min_width=110, parent_bg=card.bg_color).pack(side=tk.RIGHT, padx=(6, 0))

            CurvedBadge(row, text=spec.get("badge_size", ""), bg_color=BADGE_BG,
                        fg_color=TEXT_PRIMARY, border_color=BADGE_BORDER,
                        radius=7, height=22, min_width=50, parent_bg=card.bg_color).pack(side=tk.RIGHT, padx=(0, 4))

            rb_ind = tk.Label(
                row,
                text="●" if is_sel else "○",
                font=("Segoe UI", 12, "bold"),
                fg=ACCENT_BLUE if is_sel else TEXT_MUTED,
                bg=card.bg_color,
                cursor="hand2",
                anchor="w",
            )
            rb_ind.pack(side=tk.LEFT, padx=(0, 8))

            lbl_title = tk.Label(
                row,
                text=spec.get("short_name", spec["name"]),
                font=FONT_HEADING,
                fg=TEXT_PRIMARY,
                bg=card.bg_color,
                cursor="hand2",
                anchor="w",
            )
            lbl_title.pack(side=tk.LEFT)

            desc = tk.Label(
                card,
                text=spec.get("desc", ""),
                font=FONT_BODY,
                fg=TEXT_MUTED,
                bg=card.bg_color,
                wraplength=620,
                justify=tk.LEFT,
                cursor="hand2",
                anchor="w",
            )
            desc.pack(anchor="w", pady=(3, 0), padx=(26, 0))

            self.card_widgets[k] = {
                "card": card,
                "row": row,
                "rb_ind": rb_ind,
                "lbl_title": lbl_title,
                "desc": desc,
            }

            for w in [card, row, rb_ind, lbl_title, desc]:
                w.bind("<Button-1>", lambda e, p=k: self._select_profile(p))

        _bind_mousewheel(self.cards_frame)

        # Progress Area
        self.progress_frame = tk.Frame(main_frame, bg=BG_DARK)
        self.progress_frame.pack(fill=tk.X, pady=(0, 10))

        self.progress_label = tk.Label(
            self.progress_frame,
            text="",
            font=FONT_BODY,
            fg=TEXT_MUTED,
            bg=BG_DARK,
        )
        self.progress_label.pack(anchor="w", pady=(0, 6))

        # Smooth Curved progress bar
        self.progress_bar = CurvedProgressBar(self.progress_frame, height=12)
        self.progress_bar.pack(fill=tk.X)

        # Full-width Curved Action Button (672px x 44px, radius=12)
        self.btn_action = CurvedButton(
            main_frame,
            text="Download & Start Fixelect",
            command=self._start_download,
            width=672,
            height=44,
            radius=12,
            bg_color=ACCENT_BLUE,
            hover_color=ACCENT_BLUE_HOVER,
            active_color=ACCENT_BLUE_ACTIVE,
            font=("Segoe UI", 11, "bold"),
        )
        self.btn_action.pack(anchor="center", pady=(6, 0))

        # Initial style setup
        self._on_profile_change()

    def _select_profile(self, profile):
        if self.is_downloading:
            return
        self.selected_profile.set(profile)
        cfg = load_config()
        cfg["model_profile"] = profile
        save_config(cfg)
        self._on_profile_change()

    def _on_profile_change(self):
        if self.is_downloading:
            return
        curr_p = self.selected_profile.get()

        for k, widgets in self.card_widgets.items():
            is_sel = (k == curr_p)
            card = widgets["card"]
            card_bg = SURFACE_CARD_HOVER if is_sel else SURFACE_CARD
            card_border = ACCENT_BLUE if is_sel else BORDER_COLOR
            card_bw = 2 if is_sel else 1
            card.set_border(card_border, border_width=card_bw, bg_color=card_bg)

            widgets["rb_ind"].config(
                text="●" if is_sel else "○",
                fg=ACCENT_BLUE if is_sel else TEXT_MUTED,
                bg=card_bg,
            )
            widgets["row"].config(bg=card_bg)
            widgets["lbl_title"].config(bg=card_bg)
            widgets["desc"].config(bg=card_bg)

        existing = resolve_model(curr_p)
        spec = MODELS.get(curr_p) or MODELS.get("3b", {})
        sname = spec.get("short_name", curr_p.upper())

        if existing:
            self.progress_label.config(
                text=f"✓ {sname} model is already downloaded & ready on your disk.",
                fg=ACCENT_GREEN,
            )
            self.progress_bar.set_progress(1.0)
            self.btn_action.set_text(f"Apply & Launch Fixelect ({sname} Ready)")
            self.btn_action.set_state(tk.NORMAL)
            self.btn_action.command = self._finish
        else:
            approx = spec.get("approx_mb", "1000")
            self.progress_label.config(
                text=f"Ready to download {sname} (~{approx} MB) from Hugging Face.",
                fg=TEXT_MUTED,
            )
            self.progress_bar.set_progress(0.0)
            self.btn_action.set_text(f"Download {sname} & Launch Fixelect")
            self.btn_action.set_state(tk.NORMAL)
            self.btn_action.command = self._start_download


    def _update_progress(self, downloaded, total, speed):
        pct = (downloaded / total) if total else 0.0
        dl_mb = downloaded / (1024 * 1024)
        tot_mb = total / (1024 * 1024) if total else 0
        spd_mb = speed / (1024 * 1024) if speed else 0
        eta = (total - downloaded) / speed if speed and total else 0

        self.progress_label.config(
            text=f"Downloading model: {dl_mb:.0f} MB / {tot_mb:.0f} MB ({pct*100:.1f}%) • {spd_mb:.1f} MB/s • ETA: {eta:.0f}s"
        )
        self.progress_bar.set_progress(pct)
        self.root.update_idletasks()

    def _start_download(self):
        if self.is_downloading:
            return
        self.is_downloading = True
        self.btn_action.set_text("Downloading... Please wait")
        self.btn_action.set_state(tk.DISABLED)

        profile = self.selected_profile.get()
        cfg = load_config()
        cfg["model_profile"] = profile
        save_config(cfg)

        def worker():
            try:
                download_model(
                    profile=profile,
                    progress_callback=lambda d, t, s: self.progress_queue.put(("progress", (d, t, s)))
                )
                self.progress_queue.put(("complete", None))
            except Exception as e:
                self.progress_queue.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_download_complete(self):
        self.progress_label.config(text="✓ Model downloaded and verified successfully!", fg=ACCENT_GREEN)
        self.progress_bar.set_progress(1.0)
        self.root.after(800, self._finish)

    def _finish(self):
        if hasattr(self, "_after_id") and self._after_id and self.root:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass
        if self.root:
            r = self.root
            self.root = None
            try:
                r.destroy()
            except Exception:
                pass
        if self.on_complete:
            self.on_complete()

    def show(self):
        if isinstance(self.root, tk.Tk):
            self.root.mainloop()
        else:
            self.root.lift()
            self.root.focus_force()
            self.root.grab_set()


class DashboardWindow:
    """
    Modern Minimalist Windows 11 Fluent Dashboard & Live Playground.
    Spacious 750px layout with smooth curved cards, keycaps, and action buttons.
    """

    def __init__(self, fix_fn=None, on_quit=None, hotkey_listener=None):
        self.fix_fn = fix_fn
        self.on_quit = on_quit
        self.hotkey_listener = hotkey_listener
        self.root = None
        self.hw = detect_hardware()
        self.config = load_config()
        self.result_queue = queue.Queue()
        self._after_id = None
        self.badge_fix = None
        self.badge_pol = None
        self.btn_fix = None
        self.btn_polish = None
        self.trigger_mode_var = None
        self.custom_fix_var = None
        self.custom_pol_var = None
        self.custom_frame = None

    def show(self):
        if self.root and tk.Tcl().eval(f"info exists {self.root}"):
            self.root.lift()
            self.root.focus_force()
            return

        self.root = tk.Tk()
        self.root.title("Fixelect Dashboard & Settings")
        self.root.geometry("750x880")
        self.root.resizable(False, False)
        self.root.configure(bg=BG_DARK)

        # Center on screen
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        cx = (sw - 750) // 2
        cy = (sh - 880) // 2
        self.root.geometry(f"750x880+{cx}+{cy}")

        # Windows 11 Dark Titlebar & Official Brand Icon
        hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        enable_dark_titlebar(hwnd)
        apply_window_icon(self.root)
        try:
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.SwitchToThisWindow(hwnd, True)
        except Exception:
            pass

        self._build_ui()
        self._poll_results()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Escape>", lambda e: self._on_close())
        self.root.mainloop()

    def _poll_results(self):
        if not self.root:
            return
        try:
            while True:
                res, ms = self.result_queue.get_nowait()
                self.output_box.config(state=tk.NORMAL)
                self.output_box.delete("1.0", tk.END)
                self.output_box.insert("1.0", res)
                self.output_box.config(state=tk.DISABLED)

                self.latency_label.config(text=f"⚡ {ms:.0f}ms ({self.hw['backend'].upper()})", fg=ACCENT_GREEN)
                self.btn_fix.set_state(tk.NORMAL)
                self.btn_polish.set_state(tk.NORMAL)
        except queue.Empty:
            pass
        except Exception:
            pass

        if self.root:
            try:
                self._after_id = self.root.after(40, self._poll_results)
            except Exception:
                pass

    def _build_ui(self):
        main = tk.Frame(self.root, bg=BG_DARK, padx=24, pady=16)
        main.pack(fill=tk.BOTH, expand=True)

        # Footer Row: Packed FIRST with side=tk.BOTTOM so it is ALWAYS pinned to the bottom of the client window
        footer = tk.Frame(main, bg=BG_DARK)
        footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))

        CurvedButton(
            footer,
            text="Quit Fixelect",
            command=self._handle_quit,
            width=110,
            height=34,
            radius=8,
            bg_color=SURFACE_CARD,
            hover_color="#2A1420",
            border_color="#3A1D28",
            text_color="#FF4D62",
            font=FONT_BODY,
            parent_bg=BG_DARK,
        ).pack(side=tk.LEFT)

        CurvedButton(
            footer,
            text="Terms & Privacy",
            command=self._show_terms_and_privacy,
            width=130,
            height=34,
            radius=8,
            bg_color=SURFACE_CARD,
            hover_color=SURFACE_CARD_HOVER,
            border_color=BORDER_COLOR,
            text_color=TEXT_MUTED,
            font=FONT_BODY,
            parent_bg=BG_DARK,
        ).pack(side=tk.LEFT, padx=(8, 0))

        CurvedButton(
            footer,
            text="Protected Terms",
            command=self._show_custom_words_manager,
            width=135,
            height=34,
            radius=8,
            bg_color=SURFACE_CARD,
            hover_color=SURFACE_CARD_HOVER,
            border_color=BORDER_COLOR,
            text_color=TEXT_MUTED,
            font=FONT_BODY,
            parent_bg=BG_DARK,
        ).pack(side=tk.LEFT, padx=(8, 0))

        CurvedButton(
            footer,
            text="Hide to System Tray",
            command=self._on_close,
            width=165,
            height=34,
            radius=8,
            bg_color=ACCENT_BLUE,
            hover_color=ACCENT_BLUE_HOVER,
            active_color=ACCENT_BLUE_ACTIVE,
            text_color="#FFFFFF",
            font=FONT_BODY_BOLD,
            parent_bg=BG_DARK,
        ).pack(side=tk.RIGHT)

        # Header Row: Brand Logo on left, Model Setup button & Active Status Pill on right
        header = tk.Frame(main, bg=BG_DARK)
        header.pack(fill=tk.X, pady=(0, 10))

        logo_path = get_resource_path("resources/brand_logo_dashboard.png")
        if logo_path.is_file():
            try:
                self.logo_img = ImageTk.PhotoImage(Image.open(logo_path))
                tk.Label(header, image=self.logo_img, bg=BG_DARK).pack(side=tk.LEFT)
            except Exception:
                tk.Label(header, text="Fixelect", font=FONT_APP_TITLE, fg=TEXT_PRIMARY, bg=BG_DARK).pack(side=tk.LEFT)
        else:
            tk.Label(header, text="Fixelect", font=FONT_APP_TITLE, fg=TEXT_PRIMARY, bg=BG_DARK).pack(side=tk.LEFT)

        # Status Pill (Curved)
        status_pill = CurvedBadge(
            header,
            text=f"● Active ({self.hw['backend'].upper()})",
            bg_color=ACCENT_GREEN_BG,
            fg_color=ACCENT_GREEN,
            border_color=ACCENT_GREEN_BORDER,
            radius=8,
            height=32,
            min_width=120,
            font=FONT_BODY_BOLD,
            parent_bg=BG_DARK,
        )
        status_pill.pack(side=tk.RIGHT)

        # Setup Button (Curved with mathematically centered vector gear icon)
        btn_setup = CurvedButton(
            header,
            text="Model & Hardware Setup",
            icon="gear",
            command=self._open_setup_window,
            width=200,
            height=32,
            radius=8,
            bg_color=SURFACE_CARD,
            hover_color=SURFACE_CARD_HOVER,
            border_color=BORDER_COLOR,
            text_color=TEXT_PRIMARY,
            font=FONT_BODY_BOLD,
            parent_bg=BG_DARK,
        )
        btn_setup.pack(side=tk.RIGHT, padx=(0, 10))

        # Hardware & Model Specs Bar (FluentCard)
        specs_bar = FluentCard(main, padx=14, pady=8)
        specs_bar.pack(fill=tk.X, pady=(0, 12))

        gpu_txt = f"{self.hw['gpu_name']} ({self.hw['vram_gb']} GB VRAM)" if self.hw.get("vram_gb") else self.hw['gpu_name']
        m_prof = self.config.get("model_profile", "3b")
        model_txt = MODELS.get(m_prof, {}).get("short_name", m_prof.upper())
        self.specs_label = tk.Label(
            specs_bar,
            text=f"⚡ {gpu_txt}  •  Model: {model_txt}  •  RAM: {self.hw['ram_gb']} GB",
            font=FONT_BODY_BOLD,
            fg=ACCENT_GREEN,
            bg=SURFACE_CARD,
        )
        self.specs_label.pack(side=tk.LEFT)

        # --- SECTION 1: DUAL-MODE GUIDE CARDS (FluentCard, Exactly 50/50 Uniform Width) ---
        modes_row = tk.Frame(main, bg=BG_DARK)
        modes_row.pack(fill=tk.X, pady=(0, 12))
        modes_row.grid_columnconfigure(0, weight=1, uniform="modes")
        modes_row.grid_columnconfigure(1, weight=1, uniform="modes")

        # Mode A: Fix (Electric Blue theme)
        card_fix = FluentCard(modes_row, border_color=ACCENT_BLUE, padx=14, pady=12)
        card_fix.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        self.badge_fix = tk.Frame(card_fix, bg=SURFACE_CARD)
        self.badge_fix.pack(anchor="w", pady=(0, 6))
        self._render_keycaps(self.badge_fix, "fix")

        tk.Label(
            card_fix,
            text="Default Fix Mode",
            font=FONT_HEADING,
            fg=TEXT_PRIMARY,
            bg=SURFACE_CARD,
        ).pack(anchor="w")

        tk.Label(
            card_fix,
            text="Fixes typos, mis-keys & grammar instantly. 100% preserves your words, tone, and slang.",
            font=FONT_BODY,
            fg=TEXT_MUTED,
            bg=SURFACE_CARD,
            wraplength=275,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(4, 0))

        # Mode B: Polish (Coral Red theme)
        card_pol = FluentCard(modes_row, border_color=BRAND_RED, padx=14, pady=12)
        card_pol.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        self.badge_pol = tk.Frame(card_pol, bg=SURFACE_CARD)
        self.badge_pol.pack(anchor="w", pady=(0, 6))
        self._render_keycaps(self.badge_pol, "polish")

        tk.Label(
            card_pol,
            text="Professional Polish",
            font=FONT_HEADING,
            fg=TEXT_PRIMARY,
            bg=SURFACE_CARD,
        ).pack(anchor="w")

        tk.Label(
            card_pol,
            text="Elevates rough thoughts into articulate, executive prose with smooth transitions and active voice.",
            font=FONT_BODY,
            fg=TEXT_MUTED,
            bg=SURFACE_CARD,
            wraplength=275,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(4, 0))

        # --- SECTION 2: INTERACTIVE LIVE PLAYGROUND (FluentCard) ---
        pg_card = FluentCard(main, padx=16, pady=12)
        pg_card.pack(fill=tk.X, pady=(0, 12))

        tk.Label(
            pg_card,
            text="LIVE PLAYGROUND (TEST INSTANTLY):",
            font=FONT_BODY_BOLD,
            fg=TEXT_MUTED,
            bg=SURFACE_CARD,
        ).pack(anchor="w", pady=(0, 6))

        self.input_box = tk.Text(
            pg_card,
            height=3,
            bg=ENTRY_BG,
            fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            font=FONT_BODY,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            padx=10,
            pady=6,
        )
        self.input_box.pack(fill=tk.X, pady=(0, 8))
        self.input_box.insert("1.0", "tobehonest its kinda really strannge an i don know what s hapenning")
        self.input_box.bind("<Control-Return>", lambda e: (self._run_test("fix"), "break")[1])
        self.input_box.bind("<Shift-Control-Return>", lambda e: (self._run_test("polish"), "break")[1])
        self.input_box.bind("<Control-Shift-Return>", lambda e: (self._run_test("polish"), "break")[1])

        # Buttons row
        btn_row = tk.Frame(pg_card, bg=SURFACE_CARD)
        btn_row.pack(fill=tk.X, pady=(0, 8))

        lbl_fix = f"Test Fix ({get_hotkey_label('fix', self.config)})"
        lbl_pol = f"Test Polish ({get_hotkey_label('polish', self.config)})"

        self.btn_fix = CurvedButton(
            btn_row,
            text=lbl_fix,
            command=lambda: self._run_test("fix"),
            width=175,
            height=34,
            radius=8,
            bg_color=ACCENT_BLUE,
            hover_color=ACCENT_BLUE_HOVER,
            active_color=ACCENT_BLUE_ACTIVE,
            font=FONT_BODY_BOLD,
            parent_bg=SURFACE_CARD,
        )
        self.btn_fix.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_polish = CurvedButton(
            btn_row,
            text=lbl_pol,
            command=lambda: self._run_test("polish"),
            width=175,
            height=34,
            radius=8,
            bg_color=BRAND_RED,
            hover_color=BRAND_RED_HOVER,
            active_color=BRAND_RED_ACTIVE,
            font=FONT_BODY_BOLD,
            parent_bg=SURFACE_CARD,
        )
        self.btn_polish.pack(side=tk.LEFT)

        self.latency_label = tk.Label(
            btn_row,
            text="",
            font=FONT_BODY_BOLD,
            fg=ACCENT_GREEN,
            bg=SURFACE_CARD,
        )
        self.latency_label.pack(side=tk.RIGHT)

        # Output Box
        self.output_box = tk.Text(
            pg_card,
            height=3,
            bg=ENTRY_BG,
            fg=TEXT_PRIMARY,
            font=FONT_BODY,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            padx=10,
            pady=6,
            state=tk.DISABLED,
        )
        self.output_box.pack(fill=tk.X)

        tk.Label(
            pg_card,
            text="Tip: Press Ctrl+Enter to test Fix, or Shift+Ctrl+Enter for Polish",
            font=FONT_SMALL,
            fg=TEXT_MUTED,
            bg=SURFACE_CARD,
        ).pack(anchor="w", pady=(6, 0))

        # --- SECTION 3: PREFERENCES & SHORTCUTS (FluentCard) ---
        pref_card = FluentCard(main, padx=16, pady=10)
        pref_card.pack(fill=tk.X, pady=(0, 14))

        tk.Label(
            pref_card,
            text="ACTIVATION TRIGGER & HOTKEYS:",
            font=FONT_BODY_BOLD,
            fg=TEXT_MUTED,
            bg=SURFACE_CARD,
        ).pack(anchor="w", pady=(0, 6))

        self.trigger_mode_var = tk.StringVar(value=self.config.get("trigger_mode", "double_tap"))
        self.custom_fix_var = tk.StringVar(value=self.config.get("custom_fix", "<ctrl>+<alt>+f"))
        self.custom_pol_var = tk.StringVar(value=self.config.get("custom_polish", "<ctrl>+<alt>+p"))

        presets_frame = tk.Frame(pref_card, bg=SURFACE_CARD)
        presets_frame.pack(fill=tk.X, pady=(0, 2))

        presets = [
            ("double_tap", "Double-Tap Modifiers (Alt x2 Fix  •  Ctrl x2 Polish) — Recommended"),
            ("alt_space", "Alt + Space (Alt Space Fix  •  Alt Shift Space Polish)"),
            ("classic", "Classic 3-Key (Ctrl + Alt + F Fix  •  Ctrl + Alt + P Polish)"),
            ("custom", "Custom Shortcuts..."),
        ]

        for val, label in presets:
            rb = tk.Radiobutton(
                presets_frame,
                text=label,
                variable=self.trigger_mode_var,
                value=val,
                command=self._on_trigger_mode_change,
                font=FONT_BODY,
                fg=TEXT_PRIMARY,
                bg=SURFACE_CARD,
                activebackground=SURFACE_CARD,
                activeforeground=TEXT_PRIMARY,
                selectcolor=BG_DARK,
                highlightthickness=0,
                bd=0,
            )
            rb.pack(anchor="w", pady=1)

        # Custom inputs frame (collapsed by default unless mode is custom)
        self.custom_frame = tk.Frame(pref_card, bg=SURFACE_CARD)

        c_row = tk.Frame(self.custom_frame, bg=SURFACE_CARD)
        c_row.pack(fill=tk.X, pady=(4, 2))

        tk.Label(c_row, text="Fix Key:", font=FONT_SMALL_BOLD, fg=TEXT_MUTED, bg=SURFACE_CARD).pack(side=tk.LEFT, padx=(0, 4))
        entry_cfix = tk.Entry(
            c_row,
            textvariable=self.custom_fix_var,
            font=FONT_BODY,
            width=16,
            bg=ENTRY_BG,
            fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
        )
        entry_cfix.pack(side=tk.LEFT, ipady=3, padx=(0, 12))

        tk.Label(c_row, text="Polish Key:", font=FONT_SMALL_BOLD, fg=TEXT_MUTED, bg=SURFACE_CARD).pack(side=tk.LEFT, padx=(0, 4))
        entry_cpol = tk.Entry(
            c_row,
            textvariable=self.custom_pol_var,
            font=FONT_BODY,
            width=16,
            bg=ENTRY_BG,
            fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
        )
        entry_cpol.pack(side=tk.LEFT, ipady=3, padx=(0, 10))

        CurvedButton(
            c_row,
            text="Apply",
            command=self._save_trigger_mode,
            width=75,
            height=28,
            radius=6,
            bg_color=ACCENT_BLUE,
            hover_color=ACCENT_BLUE_HOVER,
            active_color=ACCENT_BLUE_ACTIVE,
            font=FONT_SMALL_BOLD,
            parent_bg=SURFACE_CARD,
        ).pack(side=tk.LEFT)

        if self.trigger_mode_var.get() == "custom":
            self.custom_frame.pack(fill=tk.X, pady=(2, 4))

        # Divider between shortcuts and general preferences
        sep = tk.Frame(pref_card, height=1, bg=BORDER_COLOR)
        sep.pack(fill=tk.X, pady=(6, 6))

        tk.Label(
            pref_card,
            text="SYSTEM PREFERENCES:",
            font=FONT_SMALL_BOLD,
            fg=TEXT_MUTED,
            bg=SURFACE_CARD,
        ).pack(anchor="w", pady=(0, 4))

        self.sound_var = tk.BooleanVar(value=self.config.get("sound_enabled", True))
        chk_sound = tk.Checkbutton(
            pref_card,
            text="Play subtle audio chime when text is corrected",
            variable=self.sound_var,
            command=self._save_prefs,
            font=FONT_BODY,
            fg=TEXT_PRIMARY,
            bg=SURFACE_CARD,
            activebackground=SURFACE_CARD,
            activeforeground=TEXT_PRIMARY,
            selectcolor=BG_DARK,
            highlightthickness=0,
            bd=0,
        )
        chk_sound.pack(anchor="w", pady=(0, 2))

        self.start_var = tk.BooleanVar(value=is_auto_start_enabled())
        chk_start = tk.Checkbutton(
            pref_card,
            text="Launch Fixelect automatically on Windows startup",
            variable=self.start_var,
            command=self._save_prefs,
            font=FONT_BODY,
            fg=TEXT_PRIMARY,
            bg=SURFACE_CARD,
            activebackground=SURFACE_CARD,
            activeforeground=TEXT_PRIMARY,
            selectcolor=BG_DARK,
            highlightthickness=0,
            bd=0,
        )
        chk_start.pack(anchor="w")

    def _show_terms_and_privacy(self):
        """Display the offline privacy guarantee, terms of use, and open-source licenses."""
        modal = tk.Toplevel(self.root)
        modal.title("Fixelect — Terms of Use & Privacy Guarantee")
        modal.geometry("680x620")
        modal.resizable(False, False)
        modal.configure(bg=BG_DARK)
        modal.transient(self.root)
        modal.grab_set()

        self.root.update_idletasks()
        rx = self.root.winfo_x()
        ry = self.root.winfo_y()
        modal.geometry(f"680x620+{rx+35}+{ry+35}")

        hwnd = ctypes.windll.user32.GetParent(modal.winfo_id()) or modal.winfo_id()
        enable_dark_titlebar(hwnd)
        apply_window_icon(modal)
        modal.bind("<Escape>", lambda e: modal.destroy())

        box = tk.Frame(modal, bg=BG_DARK, padx=20, pady=16)
        box.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            box,
            text="Privacy Guarantee & Terms of Use",
            font=FONT_TITLE,
            fg=TEXT_PRIMARY,
            bg=BG_DARK,
        ).pack(anchor="w", pady=(0, 2))

        tk.Label(
            box,
            text="Author: Bositxon Erkinxonov • 100% Offline • Zero Telemetry • Open Source (MIT / Apache 2.0)",
            font=FONT_SMALL_BOLD,
            fg=ACCENT_GREEN,
            bg=BG_DARK,
        ).pack(anchor="w", pady=(0, 10))

        # Bottom row packed first so Close button is never cut off
        btn_close = CurvedButton(
            box,
            text="Close",
            command=modal.destroy,
            width=110,
            height=34,
            radius=8,
            bg_color=ACCENT_BLUE,
            hover_color=ACCENT_BLUE_HOVER,
            active_color=ACCENT_BLUE_ACTIVE,
            text_color="#FFFFFF",
            font=FONT_BODY_BOLD,
            parent_bg=BG_DARK,
        )
        btn_close.pack(side=tk.BOTTOM, anchor="e", pady=(10, 0))

        frame_txt = tk.Frame(box, bg=SURFACE_CARD, highlightthickness=1, highlightbackground=BORDER_COLOR)
        frame_txt.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(frame_txt)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        txt = tk.Text(
            frame_txt,
            wrap=tk.WORD,
            bg=ENTRY_BG,
            fg=TEXT_PRIMARY,
            font=("Consolas", 9),
            padx=10,
            pady=10,
            relief=tk.FLAT,
            yscrollcommand=scrollbar.set,
        )
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=txt.yview)

        content = []
        priv_path = get_resource_path("PRIVACY_POLICY.md")
        if priv_path.is_file():
            content.append(priv_path.read_text(encoding="utf-8"))
        lic_path = get_resource_path("LICENSE.txt")
        if lic_path.is_file():
            content.append("\n" + "=" * 60 + "\n")
            content.append(lic_path.read_text(encoding="utf-8"))

        if not content:
            content = ["Fixelect is 100% offline and collects zero telemetry or user data."]

        txt.insert("1.0", "".join(content))
        txt.config(state=tk.DISABLED)

    def _show_custom_words_manager(self):
        """Display a modal dialog allowing the user to view and add protected words to words.txt."""
        modal = tk.Toplevel(self.root)
        modal.title("Fixelect — Protected Words & Whitelist")
        modal.geometry("560x520")
        modal.resizable(False, False)
        modal.configure(bg=BG_DARK)
        modal.transient(self.root)
        modal.grab_set()

        self.root.update_idletasks()
        rx = self.root.winfo_x()
        ry = self.root.winfo_y()
        modal.geometry(f"560x520+{rx+95}+{ry+80}")

        hwnd = ctypes.windll.user32.GetParent(modal.winfo_id()) or modal.winfo_id()
        enable_dark_titlebar(hwnd)
        apply_window_icon(modal)
        modal.bind("<Escape>", lambda e: modal.destroy())

        box = tk.Frame(modal, bg=BG_DARK, padx=22, pady=16)
        box.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            box,
            text="Protected Words & Custom Whitelist",
            font=FONT_TITLE,
            fg=TEXT_PRIMARY,
            bg=BG_DARK,
        ).pack(anchor="w", pady=(0, 2))

        tk.Label(
            box,
            text="Fixelect will NEVER modify, alter, or correct these words (names, jargon, acronyms).",
            font=FONT_SUBTITLE,
            fg=TEXT_MUTED,
            bg=BG_DARK,
            wraplength=510,
            justify=tk.LEFT,
            anchor="w",
        ).pack(anchor="w", pady=(0, 12))

        # Bottom row: "Done" button packed FIRST with side=tk.BOTTOM so it is ALWAYS visible
        CurvedButton(
            box,
            text="Done",
            command=modal.destroy,
            width=90,
            height=32,
            radius=6,
            bg_color=SURFACE_CARD,
            hover_color=SURFACE_CARD_HOVER,
            border_color=BORDER_COLOR,
            text_color=TEXT_PRIMARY,
            font=FONT_BODY_BOLD,
            parent_bg=BG_DARK,
        ).pack(side=tk.BOTTOM, anchor="e", pady=(10, 0))

        # Add Term Row
        add_row = tk.Frame(box, bg=BG_DARK)
        add_row.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))

        entry_word = tk.Entry(
            add_row,
            font=FONT_BODY,
            bg=ENTRY_BG,
            fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
        )
        entry_word.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, padx=(0, 8))

        # Words List Frame with Scrollbar
        list_frame = tk.Frame(box, bg=SURFACE_CARD, highlightthickness=1, highlightbackground=BORDER_COLOR)
        list_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        txt_words = tk.Text(
            list_frame,
            bg=ENTRY_BG,
            fg=TEXT_PRIMARY,
            font=FONT_BODY,
            padx=10,
            pady=8,
            relief=tk.FLAT,
            yscrollcommand=scrollbar.set,
        )
        txt_words.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=txt_words.yview)

        def refresh_words():
            txt_words.config(state=tk.NORMAL)
            txt_words.delete("1.0", tk.END)
            try:
                from check_guard import PROTECTED_WORDS
                sorted_list = sorted(list(PROTECTED_WORDS))
                txt_words.insert("1.0", "\n".join(sorted_list))
            except Exception:
                pass
            txt_words.config(state=tk.DISABLED)

        def on_add():
            val = entry_word.get().strip()
            if val:
                try:
                    from check_guard import add_protected_word
                    add_protected_word(val)
                except Exception:
                    pass
                entry_word.delete(0, tk.END)
                refresh_words()

        CurvedButton(
            add_row,
            text="Add Term",
            command=on_add,
            width=100,
            height=32,
            radius=6,
            bg_color=ACCENT_BLUE,
            hover_color=ACCENT_BLUE_HOVER,
            active_color=ACCENT_BLUE_ACTIVE,
            text_color="#FFFFFF",
            font=FONT_BODY_BOLD,
            parent_bg=BG_DARK,
        ).pack(side=tk.RIGHT)

        entry_word.bind("<Return>", lambda e: on_add())
        refresh_words()

    def _run_test(self, mode):
        text = self.input_box.get("1.0", tk.END).strip()
        if not text:
            self.latency_label.config(text="Please enter text above to test", fg=TEXT_MUTED)
            return

        self.latency_label.config(text="Thinking...", fg=TEXT_MUTED)
        self.btn_fix.set_state(tk.DISABLED)
        self.btn_polish.set_state(tk.DISABLED)

        def worker():
            t0 = time.time()
            fn = self.fix_fn
            if fn is None:
                try:
                    from check_guard import load_pipeline
                    from config import load_config
                    cfg = load_config()
                    m_prof = cfg.get("model_profile", "3b")
                    pipe = load_pipeline(m_prof, engine_type="embedded")
                    fn = lambda t, mode="fix": pipe(t, mode=mode)
                    self.fix_fn = fn
                except Exception as e:
                    res = f"Engine Error: {e}"
                    ms = (time.time() - t0) * 1000
                    self.result_queue.put((res, ms))
                    return

            try:
                res_tuple = fn(text, mode=mode)
                if isinstance(res_tuple, tuple):
                    res = res_tuple[0]
                else:
                    res = str(res_tuple)
            except Exception as e:
                res = f"Error: {e}"
            ms = (time.time() - t0) * 1000
            self.result_queue.put((res, ms))

        threading.Thread(target=worker, daemon=True).start()

    def _render_keycaps(self, parent_frame, mode):
        if not parent_frame:
            return
        for w in parent_frame.winfo_children():
            w.destroy()
        caps = get_hotkey_keycaps(mode, self.config)
        for key in caps:
            KeyCap(parent_frame, key_text=key).pack(side=tk.LEFT, padx=1)

    def _on_trigger_mode_change(self):
        mode = self.trigger_mode_var.get()
        if mode == "custom":
            self.custom_frame.pack(fill=tk.X, pady=(2, 4))
        else:
            self.custom_frame.pack_forget()
            self._save_trigger_mode()

    def _save_trigger_mode(self):
        mode = self.trigger_mode_var.get()
        self.config["trigger_mode"] = mode
        if mode == "custom":
            self.config["custom_fix"] = self.custom_fix_var.get().strip()
            self.config["custom_polish"] = self.custom_pol_var.get().strip()
        save_config(self.config)

        if self.hotkey_listener:
            try:
                self.hotkey_listener.reload(self.config)
            except Exception as e:
                print(f"Error reloading Windows hotkeys: {e}")

        # Refresh KeyCaps and Playground buttons
        self._render_keycaps(self.badge_fix, "fix")
        self._render_keycaps(self.badge_pol, "polish")
        if self.btn_fix:
            self.btn_fix.set_text(f"Test Fix ({get_hotkey_label('fix', self.config)})")
        if self.btn_polish:
            self.btn_polish.set_text(f"Test Polish ({get_hotkey_label('polish', self.config)})")

    def _save_prefs(self):
        self.config["sound_enabled"] = self.sound_var.get()
        save_config(self.config)
        set_auto_start(self.start_var.get())

    def _on_close(self):
        if hasattr(self, "_after_id") and self._after_id and self.root:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass
        if self.root:
            r = self.root
            self.root = None
            try:
                r.destroy()
            except Exception:
                pass

    def _open_setup_window(self):
        """Open the Hardware Auto-detection & Model Downloader window."""
        SetupWindow(parent=self.root, on_complete=self._refresh_after_setup).show()

    def _refresh_after_setup(self):
        """Refresh configuration and hardware specs after setup."""
        self.config = load_config()
        self.hw = detect_hardware()
        m_prof = self.config.get("model_profile", "3b")
        if hasattr(self, "specs_label") and self.specs_label:
            gpu_txt = f"{self.hw['gpu_name']} ({self.hw['vram_gb']} GB VRAM)" if self.hw.get("vram_gb") else self.hw['gpu_name']
            model_txt = MODELS.get(m_prof, {}).get("short_name", m_prof.upper())
            self.specs_label.config(text=f"⚡ {gpu_txt}  •  Model: {model_txt}  •  RAM: {self.hw['ram_gb']} GB")

        def preload_engine():
            try:
                from engine import get_default_engine
                eng = get_default_engine(model_profile=m_prof)
                eng.start()
            except Exception as e:
                print(f"Error starting new model: {e}")

        threading.Thread(target=preload_engine, daemon=True).start()

    def _handle_quit(self):
        self._on_close()
        if self.on_quit:
            self.on_quit()