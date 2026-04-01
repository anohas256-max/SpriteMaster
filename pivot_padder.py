import os
import sys
import math
import json
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk, ImageDraw, ImageOps
import customtkinter as ctk

# --- Базовые пресеты (только чтение) ---
STATIC_PRESETS = {
    "128 x 128 (Квадрат)": (128, 128),
    "256 x 256 (Квадрат+)": (256, 256),
    "128 x 256 (Вертикальный)": (128, 256),
    "256 x 128 (Горизонтальный)": (256, 128),
    "64 x 256 (Узкий длинный)": (64, 256),
    "128 x 384 (Пропорция 1:3)": (128, 384),
    "128 x 512 (Для мечей)": (128, 512)
}

MODES = [
    {"name": "Расширять холст (Без обрезки)", "color": "#2fa572", "hover": "#25825a"},
    {"name": "Сжимать картинку (Под пресет)", "color": "#1f6aa5", "hover": "#144870"},
    {"name": "Обрезать лишнее (Жестко)", "color": "#b84b4b", "hover": "#8f3a3a"}
]

TRANSPARENT_RGBA = (0, 0, 0, 0)
RESAMPLE_LANCZOS = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS
RESAMPLE_BICUBIC = Image.Resampling.BICUBIC if hasattr(Image, 'Resampling') else Image.BICUBIC
RESAMPLE_NEAREST = Image.Resampling.NEAREST if hasattr(Image, 'Resampling') else Image.NEAREST

class SpriteMasterProApp(ctk.CTk):
    def __init__(self, folder_path):
        super().__init__()
        self.title("Sprite Master Pro 11.2: UI Flow Fixed")
        self.geometry("1400x900")

        self.folder_path = folder_path
        self.images = [f for f in os.listdir(folder_path) if f.lower().endswith('.png')]
        if not self.images:
            messagebox.showerror("Ошибка", "В папке нет PNG файлов!")
            sys.exit()

        # --- СИСТЕМА ГЛОБАЛЬНОГО СОХРАНЕНИЯ ---
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_file = os.path.join(base_dir, "sprite_master_config.json")
        self.load_settings()

        # Применяем тему
        ctk.set_appearance_mode(self.user_settings["theme"])
        ctk.set_default_color_theme("blue")

        self.current_index = 0
        self.source_img = None         
        self.processed_img = None      
        
        self.source_pivot_x = 0; self.source_pivot_y = 0
        self.pivot_viz_size = self.user_settings["pivot_viz_size"]
        
        self.current_angle = 0
        self.mirrored = False
        self.autocropped = False
        
        self.tr_crop_x = 0; self.tr_crop_y = 0; self.tr_scale = 1.0
        
        self.view_zoom = 1.0           
        self.loupe_zoom = self.user_settings["loupe_zoom"]
        self.res_zoom = 1.0 
        
        self.current_mode_idx = self.user_settings["mode_idx"]
        self.is_animating = False
        self.preview_angle = 0
        self.dyn_rot_id = None
        self.loupe_locked = False
        
        self.undo_stack = []
        self.max_undo_steps = 10
        self.guidelines = [] 
        
        self.user_presets = self.user_settings["custom_presets"]
        self.refresh_preset_combo_values()
        
        self.preset_choice = self.user_settings["preset"]
        if self.preset_choice not in self.all_presets_dict:
            self.preset_choice = list(self.all_presets_dict.keys())[0]
        self.target_w, self.target_h = self.all_presets_dict[self.preset_choice]
        
        self.final_out_w, self.final_out_h = self.target_w, self.target_h
        self.canvas_bg = self.user_settings["canvas_bg"]
        self.pivot_color = self.get_pivot_color(self.canvas_bg)

        self.setup_ui()
        self.bind_events()
        self.load_next_image()

    def load_settings(self):
        self.user_settings = {
            "theme": "Dark",
            "canvas_bg": "#3b3b3b",
            "preset": "128 x 128 (Квадрат)",
            "mode_idx": 0,
            "loupe_zoom": 5.0,
            "pivot_viz_size": 4.0,
            "custom_presets": [] 
        }
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    loaded = json.load(f)
                    self.user_settings.update(loaded)
            except: pass

    def save_settings(self):
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.user_settings, f)
        except: pass

    def get_pivot_color(self, bg_hex):
        if bg_hex in ["#ffffff", "#d6d6d6", "#ffb6c1"]: 
            return "#ff0000" 
        else: 
            return "#00ffcc" 

    def refresh_preset_combo_values(self):
        self.all_presets_dict = STATIC_PRESETS.copy()
        for p in self.user_presets:
            name = p["name"]
            w, h = p["w"], p["h"]
            full_name = f"👤 {name} ({w} x {h})"
            self.all_presets_dict[full_name] = (w, h)
        self.preset_names_list = list(self.all_presets_dict.keys())

    # --- UI ---
    def setup_ui(self):
        # --- ВЕРХНЯЯ ПАНЕЛЬ ИНСТРУМЕНТОВ ---
        self.toolbar = ctk.CTkFrame(self, corner_radius=0)
        self.toolbar.pack(side=tk.TOP, fill=tk.X, padx=0, pady=0, ipadx=10, ipady=5)

        settings_frame = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        settings_frame.pack(side=tk.LEFT, padx=10)
        self.btn_settings = ctk.CTkButton(settings_frame, text="⚙️ Настройки", width=30, command=self.open_settings)
        self.btn_settings.pack(pady=2)

        # 2. Пресеты (Теперь всё управление здесь)
        info_frame = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        info_frame.pack(side=tk.LEFT, padx=10)
        
        ctk.CTkLabel(info_frame, text="Пресет (Размер):", font=ctk.CTkFont(weight="bold")).pack(anchor=tk.W)
        
        combo_row = ctk.CTkFrame(info_frame, fg_color="transparent")
        combo_row.pack(anchor=tk.W, pady=2)
        
        self.preset_combo = ctk.CTkComboBox(combo_row, values=self.preset_names_list, width=180, command=self.on_preset_change)
        self.preset_combo.set(self.preset_choice) 
        self.preset_combo.pack(side=tk.LEFT)
        
        self.btn_del_preset = ctk.CTkButton(combo_row, text="−", width=28, fg_color="#b84b4b", hover_color="#8f3a3a", command=self.remove_custom_preset)
        self.btn_del_preset.pack(side=tk.LEFT, padx=5)

        # Мини-строка добавления пресета
        add_row = ctk.CTkFrame(info_frame, fg_color="transparent")
        add_row.pack(anchor=tk.W, pady=2)
        
        self.custom_w = ctk.CTkEntry(add_row, placeholder_text="Ш", width=45, height=24)
        self.custom_w.pack(side=tk.LEFT)
        ctk.CTkLabel(add_row, text="x").pack(side=tk.LEFT, padx=2)
        self.custom_h = ctk.CTkEntry(add_row, placeholder_text="В", width=45, height=24)
        self.custom_h.pack(side=tk.LEFT)
        self.custom_name = ctk.CTkEntry(add_row, placeholder_text="Имя", width=85, height=24)
        self.custom_name.pack(side=tk.LEFT, padx=4)
        self.btn_add_preset = ctk.CTkButton(add_row, text="+", width=28, height=24, command=self.add_custom_preset)
        self.btn_add_preset.pack(side=tk.LEFT)

        self.file_label = ctk.CTkLabel(info_frame, text="Файл: ...", font=ctk.CTkFont(size=11))
        self.file_label.pack(anchor=tk.W)

        # 3. Режимы
        tools_frame = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        tools_frame.pack(side=tk.LEFT, padx=10)
        m = MODES[self.current_mode_idx]
        self.btn_mode = ctk.CTkButton(tools_frame, text=f"Режим: {m['name']}", command=self.cycle_mode, 
                                      fg_color=m['color'], hover_color=m['hover'], text_color="white", width=220)
        self.btn_mode.pack(pady=2)
        self.btn_crop = ctk.CTkButton(tools_frame, text="✂ Обрезать пустой фон (Action)", command=self.action_autocrop, 
                                      fg_color="#a86032", hover_color="#854c27", width=220)
        self.btn_crop.pack(pady=2)

        # 4. Вращение
        rot_frame = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        rot_frame.pack(side=tk.LEFT, padx=10)
        ctk.CTkLabel(rot_frame, text="Трансформация (Сохр. в Ctrl+Z):", font=ctk.CTkFont(weight="bold")).pack(pady=2)
        
        rot_btns = ctk.CTkFrame(rot_frame, fg_color="transparent")
        rot_btns.pack()
        
        btn_dyn_l = ctk.CTkButton(rot_btns, text="◄ Дин.", width=40, fg_color="#555")
        btn_dyn_l.pack(side=tk.LEFT, padx=2)
        btn_dyn_l.bind("<ButtonPress-1>", lambda e: self.start_dyn_rotation(-2))
        btn_dyn_l.bind("<ButtonRelease-1>", lambda e: self.stop_dyn_rotation())
        
        for angle in [-45, -5, -1, 0, 1, 5, 45]:
            cmd = (lambda a=angle: self.apply_rotation(a, reset=True)) if angle == 0 else (lambda a=angle: self.apply_rotation(a))
            ctk.CTkButton(rot_btns, text=f"{'+' if angle>0 else ''}{angle}°", width=35, command=cmd).pack(side=tk.LEFT, padx=1)
            
        btn_dyn_r = ctk.CTkButton(rot_btns, text="Дин. ►", width=40, fg_color="#555")
        btn_dyn_r.pack(side=tk.LEFT, padx=2)
        btn_dyn_r.bind("<ButtonPress-1>", lambda e: self.start_dyn_rotation(2))
        btn_dyn_r.bind("<ButtonRelease-1>", lambda e: self.stop_dyn_rotation())

        ctk.CTkButton(rot_frame, text="↔ Отзеркалить (Flip H)", width=200, height=20, command=self.flip_horizontal).pack(pady=2)

        # 5. Сохранение
        nav_frame = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        nav_frame.pack(side=tk.RIGHT, padx=10)
        self.btn_next = ctk.CTkButton(nav_frame, text="Сохранить (Enter) ➔", command=self.save_and_next, 
                                      font=ctk.CTkFont(weight="bold", size=14), fg_color="#2fa572", hover_color="#25825a", height=40)
        self.btn_next.pack()

        # --- РАБОЧАЯ ЗОНА ---
        self.paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashwidth=6, bg="#2b2b2b", bd=0)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # === ПАНЕЛЬ 1: ОСНОВНОЕ ПРЕВЬЮ ===
        self.frame_left = ctk.CTkFrame(self.paned)
        self.paned.add(self.frame_left, minsize=250) 
        
        tools_row = ctk.CTkFrame(self.frame_left, fg_color="transparent")
        tools_row.pack(fill=tk.X, padx=10, pady=5)
        
        self.active_tool_var = ctk.StringVar(value="Pivot")
        self.tool_seg = ctk.CTkSegmentedButton(tools_row, values=["📍 Центр вращения (Pivot)", "📏 Линейка (Shift=45°)"], variable=self.active_tool_var)
        self.tool_seg.set("📍 Центр вращения (Pivot)")
        self.tool_seg.pack(side=tk.LEFT, padx=5)
        
        self.btn_clear_lines = ctk.CTkButton(tools_row, text="❌ Стереть линейки", width=120, fg_color="#8a3b3b", hover_color="#6e2f2f", command=self.clear_guidelines)
        self.btn_clear_lines.pack(side=tk.RIGHT, padx=5)

        zoom_bar = ctk.CTkFrame(self.frame_left, fg_color="transparent")
        zoom_bar.pack(fill=tk.X, padx=10, pady=5)
        ctk.CTkLabel(zoom_bar, text="🔍 Зум (Ctrl+Колесо):", font=ctk.CTkFont(weight="bold")).pack(side=tk.LEFT)
        self.zoom_slider = ctk.CTkSlider(zoom_bar, from_=1, to=10, command=self.on_view_zoom_change)
        self.zoom_slider.set(1.0)
        self.zoom_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        
        ctk.CTkLabel(self.frame_left, text="(ПКМ: Ластик. Удаляет выделенное навсегда из оригинала)", text_color="#888").pack()

        canvas_outer = ctk.CTkFrame(self.frame_left)
        canvas_outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.vbar = ctk.CTkScrollbar(canvas_outer, orientation="vertical")
        self.vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.hbar = ctk.CTkScrollbar(canvas_outer, orientation="horizontal")
        self.hbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.raw_canvas = tk.Canvas(canvas_outer, width=100, height=100, bg=self.canvas_bg, highlightthickness=0, cursor="crosshair", 
                                    xscrollcommand=self.hbar.set, yscrollcommand=self.vbar.set)
        self.raw_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.vbar.configure(command=self.raw_canvas.yview)
        self.hbar.configure(command=self.raw_canvas.xview)
        
        self.raw_canvas.bind("<ButtonPress-1>", self.on_lmb_press)
        self.raw_canvas.bind("<B1-Motion>", self.on_lmb_drag)
        self.raw_canvas.bind("<ButtonRelease-1>", self.on_lmb_release)
        
        self.raw_canvas.bind("<Button-3>", self.on_eraser_press)
        self.raw_canvas.bind("<B3-Motion>", self.on_eraser_drag)
        self.raw_canvas.bind("<ButtonRelease-3>", self.on_eraser_release)

        # === ПАНЕЛЬ 2: ЛУПА ===
        self.frame_mid = ctk.CTkFrame(self.paned)
        self.paned.add(self.frame_mid, minsize=320)
        ctk.CTkLabel(self.frame_mid, text="2. Интерактивная Лупа", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=5)
        
        self.btn_lock_loupe = ctk.CTkButton(self.frame_mid, text="🔓 Лупа: Свободная", command=self.toggle_loupe_lock, 
                                            fg_color="#555", hover_color="#444", width=200, height=24)
        self.btn_lock_loupe.pack(pady=5)
        
        loupe_container = ctk.CTkFrame(self.frame_mid, fg_color="transparent")
        loupe_container.pack(pady=10)
        self.zoom_canvas = tk.Canvas(loupe_container, bg=self.canvas_bg, width=256, height=256, highlightthickness=0, cursor="crosshair")
        self.zoom_canvas.pack()
        self.zoom_canvas.bind("<Button-1>", self.on_loupe_click)

        loupe_ctrl = ctk.CTkFrame(self.frame_mid, fg_color="transparent")
        loupe_ctrl.pack(fill=tk.X, padx=20, pady=5)
        ctk.CTkLabel(loupe_ctrl, text="Сила лупы:").pack(side=tk.LEFT)
        self.loupe_slider = ctk.CTkSlider(loupe_ctrl, from_=2, to=30, command=self.on_loupe_zoom_change)
        self.loupe_slider.set(self.loupe_zoom)
        self.loupe_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        
        pivot_ctrl = ctk.CTkFrame(self.frame_mid, fg_color="transparent")
        pivot_ctrl.pack(fill=tk.X, padx=20, pady=5)
        ctk.CTkLabel(pivot_ctrl, text="Размер пивота:").pack(side=tk.LEFT)
        self.pivot_slider = ctk.CTkSlider(pivot_ctrl, from_=1, to=15, command=self.on_pivot_viz_size_change)
        self.pivot_slider.set(self.pivot_viz_size)
        self.pivot_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)

        fine_f = ctk.CTkFrame(self.frame_mid, fg_color="transparent")
        fine_f.pack(pady=10)
        
        ctk.CTkLabel(fine_f, text="X:", font=ctk.CTkFont(weight="bold", size=14)).pack(side=tk.LEFT, padx=5)
        ctk.CTkButton(fine_f, text="<", width=25, command=lambda: self.tweak_pivot(-1, 0)).pack(side=tk.LEFT)
        self.entry_x = ctk.CTkEntry(fine_f, width=50, justify="center", font=ctk.CTkFont(weight="bold", size=14))
        self.entry_x.pack(side=tk.LEFT, padx=2)
        self.entry_x.bind("<Return>", self.on_entry_change)
        ctk.CTkButton(fine_f, text=">", width=25, command=lambda: self.tweak_pivot(1, 0)).pack(side=tk.LEFT)
        
        ctk.CTkLabel(fine_f, text="   Y:", font=ctk.CTkFont(weight="bold", size=14)).pack(side=tk.LEFT, padx=5)
        ctk.CTkButton(fine_f, text="<", width=25, command=lambda: self.tweak_pivot(0, -1)).pack(side=tk.LEFT)
        self.entry_y = ctk.CTkEntry(fine_f, width=50, justify="center", font=ctk.CTkFont(weight="bold", size=14))
        self.entry_y.pack(side=tk.LEFT, padx=2)
        self.entry_y.bind("<Return>", self.on_entry_change)
        ctk.CTkButton(fine_f, text=">", width=25, command=lambda: self.tweak_pivot(0, 1)).pack(side=tk.LEFT)

        # === ПАНЕЛЬ 3: РЕЗУЛЬТАТ ===
        self.frame_right = ctk.CTkFrame(self.paned)
        self.paned.add(self.frame_right, minsize=350)
        
        res_header = ctk.CTkFrame(self.frame_right, fg_color="transparent")
        res_header.pack(fill=tk.X, pady=10, padx=10)
        self.result_label = ctk.CTkLabel(res_header, text="3. Результат в Игре", font=ctk.CTkFont(size=14, weight="bold"))
        self.result_label.pack(side=tk.LEFT)
        
        self.btn_preview = ctk.CTkButton(res_header, text="▶ Вращение", command=self.toggle_preview, width=100)
        self.btn_preview.pack(side=tk.RIGHT)
        
        tools_row_res = ctk.CTkFrame(self.frame_right, fg_color="transparent")
        tools_row_res.pack(fill=tk.X, pady=5, padx=10)

        self.pivot_toggle = ctk.CTkSwitch(tools_row_res, text="Центр", command=lambda: self.update_right_canvas(), width=60)
        self.pivot_toggle.select()
        self.pivot_toggle.pack(side=tk.LEFT, padx=5)
        
        self.bounds_toggle = ctk.CTkSwitch(tools_row_res, text="Границы экспорта", command=lambda: self.update_right_canvas(), width=60)
        self.bounds_toggle.select()
        self.bounds_toggle.pack(side=tk.LEFT, padx=5)

        res_zoom_bar = ctk.CTkFrame(self.frame_right, fg_color="transparent")
        res_zoom_bar.pack(fill=tk.X, padx=10)
        ctk.CTkLabel(res_zoom_bar, text="Зум превью:", font=ctk.CTkFont(size=11)).pack(side=tk.LEFT)
        self.res_slider = ctk.CTkSlider(res_zoom_bar, from_=0.5, to=5, command=self.on_res_zoom_change)
        self.res_slider.set(1.0)
        self.res_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        res_canvas_outer = ctk.CTkFrame(self.frame_right)
        res_canvas_outer.pack(pady=10, fill=tk.BOTH, expand=True)
        self.ready_canvas = tk.Canvas(res_canvas_outer, bg=self.canvas_bg, highlightthickness=0)
        self.ready_canvas.pack(fill=tk.BOTH, expand=True)
        self.ready_canvas.bind("<Configure>", lambda e: self.update_right_canvas())

    def bind_events(self):
        self.bind("<Return>", lambda event: self.save_and_next() if not isinstance(self.focus_get(), ctk.CTkEntry) else None)
        self.bind("<KeyPress>", self.on_key_press)
        self.raw_canvas.bind("<MouseWheel>", self.on_mouse_wheel) 
        self.bind("<Control-MouseWheel>", self.on_mouse_wheel)
        self.bind("<Control-z>", self.undo)
        self.bind("<Control-Z>", self.undo)
        self.bind("<Control-KeyPress>", self.on_ctrl_keypress)

    def on_ctrl_keypress(self, event):
        if event.keysym.lower() in ['z', 'я', 'cyrillic_ya'] or getattr(event, 'char', '') == '\x1a':
            self.undo()

    # --- НАСТРОЙКИ ---
    def open_settings(self):
        sett_win = ctk.CTkToplevel(self)
        sett_win.title("Настройки")
        sett_win.geometry("300x180")
        sett_win.transient(self) 
        
        ctk.CTkLabel(sett_win, text="Интерфейс и Тема", font=ctk.CTkFont(weight="bold")).pack(pady=10)
        
        self.theme_switch = ctk.CTkSwitch(sett_win, text="Тёмная / Светлая тема", command=self.toggle_theme, onvalue="Dark", offvalue="Light")
        self.theme_switch.select() if self.user_settings["theme"] == "Dark" else self.theme_switch.deselect()
        self.theme_switch.pack(pady=5)

        ctk.CTkLabel(sett_win, text="Цвет фона холстов:", font=ctk.CTkFont(weight="bold")).pack(pady=10)
        colors = [("#ffffff", "W"), ("#d6d6d6", "LG"), ("#3b3b3b", "DG"), ("#000000", "B"), ("#ffb6c1", "P")]
        colors_frame = ctk.CTkFrame(sett_win, fg_color="transparent")
        colors_frame.pack()
        for hex_code, name in colors:
            btn = ctk.CTkButton(colors_frame, text=name, fg_color=hex_code, width=40, height=30,
                                text_color="black" if hex_code in ["#ffffff", "#d6d6d6", "#ffb6c1"] else "white",
                                command=lambda h=hex_code: self.change_canvas_bg(h))
            btn.pack(side=tk.LEFT, padx=2)

    def add_custom_preset(self):
        w_val = self.custom_w.get()
        h_val = self.custom_h.get()
        if not w_val.isdigit() or not h_val.isdigit():
            messagebox.showerror("Ошибка", "Ширина и Высота должны быть числами!")
            return
            
        w, h = int(w_val), int(h_val)
        name = self.custom_name.get() or f"Мой {w}x{h}"
        
        self.user_presets.append({"name": name, "w": w, "h": h})
        self.user_settings["custom_presets"] = self.user_presets
        self.save_settings()
        
        self.refresh_preset_combo_values()
        self.preset_combo.configure(values=self.preset_names_list)
        
        full_name = f"👤 {name} ({w} x {h})"
        self.preset_combo.set(full_name)
        
        self.custom_w.delete(0, tk.END)
        self.custom_h.delete(0, tk.END)
        self.custom_name.delete(0, tk.END)
        
        self.on_preset_change(full_name)

    def remove_custom_preset(self):
        current_preset = self.preset_combo.get()
        for i, p in enumerate(self.user_presets):
            full_name = f"👤 {p['name']} ({p['w']} x {p['h']})"
            if current_preset == full_name:
                self.user_presets.pop(i)
                self.user_settings["custom_presets"] = self.user_presets
                self.save_settings()
                
                self.refresh_preset_combo_values()
                self.preset_combo.configure(values=self.preset_names_list)
                
                # Ставим первый стандартный
                new_choice = list(self.all_presets_dict.keys())[0]
                self.preset_combo.set(new_choice)
                self.on_preset_change(new_choice)
                return
                
        messagebox.showwarning("Внимание", "Нельзя удалить стандартный пресет!")

    def change_canvas_bg(self, hex_code):
        self.canvas_bg = hex_code
        self.pivot_color = self.get_pivot_color(hex_code)
        
        self.raw_canvas.config(bg=hex_code)
        self.zoom_canvas.config(bg=hex_code)
        self.ready_canvas.config(bg=hex_code)
        
        self.user_settings["canvas_bg"] = hex_code
        self.save_settings()
        self.update_all_views() 

    def toggle_theme(self):
        theme = "Dark" if self.theme_switch.get() == "Dark" else "Light"
        ctk.set_appearance_mode(theme)
        self.user_settings["theme"] = theme
        self.save_settings()

    # --- ОТМЕНА (Ctrl+Z) ---
    def save_state_to_undo(self):
        state = {
            'source_img': self.source_img.copy(),
            'current_angle': self.current_angle,
            'pivot_x': self.source_pivot_x,
            'pivot_y': self.source_pivot_y
        }
        self.undo_stack.append(state)
        if len(self.undo_stack) > self.max_undo_steps:
            self.undo_stack.pop(0)

    def undo(self, event=None):
        if not self.undo_stack: return
        state = self.undo_stack.pop()
        
        self.source_img = state['source_img']
        self.current_angle = state['current_angle']
        self.source_pivot_x = state['pivot_x']
        self.source_pivot_y = state['pivot_y']
        
        self.recalculate_sprite()
        self.update_all_views()

    # --- ЛОГИКА ---
    def cycle_mode(self):
        self.current_mode_idx = (self.current_mode_idx + 1) % len(MODES)
        m = MODES[self.current_mode_idx]
        self.btn_mode.configure(text=f"Режим: {m['name']}", fg_color=m['color'], hover_color=m['hover'])
        
        self.user_settings["mode_idx"] = self.current_mode_idx
        self.save_settings()
        self.update_right_canvas()

    def toggle_loupe_lock(self):
        self.loupe_locked = not self.loupe_locked
        if self.loupe_locked:
            self.btn_lock_loupe.configure(text="🔒 Лупа: Заморожена", fg_color="#a5722f", hover_color="#825a25")
        else:
            self.btn_lock_loupe.configure(text="🔓 Лупа: Свободная", fg_color="#555", hover_color="#444")

    def clear_guidelines(self):
        self.guidelines.clear()
        self.update_main_canvas()

    def start_dyn_rotation(self, step):
        self.save_state_to_undo() 
        self.do_dyn_rotation(step)

    def do_dyn_rotation(self, step):
        self.current_angle += step
        self.recalculate_sprite()
        self.dyn_rot_id = self.after(100, lambda: self.do_dyn_rotation(step)) 

    def stop_dyn_rotation(self):
        if self.dyn_rot_id:
            self.after_cancel(self.dyn_rot_id)
            self.dyn_rot_id = None

    def toggle_preview(self):
        self.is_animating = not self.is_animating
        if self.is_animating:
            self.btn_preview.configure(text="⏹ Стоп", fg_color="#b84b4b", hover_color="#8f3a3a")
            self.animate_preview()
        else:
            self.btn_preview.configure(text="▶ Вращение", fg_color=["#3a7ebf", "#1f538d"], hover_color=["#325882", "#14375e"])
            self.preview_angle = 0
            self.update_right_canvas()

    def animate_preview(self):
        if not self.is_animating: return
        self.preview_angle = (self.preview_angle + 6) % 360
        self.update_right_canvas(animating=True)
        self.after(30, self.animate_preview)

    def on_key_press(self, event):
        if isinstance(self.focus_get(), (ctk.CTkEntry)): return
        char = event.keysym.lower()
        if char in ['w', 'up', 'ц']: self.raw_canvas.yview_scroll(-1, "units")
        elif char in ['s', 'down', 'ы']: self.raw_canvas.yview_scroll(1, "units")
        elif char in ['a', 'left', 'ф']: self.raw_canvas.xview_scroll(-1, "units")
        elif char in ['d', 'right', 'в']: self.raw_canvas.xview_scroll(1, "units")

    def on_mouse_wheel(self, event):
        if event.state & 0x0004: 
            delta = 1 if event.delta > 0 else -1
            new_val = max(1.0, min(10.0, self.view_zoom + (delta * 0.5)))
            self.zoom_slider.set(new_val)
            self.on_view_zoom_change(new_val)

    def on_preset_change(self, choice):
        self.target_w, self.target_h = self.all_presets_dict[choice]
        self.user_settings["preset"] = choice
        self.save_settings()
        if self.source_img: self.recalculate_sprite()

    def action_autocrop(self):
        if not self.source_img: return
        self.save_state_to_undo()
        bbox = self.source_img.getbbox()
        if bbox:
            self.source_img = self.source_img.crop(bbox)
            self.source_pivot_x -= bbox[0]
            self.source_pivot_y -= bbox[1]
        self.recalculate_sprite()

    def apply_rotation(self, angle, reset=False):
        self.save_state_to_undo()
        if reset: 
            self.current_angle = 0
        else: 
            self.current_angle += angle
        self.recalculate_sprite()
        
    def flip_horizontal(self):
        self.save_state_to_undo()
        self.source_img = ImageOps.mirror(self.source_img)
        self.source_pivot_x = self.source_img.width - self.source_pivot_x
        self.recalculate_sprite()

    def load_next_image(self):
        if self.current_index >= len(self.images):
            messagebox.showinfo("Готово", "Все картинки обработаны!")
            self.destroy(); return

        self.img_name = self.images[self.current_index]
        self.img_path = os.path.join(self.folder_path, self.img_name)
        self.file_label.configure(text=f"Файл: {self.img_name} ({self.current_index + 1}/{len(self.images)})")

        self.source_img = Image.open(self.img_path).convert("RGBA")
        self.current_angle = 0
        self.preview_angle = 0
        self.source_pivot_x = 0
        self.source_pivot_y = 0
        
        self.undo_stack.clear()
        self.guidelines.clear()
        
        if self.is_animating: self.toggle_preview()
        self.recalculate_sprite()
        self.current_index += 1

    def recalculate_sprite(self):
        img = self.source_img.copy()

        if self.source_pivot_x == 0 and self.source_pivot_y == 0:
            self.source_pivot_x = int(img.width / 2)
            self.source_pivot_y = int(img.height / 2)

        transformed_sx = self.source_pivot_x
        transformed_sy = self.source_pivot_y
        
        transformed_copy = img
        if self.current_angle != 0:
            transformed_copy = transformed_copy.rotate(self.current_angle, expand=True, resample=RESAMPLE_BICUBIC)
            transformed_sx = int(transformed_copy.width / 2)
            transformed_sy = int(transformed_copy.height / 2)
            
        scale = min(self.target_w / transformed_copy.width, self.target_h / transformed_copy.height) * 0.95
        if scale < 1.0:
            new_w = max(1, int(transformed_copy.width * scale))
            new_h = max(1, int(transformed_copy.height * scale))
            transformed_copy = transformed_copy.resize((new_w, new_h), RESAMPLE_LANCZOS)
            self.tr_scale = scale
            transformed_sx *= scale
            transformed_sy *= scale
        else:
            self.tr_scale = 1.0

        self.processed_img = transformed_copy
        
        self.display_pivot_x = int(transformed_sx)
        self.display_pivot_y = int(transformed_sy)
        
        self.update_all_views()

    # --- ИНСТРУМЕНТЫ (ЛКМ) ---
    def set_pivot_from_transformed_space(self, dx, dy):
        tc_x = dx / self.view_zoom
        tc_y = dy / self.view_zoom
        self.source_pivot_x = int(tc_x / self.tr_scale)
        self.source_pivot_y = int(tc_y / self.tr_scale)
        
        if not self.loupe_locked:
            self.loupe_center_x = tc_x
            self.loupe_center_y = tc_y
            
        self.update_all_views()

    def on_lmb_press(self, event):
        cx = self.raw_canvas.canvasx(event.x)
        cy = self.raw_canvas.canvasy(event.y)
        
        if "Pivot" in self.active_tool_var.get() or "Пивот" in self.active_tool_var.get():
            self.set_pivot_from_transformed_space(cx, cy)
        else: 
            self.line_start_x = cx
            self.line_start_y = cy

    def on_lmb_drag(self, event):
        cx = self.raw_canvas.canvasx(event.x)
        cy = self.raw_canvas.canvasy(event.y)
        
        if "Pivot" in self.active_tool_var.get() or "Пивот" in self.active_tool_var.get():
            self.set_pivot_from_transformed_space(cx, cy)
        elif hasattr(self, 'line_start_x'): 
            self.raw_canvas.delete("temp_line")
            
            if event.state & 0x0001: 
                dx = cx - self.line_start_x
                dy = cy - self.line_start_y
                angle = round(math.atan2(dy, dx) / (math.pi/4)) * (math.pi/4)
                dist = math.hypot(dx, dy)
                cx = self.line_start_x + dist * math.cos(angle)
                cy = self.line_start_y + dist * math.sin(angle)
                
            self.raw_canvas.create_line(self.line_start_x, self.line_start_y, cx, cy, fill="#00ff00", width=2, tags="temp_line")

    def on_lmb_release(self, event):
        if "Линейка" in self.active_tool_var.get() and hasattr(self, 'line_start_x'):
            cx = self.raw_canvas.canvasx(event.x)
            cy = self.raw_canvas.canvasy(event.y)
            
            if event.state & 0x0001:
                dx = cx - self.line_start_x
                dy = cy - self.line_start_y
                angle = round(math.atan2(dy, dx) / (math.pi/4)) * (math.pi/4)
                dist = math.hypot(dx, dy)
                cx = self.line_start_x + dist * math.cos(angle)
                cy = self.line_start_y + dist * math.sin(angle)
            
            self.guidelines.append((
                self.line_start_x / self.view_zoom, self.line_start_y / self.view_zoom,
                cx / self.view_zoom, cy / self.view_zoom
            ))
            self.raw_canvas.delete("temp_line")
            del self.line_start_x
            del self.line_start_y
            self.update_main_canvas()

    # --- ЛАСТИК (ПКМ) ---
    def on_eraser_press(self, event):
        if self.current_angle != 0:
            messagebox.showwarning("Внимание", "Сбросьте выравнивание на 0°, чтобы использовать ластик!")
            return
        self.er_start_x = self.raw_canvas.canvasx(event.x)
        self.er_start_y = self.raw_canvas.canvasy(event.y)
        self.er_rect = self.raw_canvas.create_rectangle(self.er_start_x, self.er_start_y, self.er_start_x, self.er_start_y, outline="red", dash=(4,4), width=2)

    def on_eraser_drag(self, event):
        if not hasattr(self, 'er_rect') or self.current_angle != 0: return
        cur_x = self.raw_canvas.canvasx(event.x)
        cur_y = self.raw_canvas.canvasy(event.y)
        self.raw_canvas.coords(self.er_rect, self.er_start_x, self.er_start_y, cur_x, cur_y)

    def on_eraser_release(self, event):
        if not hasattr(self, 'er_rect') or self.current_angle != 0: return
        cur_x = self.raw_canvas.canvasx(event.x)
        cur_y = self.raw_canvas.canvasy(event.y)
        self.raw_canvas.delete(self.er_rect)
        del self.er_rect
        
        self.save_state_to_undo() 
        
        px1 = min(self.er_start_x, cur_x) / self.view_zoom
        py1 = min(self.er_start_y, cur_y) / self.view_zoom
        px2 = max(self.er_start_x, cur_x) / self.view_zoom
        py2 = max(self.er_start_y, cur_y) / self.view_zoom
        
        scale_back = self.source_img.width / self.processed_img.width
        sx1 = int(px1 * scale_back)
        sy1 = int(py1 * scale_back)
        sx2 = int(px2 * scale_back)
        sy2 = int(py2 * scale_back)
        
        draw = ImageDraw.Draw(self.source_img)
        draw.rectangle([sx1, sy1, sx2, sy2], fill=(0,0,0,0))
        self.recalculate_sprite()

    # --- РЕНДЕР ---
    def on_view_zoom_change(self, val):
        self.view_zoom = float(val)
        if self.processed_img: self.update_main_canvas()

    def on_loupe_zoom_change(self, val):
        self.loupe_zoom = float(val)
        self.user_settings["loupe_zoom"] = self.loupe_zoom
        self.save_settings()
        if self.processed_img: self.update_mid_canvas()

    def on_pivot_viz_size_change(self, val):
        self.pivot_viz_size = float(val)
        self.user_settings["pivot_viz_size"] = self.pivot_viz_size
        self.save_settings()
        self.update_all_views()
        
    def on_res_zoom_change(self, val):
        self.res_zoom = float(val)
        if self.processed_img: self.update_right_canvas()

    def update_all_views(self):
        self.update_main_canvas()
        self.update_mid_canvas()
        if not self.is_animating: self.update_right_canvas()

    def update_main_canvas(self):
        self.raw_canvas.delete("all")
        if not self.processed_img: return
        
        disp_w = int(self.processed_img.width * self.view_zoom)
        disp_h = int(self.processed_img.height * self.view_zoom)
        
        preview = self.processed_img.resize((disp_w, disp_h), RESAMPLE_NEAREST)
        self.tk_preview = ImageTk.PhotoImage(preview)
        
        self.raw_canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_preview)
        self.raw_canvas.config(scrollregion=(0, 0, disp_w, disp_h))

        self.raw_canvas.create_rectangle(0, 0, disp_w, disp_h, outline="#ffaa00", dash=(4,4), tags="bounds")

        cx = (self.processed_img.width / 2) * self.view_zoom
        cy = (self.processed_img.height / 2) * self.view_zoom
        self.raw_canvas.create_line(cx-10, cy, cx+10, cy, fill="#00aaff", tags="center")
        self.raw_canvas.create_line(cx, cy-10, cx, cy+10, fill="#00aaff", tags="center")
        self.raw_canvas.create_oval(cx-3, cy-3, cx+3, cy+3, fill="#00aaff", tags="center")

        for gx1, gy1, gx2, gy2 in self.guidelines:
            self.raw_canvas.create_line(gx1 * self.view_zoom, gy1 * self.view_zoom, 
                                        gx2 * self.view_zoom, gy2 * self.view_zoom, 
                                        fill="#00ff00", width=2, tags="guideline")

        px = self.display_pivot_x * self.view_zoom
        py = self.display_pivot_y * self.view_zoom
        
        d = self.pivot_viz_size * self.view_zoom / 2
        self.raw_canvas.create_line(px-d, py, px+d, py, fill=self.pivot_color, tags="pivot")
        self.raw_canvas.create_line(px, py-d, px, py+d, fill=self.pivot_color, tags="pivot")
        self.raw_canvas.create_oval(px-3, py-3, px+3, py+3, fill=self.pivot_color, tags="pivot")
        
        self.entry_x.delete(0, tk.END); self.entry_x.insert(0, str(int(self.display_pivot_x)))
        self.entry_y.delete(0, tk.END); self.entry_y.insert(0, str(int(self.display_pivot_y)))

    def on_loupe_click(self, event):
        dx = (event.x - 128) / self.loupe_zoom
        dy = (event.y - 128) / self.loupe_zoom
        
        if self.loupe_locked and hasattr(self, 'loupe_center_x'):
            cx = self.loupe_center_x + dx
            cy = self.loupe_center_y + dy
        else:
            cx = self.display_pivot_x + dx
            cy = self.display_pivot_y + dy
            
        self.set_pivot_from_transformed_space(cx * self.view_zoom, cy * self.view_zoom)

    def tweak_pivot(self, dx, dy):
        self.save_state_to_undo()
        self.source_pivot_x = max(0, min(self.source_img.width, self.source_pivot_x + dx))
        self.source_pivot_y = max(0, min(self.source_img.height, self.source_pivot_y + dy))
        self.recalculate_sprite()

    def on_entry_change(self, event):
        try:
            new_tx = int(self.entry_x.get())
            new_ty = int(self.entry_y.get())
            if 0 <= new_tx <= self.processed_img.width and 0 <= new_ty <= self.processed_img.height:
                self.save_state_to_undo()
                self.source_pivot_x = int(new_tx / self.tr_scale)
                self.source_pivot_y = int(new_ty / self.tr_scale)
                self.recalculate_sprite()
        except ValueError:
            pass

    def update_mid_canvas(self):
        self.zoom_canvas.delete("all")
        if not self.processed_img: return
        
        crop_size = int(256 / self.loupe_zoom)
        
        if self.loupe_locked and hasattr(self, 'loupe_center_x'):
            cx = self.loupe_center_x
            cy = self.loupe_center_y
        else:
            cx = self.display_pivot_x
            cy = self.display_pivot_y
            
        bbox = (cx - crop_size/2, cy - crop_size/2, cx + crop_size/2, cy + crop_size/2)
        
        zoom_crop = self.processed_img.crop(bbox)
        zoom_view = zoom_crop.resize((256, 256), RESAMPLE_NEAREST)
        self.tk_zoom_view = ImageTk.PhotoImage(zoom_view)
        self.zoom_canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_zoom_view)
        
        for x in range(0, 256, int(self.loupe_zoom)): self.zoom_canvas.create_line(x, 0, x, 256, fill="#a0a0a0", stipple="gray50")
        for y in range(0, 256, int(self.loupe_zoom)): self.zoom_canvas.create_line(0, y, 256, y, fill="#a0a0a0", stipple="gray50")
            
        pivot_vis_x = 128 + (self.display_pivot_x - cx) * self.loupe_zoom
        pivot_vis_y = 128 + (self.display_pivot_y - cy) * self.loupe_zoom
        
        d = self.pivot_viz_size * self.loupe_zoom / 2
        self.zoom_canvas.create_line(pivot_vis_x-d, pivot_vis_y, pivot_vis_x+d, pivot_vis_y, fill=self.pivot_color, width=2)
        self.zoom_canvas.create_line(pivot_vis_x, pivot_vis_y-d, pivot_vis_x, pivot_vis_y+d, fill=self.pivot_color, width=2)
        self.zoom_canvas.create_oval(pivot_vis_x-3, pivot_vis_y-3, pivot_vis_x+3, pivot_vis_y+3, fill=self.pivot_color)

    def update_right_canvas(self, animating=False):
        if not self.processed_img: return
        
        mode = self.current_mode_idx
        req_hw = max(self.display_pivot_x, self.processed_img.width - self.display_pivot_x)
        req_hh = max(self.display_pivot_y, self.processed_img.height - self.display_pivot_y)
        
        fit_img = self.processed_img
        px = self.display_pivot_x
        py = self.display_pivot_y
        
        if mode == 0: 
            self.final_out_w = max(self.target_w, int(req_hw * 2))
            self.final_out_h = max(self.target_h, int(req_hh * 2))
        elif mode == 1: 
            self.final_out_w = self.target_w
            self.final_out_h = self.target_h
            scale_fit = min(1.0, (self.target_w/2) / req_hw, (self.target_h/2) / req_hh)
            if scale_fit < 1.0:
                new_w = max(1, int(self.processed_img.width * scale_fit))
                new_h = max(1, int(self.processed_img.height * scale_fit))
                fit_img = self.processed_img.resize((new_w, new_h), RESAMPLE_LANCZOS)
                px *= scale_fit
                py *= scale_fit
        else: 
            self.final_out_w = self.target_w
            self.final_out_h = self.target_h
            
        self.result_label.configure(text=f"3. Результат ({self.final_out_w}x{self.final_out_h})")
        self.ready_img = Image.new("RGBA", (self.final_out_w, self.final_out_h), TRANSPARENT_RGBA)
        tc_x = int(self.final_out_w / 2)
        tc_y = int(self.final_out_h / 2)
        
        paste_x = int(tc_x - px)
        paste_y = int(tc_y - py)
        self.ready_img.paste(fit_img, (paste_x, paste_y), fit_img)
        
        display_img = self.ready_img
        if animating:
            diag = int((self.final_out_w**2 + self.final_out_h**2)**0.5) + 20
            anim_cvs = Image.new("RGBA", (diag, diag), TRANSPARENT_RGBA)
            anim_cvs.paste(self.ready_img, (diag//2 - self.final_out_w//2, diag//2 - self.final_out_h//2))
            display_img = anim_cvs.rotate(-self.preview_angle, resample=RESAMPLE_BICUBIC, expand=False)
            
        if self.res_zoom != 1.0:
            zw = int(display_img.width * self.res_zoom)
            zh = int(display_img.height * self.res_zoom)
            display_img = display_img.resize((zw, zh), RESAMPLE_NEAREST)
            
        self.tk_ready = ImageTk.PhotoImage(display_img)
        self.ready_canvas.delete("all")
        
        cvs_w = self.ready_canvas.winfo_width()
        cvs_h = self.ready_canvas.winfo_height()
        if cvs_w < 10: 
            cvs_w = self.final_out_w
            cvs_h = self.final_out_h
        
        offset_x = max(0, (cvs_w - display_img.width) // 2)
        offset_y = max(0, (cvs_h - display_img.height) // 2)
        
        self.ready_canvas.create_image(offset_x, offset_y, anchor=tk.NW, image=self.tk_ready)
        
        if not animating:
            z_tc_x = offset_x + tc_x * self.res_zoom
            z_tc_y = offset_y + tc_y * self.res_zoom
            z_out_w = self.final_out_w * self.res_zoom
            z_out_h = self.final_out_h * self.res_zoom

            if self.bounds_toggle.get():
                self.ready_canvas.create_rectangle(offset_x, offset_y, offset_x + z_out_w, offset_y + z_out_h, outline="#ffaa00", dash=(4,4), tags="bounds")

            if self.pivot_toggle.get():
                d = self.pivot_viz_size * self.res_zoom / 2
                self.ready_canvas.create_line(z_tc_x-d, z_tc_y, z_tc_x+d, z_tc_y, fill=self.pivot_color, width=2)
                self.ready_canvas.create_line(z_tc_x, z_tc_y-d, z_tc_x, z_tc_y+d, fill=self.pivot_color, width=2)
                self.ready_canvas.create_oval(z_tc_x-3, z_tc_y-3, z_tc_x+3, z_tc_y+3, fill=self.pivot_color)

    def save_and_next(self):
        if self.ready_img is not None:
            folder_name = f"ready_{self.final_out_w}x{self.final_out_h}"
            out_dir = os.path.join(self.folder_path, folder_name)
            os.makedirs(out_dir, exist_ok=True)
            self.ready_img.save(os.path.join(out_dir, self.img_name))
            print(f"Сохранено: {self.img_name} в {folder_name}")
        self.load_next_image()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        root = tk.Tk()
        tk.Label(root, text="Запускай через ПКМ по папке!").pack()
        root.mainloop()
        sys.exit()
    app = SpriteMasterProApp(sys.argv[1])
    app.mainloop()