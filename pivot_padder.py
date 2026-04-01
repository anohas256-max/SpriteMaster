import os
import sys
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk, ImageDraw
import customtkinter as ctk

# --- Инициализация современного UI ---
ctk.set_appearance_mode("Dark")  # Темная тема по умолчанию
ctk.set_default_color_theme("blue") # Цветовые акценты (синие)

PRESETS = {
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
MAGNIFICATION_FACTOR = 4

RESAMPLE_LANCZOS = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS
RESAMPLE_BICUBIC = Image.Resampling.BICUBIC if hasattr(Image, 'Resampling') else Image.BICUBIC
RESAMPLE_NEAREST = Image.Resampling.NEAREST if hasattr(Image, 'Resampling') else Image.NEAREST

class SpriteMasterProApp(ctk.CTk):
    def __init__(self, folder_path):
        super().__init__()
        self.title("Sprite Master Pro 6.0: Modern Studio")
        self.geometry("1300x850")

        self.folder_path = folder_path
        self.images = [f for f in os.listdir(folder_path) if f.lower().endswith('.png')]
        if not self.images:
            messagebox.showerror("Ошибка", "В папке нет PNG файлов!")
            sys.exit()

        self.current_index = 0
        self.source_img = None         
        self.processed_img = None      
        
        self.pivot_x = 0; self.pivot_y = 0
        self.current_angle = 0
        self.is_autocropped = False
        self.view_zoom = 1.0           
        self.loupe_zoom = 5.0          
        
        self.current_mode_idx = 0
        self.is_animating = False
        self.preview_angle = 0
        
        # Ластик и Ctrl+Z
        self.tr_scale = 1.0
        self.tr_crop_x = 0
        self.tr_crop_y = 0
        self.undo_stack = []
        self.max_undo_steps = 10
        
        self.target_w, self.target_h = PRESETS["128 x 128 (Квадрат)"]
        self.final_out_w, self.final_out_h = self.target_w, self.target_h
        
        # Настройки цвета холстов (чтобы модель было видно)
        self.canvas_bg = "#d6d6d6" # Светло-серый по умолчанию

        self.setup_ui()
        self.bind_events()
        self.load_next_image()

    def setup_ui(self):
        # --- ВЕРХНЯЯ ПАНЕЛЬ ИНСТРУМЕНТОВ ---
        self.toolbar = ctk.CTkFrame(self, corner_radius=0)
        self.toolbar.pack(side=tk.TOP, fill=tk.X, padx=0, pady=0, ipadx=10, ipady=5)

        # 1. Настройки и Тема
        settings_frame = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        settings_frame.pack(side=tk.LEFT, padx=10)
        
        self.btn_settings = ctk.CTkButton(settings_frame, text="⚙️", width=30, command=self.open_settings)
        self.btn_settings.pack(pady=2)
        
        self.theme_switch = ctk.CTkSwitch(settings_frame, text="Тема", command=self.toggle_theme, onvalue="Dark", offvalue="Light")
        self.theme_switch.select() # Включаем Dark
        self.theme_switch.pack(pady=2)

        # 2. Пресеты
        info_frame = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        info_frame.pack(side=tk.LEFT, padx=10)
        ctk.CTkLabel(info_frame, text="Пресет (Размер):", font=ctk.CTkFont(weight="bold")).pack(anchor=tk.W)
        self.preset_combo = ctk.CTkComboBox(info_frame, values=list(PRESETS.keys()), width=200, command=self.on_preset_change)
        self.preset_combo.pack(anchor=tk.W, pady=2)
        self.file_label = ctk.CTkLabel(info_frame, text="Файл: ...", font=ctk.CTkFont(size=11))
        self.file_label.pack(anchor=tk.W)

        # 3. Режимы
        tools_frame = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        tools_frame.pack(side=tk.LEFT, padx=10)
        self.btn_mode = ctk.CTkButton(tools_frame, text=f"Режим: {MODES[0]['name']}", command=self.cycle_mode, 
                                      fg_color=MODES[0]['color'], hover_color=MODES[0]['hover'], text_color="white", width=250)
        self.btn_mode.pack(pady=2)
        self.btn_crop = ctk.CTkButton(tools_frame, text="✂ Автообрезка фона: ВЫКЛ", command=self.toggle_autocrop, 
                                      fg_color="#8a3b3b", hover_color="#6e2f2f", width=250)
        self.btn_crop.pack(pady=2)

        # 4. Вращение
        rot_frame = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        rot_frame.pack(side=tk.LEFT, padx=10)
        ctk.CTkLabel(rot_frame, text="Выравнивание:", font=ctk.CTkFont(weight="bold")).pack(pady=2)
        rot_btns = ctk.CTkFrame(rot_frame, fg_color="transparent")
        rot_btns.pack()
        for angle in [-5, -1, 0, 1, 5]:
            cmd = (lambda a=angle: self.apply_rotation(a, reset=True)) if angle == 0 else (lambda a=angle: self.apply_rotation(a))
            ctk.CTkButton(rot_btns, text=f"{'+' if angle>0 else ''}{angle}°", width=40, command=cmd).pack(side=tk.LEFT, padx=2)

        # 5. Сохранение
        nav_frame = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        nav_frame.pack(side=tk.RIGHT, padx=10)
        self.btn_next = ctk.CTkButton(nav_frame, text="Сохранить (Enter) ➔", command=self.save_and_next, 
                                      font=ctk.CTkFont(weight="bold", size=14), fg_color="#2fa572", hover_color="#25825a", height=40)
        self.btn_next.pack()

        # --- РАБОЧАЯ ЗОНА ---
        # PanedWindow в Tkinter до сих пор незаменим для резиновых окон, просто стилизуем его
        self.paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashwidth=6, bg="#2b2b2b", bd=0)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # === ПАНЕЛЬ 1: ОСНОВНОЕ ПРЕВЬЮ ===
        self.frame_left = ctk.CTkFrame(self.paned)
        self.paned.add(self.frame_left, minsize=400) 
        
        zoom_bar = ctk.CTkFrame(self.frame_left, fg_color="transparent")
        zoom_bar.pack(fill=tk.X, padx=10, pady=5)
        ctk.CTkLabel(zoom_bar, text="🔍 Зум (Ctrl+Колесо):", font=ctk.CTkFont(weight="bold")).pack(side=tk.LEFT)
        self.zoom_slider = ctk.CTkSlider(zoom_bar, from_=1, to=10, command=self.on_view_zoom_change)
        self.zoom_slider.set(1.0)
        self.zoom_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)

        # Холст внутри CTkScrollableFrame не подходит для 2D скроллинга Canvas, поэтому комбинируем
        canvas_outer = ctk.CTkFrame(self.frame_left)
        canvas_outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.vbar = ctk.CTkScrollbar(canvas_outer, orientation="vertical")
        self.vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.hbar = ctk.CTkScrollbar(canvas_outer, orientation="horizontal")
        self.hbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Сам Canvas остается из tk, но с нулями в границах
        self.raw_canvas = tk.Canvas(canvas_outer, bg=self.canvas_bg, highlightthickness=0, cursor="crosshair", 
                                    xscrollcommand=self.hbar.set, yscrollcommand=self.vbar.set)
        self.raw_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.vbar.configure(command=self.raw_canvas.yview)
        self.hbar.configure(command=self.raw_canvas.xview)
        
        self.raw_canvas.bind("<Button-1>", self.on_canvas_click)
        self.raw_canvas.bind("<B1-Motion>", self.on_canvas_click)
        self.raw_canvas.bind("<Button-3>", self.on_eraser_press)
        self.raw_canvas.bind("<B3-Motion>", self.on_eraser_drag)
        self.raw_canvas.bind("<ButtonRelease-3>", self.on_eraser_release)

        # === ПАНЕЛЬ 2: ЛУПА ===
        self.frame_mid = ctk.CTkFrame(self.paned)
        self.paned.add(self.frame_mid, minsize=300)
        ctk.CTkLabel(self.frame_mid, text="2. Интерактивная Лупа", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=10)
        
        loupe_container = ctk.CTkFrame(self.frame_mid, fg_color="transparent")
        loupe_container.pack(pady=10)
        self.zoom_canvas = tk.Canvas(loupe_container, bg=self.canvas_bg, width=256, height=256, highlightthickness=0, cursor="crosshair")
        self.zoom_canvas.pack()
        self.zoom_canvas.bind("<Button-1>", self.on_loupe_click)
        self.zoom_canvas.bind("<B1-Motion>", self.on_loupe_click)

        loupe_ctrl = ctk.CTkFrame(self.frame_mid, fg_color="transparent")
        loupe_ctrl.pack(fill=tk.X, padx=20, pady=10)
        ctk.CTkLabel(loupe_ctrl, text="Сила лупы:").pack(side=tk.LEFT)
        self.loupe_slider = ctk.CTkSlider(loupe_ctrl, from_=2, to=15, command=self.on_loupe_zoom_change)
        self.loupe_slider.set(5.0)
        self.loupe_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)

        # Точная настройка под лупой
        fine_f = ctk.CTkFrame(self.frame_mid, fg_color="transparent")
        fine_f.pack(pady=10)
        ctk.CTkLabel(fine_f, text="Точная координата X: ").pack(side=tk.LEFT)
        self.spin_x = tk.Spinbox(fine_f, from_=-9999, to=9999, width=5, command=self.on_spinbox_change, bg="#444", fg="white", buttonbackground="#555")
        self.spin_x.pack(side=tk.LEFT)
        ctk.CTkLabel(fine_f, text="  Y: ").pack(side=tk.LEFT)
        self.spin_y = tk.Spinbox(fine_f, from_=-9999, to=9999, width=5, command=self.on_spinbox_change, bg="#444", fg="white", buttonbackground="#555")
        self.spin_y.pack(side=tk.LEFT)

        # === ПАНЕЛЬ 3: РЕЗУЛЬТАТ ===
        self.frame_right = ctk.CTkFrame(self.paned)
        self.paned.add(self.frame_right, minsize=350)
        
        res_header = ctk.CTkFrame(self.frame_right, fg_color="transparent")
        res_header.pack(fill=tk.X, pady=10, padx=10)
        self.result_label = ctk.CTkLabel(res_header, text="3. Результат в Игре", font=ctk.CTkFont(size=14, weight="bold"))
        self.result_label.pack(side=tk.LEFT)
        
        self.btn_preview = ctk.CTkButton(res_header, text="▶ Вращение", command=self.toggle_preview, width=100)
        self.btn_preview.pack(side=tk.RIGHT)

        res_canvas_outer = ctk.CTkFrame(self.frame_right)
        res_canvas_outer.pack(pady=10)
        self.ready_canvas = tk.Canvas(res_canvas_outer, bg=self.canvas_bg, highlightthickness=0)
        self.ready_canvas.pack(padx=2, pady=2)

    def bind_events(self):
        self.bind("<Return>", lambda event: self.save_and_next())
        self.bind("<KeyPress>", self.on_key_press)
        self.raw_canvas.bind("<MouseWheel>", self.on_mouse_wheel) 
        self.bind("<Control-MouseWheel>", self.on_mouse_wheel)
        
        # Бинды отмены (только латиница, чтобы Питон не падал)
        self.bind("<Control-z>", self.undo)
        self.bind("<Control-Z>", self.undo)
        # Универсальный слушатель для русской раскладки
        self.bind("<Control-KeyPress>", self.on_ctrl_keypress)

    def on_ctrl_keypress(self, event):
        # '\x1a' — это универсальный системный код для Ctrl+Z на любой раскладке
        if event.keysym.lower() in ['z', 'я', 'cyrillic_ya'] or getattr(event, 'char', '') == '\x1a':
            self.undo()

    # --- НАСТРОЙКИ (GEAR MENU) ---
    def open_settings(self):
        sett_win = ctk.CTkToplevel(self)
        sett_win.title("Настройки")
        sett_win.geometry("300x200")
        sett_win.transient(self) # Поверх главного окна
        
        ctk.CTkLabel(sett_win, text="Цвет фона холстов:", font=ctk.CTkFont(weight="bold")).pack(pady=10)
        
        colors = [("#ffffff", "Белый"), ("#d6d6d6", "Светло-серый"), ("#3b3b3b", "Темно-серый"), ("#000000", "Черный"), ("#ffb6c1", "Розовый (Контраст)")]
        for hex_code, name in colors:
            btn = ctk.CTkButton(sett_win, text=name, fg_color=hex_code, text_color="black" if hex_code in ["#ffffff", "#d6d6d6", "#ffb6c1"] else "white",
                                command=lambda h=hex_code: self.change_canvas_bg(h))
            btn.pack(pady=2, padx=20, fill=tk.X)

    def change_canvas_bg(self, hex_code):
        self.canvas_bg = hex_code
        self.raw_canvas.config(bg=hex_code)
        self.zoom_canvas.config(bg=hex_code)
        self.ready_canvas.config(bg=hex_code)
        self.update_right_canvas() # Перерисовать, чтобы обновить прозрачность

    def toggle_theme(self):
        if self.theme_switch.get() == "Dark":
            ctk.set_appearance_mode("Dark")
            self.paned.config(bg="#2b2b2b")
        else:
            ctk.set_appearance_mode("Light")
            self.paned.config(bg="#e0e0e0")

    # --- ЛОГИКА ---
    def cycle_mode(self):
        self.current_mode_idx = (self.current_mode_idx + 1) % len(MODES)
        m = MODES[self.current_mode_idx]
        self.btn_mode.configure(text=f"Режим: {m['name']}", fg_color=m['color'], hover_color=m['hover'])
        self.update_right_canvas()

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
        if isinstance(self.focus_get(), (tk.Entry, tk.Spinbox)): return
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
        self.target_w, self.target_h = PRESETS[choice]
        if self.source_img: self.recalculate_sprite()

    def toggle_autocrop(self):
        self.is_autocropped = not self.is_autocropped
        self.btn_crop.configure(text="✂ Автообрезка: ВКЛ" if self.is_autocropped else "✂ Автообрезка: ВЫКЛ", 
                                fg_color="#2fa572" if self.is_autocropped else "#8a3b3b",
                                hover_color="#25825a" if self.is_autocropped else "#6e2f2f")
        if self.source_img: self.recalculate_sprite()

    def apply_rotation(self, angle, reset=False):
        if reset: self.current_angle = 0
        else: self.current_angle += angle
        self.recalculate_sprite()

    def load_next_image(self):
        if self.current_index >= len(self.images):
            messagebox.showinfo("Готово", "Все картинки обработаны!")
            self.destroy(); return

        self.img_name = self.images[self.current_index]
        self.img_path = os.path.join(self.folder_path, self.img_name)
        self.file_label.configure(text=f"Файл: {self.img_name} ({self.current_index + 1}/{len(self.images)})")

        self.source_img = Image.open(self.img_path).convert("RGBA")
        self.current_angle = 0; self.preview_angle = 0
        self.undo_stack.clear()
        
        if self.is_animating: self.toggle_preview()
        self.recalculate_sprite()
        self.current_index += 1

    def recalculate_sprite(self):
        img = self.source_img.copy()
        self.tr_crop_x = 0; self.tr_crop_y = 0

        if self.current_angle != 0:
            img = img.rotate(self.current_angle, expand=True, resample=RESAMPLE_BICUBIC, fillcolor=TRANSPARENT_RGBA)
        
        if self.is_autocropped:
            bbox = img.getbbox()
            if bbox: 
                img = img.crop(bbox)
                self.tr_crop_x = bbox[0]; self.tr_crop_y = bbox[1]

        self.tr_scale = min(self.target_w / img.width, self.target_h / img.height) * 0.95
        if self.tr_scale < 1.0:
            new_w = max(1, int(img.width * self.tr_scale))
            new_h = max(1, int(img.height * self.tr_scale))
            img = img.resize((new_w, new_h), RESAMPLE_LANCZOS)
        else:
            self.tr_scale = 1.0

        self.processed_img = img
        self.pivot_x = int(self.processed_img.width / 2)
        self.pivot_y = int(self.processed_img.height / 2)
        
        self.update_all_views()

    # --- ОТМЕНА (Ctrl+Z) ---
    def undo(self, event=None):
        if not self.undo_stack: return
        self.source_img = self.undo_stack.pop()
        self.recalculate_sprite()

    # --- ЛАСТИК ---
    def on_eraser_press(self, event):
        if self.current_angle != 0:
            messagebox.showwarning("Внимание", "Сбросьте выравнивание на 0°, чтобы использовать ластик!")
            return
        self.er_start_x = self.raw_canvas.canvasx(event.x)
        self.er_start_y = self.raw_canvas.canvasy(event.y)
        self.er_rect = self.raw_canvas.create_rectangle(self.er_start_x, self.er_start_y, self.er_start_x, self.er_start_y, outline="red", dash=(4,4), width=2)

    def on_eraser_drag(self, event):
        if not hasattr(self, 'er_rect') or self.current_angle != 0: return
        cur_x = self.raw_canvas.canvasx(event.x); cur_y = self.raw_canvas.canvasy(event.y)
        self.raw_canvas.coords(self.er_rect, self.er_start_x, self.er_start_y, cur_x, cur_y)

    def on_eraser_release(self, event):
        if not hasattr(self, 'er_rect') or self.current_angle != 0: return
        cur_x = self.raw_canvas.canvasx(event.x); cur_y = self.raw_canvas.canvasy(event.y)
        self.raw_canvas.delete(self.er_rect)
        del self.er_rect
        
        # Сохраняем перед удалением
        self.undo_stack.append(self.source_img.copy())
        if len(self.undo_stack) > self.max_undo_steps: self.undo_stack.pop(0)
        
        px1 = min(self.er_start_x, cur_x) / self.view_zoom; py1 = min(self.er_start_y, cur_y) / self.view_zoom
        px2 = max(self.er_start_x, cur_x) / self.view_zoom; py2 = max(self.er_start_y, cur_y) / self.view_zoom
        
        sx1 = int(px1 / self.tr_scale) + self.tr_crop_x; sy1 = int(py1 / self.tr_scale) + self.tr_crop_y
        sx2 = int(px2 / self.tr_scale) + self.tr_crop_x; sy2 = int(py2 / self.tr_scale) + self.tr_crop_y
        
        draw = ImageDraw.Draw(self.source_img)
        draw.rectangle([sx1, sy1, sx2, sy2], fill=(0,0,0,0))
        self.recalculate_sprite()

    # --- РЕНДЕР ---
    def on_view_zoom_change(self, val):
        self.view_zoom = float(val)
        if self.processed_img: self.update_main_canvas()

    def on_loupe_zoom_change(self, val):
        self.loupe_zoom = float(val)
        if self.processed_img: self.update_mid_canvas()

    def update_all_views(self):
        self.update_main_canvas()
        self.update_mid_canvas()
        if not self.is_animating: self.update_right_canvas()

    def update_main_canvas(self):
        self.raw_canvas.delete("all")
        disp_w = int(self.processed_img.width * self.view_zoom)
        disp_h = int(self.processed_img.height * self.view_zoom)
        
        preview = self.processed_img.resize((disp_w, disp_h), RESAMPLE_NEAREST)
        self.tk_preview = ImageTk.PhotoImage(preview)
        
        self.raw_canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_preview)
        self.raw_canvas.config(scrollregion=(0, 0, disp_w, disp_h))

        px = self.pivot_x * self.view_zoom; py = self.pivot_y * self.view_zoom
        self.raw_canvas.create_line(px, 0, px, disp_h, fill="#ff4d4d", dash=(2,2), tags="pivot")
        self.raw_canvas.create_line(0, py, disp_w, py, fill="#ff4d4d", dash=(2,2), tags="pivot")
        r = 3 if self.view_zoom < 3 else 5
        self.raw_canvas.create_oval(px-r, py-r, px+r, py+r, fill="#ff4d4d", tags="pivot")

    def on_canvas_click(self, event):
        cx = self.raw_canvas.canvasx(event.x); cy = self.raw_canvas.canvasy(event.y)
        self.pivot_x = max(0, min(self.processed_img.width, int(cx / self.view_zoom)))
        self.pivot_y = max(0, min(self.processed_img.height, int(cy / self.view_zoom)))
        
        self.spin_x.delete(0, tk.END); self.spin_x.insert(0, str(self.pivot_x))
        self.spin_y.delete(0, tk.END); self.spin_y.insert(0, str(self.pivot_y))
        self.update_all_views()

    def on_loupe_click(self, event):
        dx = (event.x - 128) / self.loupe_zoom; dy = (event.y - 128) / self.loupe_zoom
        self.pivot_x = max(0, min(self.processed_img.width, int(self.pivot_x + dx)))
        self.pivot_y = max(0, min(self.processed_img.height, int(self.pivot_y + dy)))
        
        self.spin_x.delete(0, tk.END); self.spin_x.insert(0, str(self.pivot_x))
        self.spin_y.delete(0, tk.END); self.spin_y.insert(0, str(self.pivot_y))
        self.update_all_views()

    def on_spinbox_change(self):
        try:
            new_x = int(self.spin_x.get()); new_y = int(self.spin_y.get())
            if 0 <= new_x <= self.processed_img.width and 0 <= new_y <= self.processed_img.height:
                self.pivot_x = new_x; self.pivot_y = new_y
                self.update_all_views()
        except ValueError: pass

    def update_mid_canvas(self):
        self.zoom_canvas.delete("all")
        crop_size = int(256 / self.loupe_zoom)
        bbox = (self.pivot_x - crop_size/2, self.pivot_y - crop_size/2, self.pivot_x + crop_size/2, self.pivot_y + crop_size/2)
        
        zoom_crop = self.processed_img.crop(bbox)
        zoom_view = zoom_crop.resize((256, 256), RESAMPLE_NEAREST)
        self.tk_zoom_view = ImageTk.PhotoImage(zoom_view)
        self.zoom_canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_zoom_view)
        
        for x in range(0, 256, int(self.loupe_zoom)): self.zoom_canvas.create_line(x, 0, x, 256, fill="#a0a0a0", stipple="gray50")
        for y in range(0, 256, int(self.loupe_zoom)): self.zoom_canvas.create_line(0, y, 256, y, fill="#a0a0a0", stipple="gray50")
            
        self.zoom_canvas.create_line(128, 0, 128, 256, fill="black", dash=(2, 2))
        self.zoom_canvas.create_line(0, 128, 256, 128, fill="black", dash=(2, 2))
        self.zoom_canvas.create_oval(126, 126, 130, 130, fill="black")

    def update_right_canvas(self, animating=False):
        mode = self.current_mode_idx
        req_hw = max(self.pivot_x, self.processed_img.width - self.pivot_x)
        req_hh = max(self.pivot_y, self.processed_img.height - self.pivot_y)
        
        fit_img = self.processed_img
        px, py = self.pivot_x, self.pivot_y
        
        if mode == 0: 
            self.final_out_w = max(self.target_w, int(req_hw * 2))
            self.final_out_h = max(self.target_h, int(req_hh * 2))
        elif mode == 1: 
            self.final_out_w, self.final_out_h = self.target_w, self.target_h
            scale_fit = min(1.0, (self.target_w/2) / req_hw, (self.target_h/2) / req_hh)
            if scale_fit < 1.0:
                new_w = max(1, int(self.processed_img.width * scale_fit))
                new_h = max(1, int(self.processed_img.height * scale_fit))
                fit_img = self.processed_img.resize((new_w, new_h), RESAMPLE_LANCZOS)
                px, py = px * scale_fit, py * scale_fit
        else: 
            self.final_out_w, self.final_out_h = self.target_w, self.target_h
            
        self.result_label.configure(text=f"3. Результат ({self.final_out_w}x{self.final_out_h})")
        self.ready_img = Image.new("RGBA", (self.final_out_w, self.final_out_h), TRANSPARENT_RGBA)
        tc_x = int(self.final_out_w / 2); tc_y = int(self.final_out_h / 2)
        
        paste_x = int(tc_x - px); paste_y = int(tc_y - py)
        self.ready_img.paste(fit_img, (paste_x, paste_y), fit_img)
        
        display_img = self.ready_img
        if animating:
            diag = int((self.final_out_w**2 + self.final_out_h**2)**0.5) + 20
            anim_cvs = Image.new("RGBA", (diag, diag), TRANSPARENT_RGBA)
            anim_cvs.paste(self.ready_img, (diag//2 - self.final_out_w//2, diag//2 - self.final_out_h//2))
            display_img = anim_cvs.rotate(-self.preview_angle, resample=RESAMPLE_BICUBIC, expand=False)
            self.ready_canvas.config(width=diag, height=diag)
        else:
            self.ready_canvas.config(width=self.final_out_w, height=self.final_out_h)
            
        self.tk_ready = ImageTk.PhotoImage(display_img)
        self.ready_canvas.delete("all")
        self.ready_canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_ready)
        
        if not animating:
            self.ready_canvas.create_line(tc_x, 0, tc_x, self.final_out_h, fill="black", tags="pivot")
            self.ready_canvas.create_line(0, tc_y, self.final_out_w, tc_y, fill="black", tags="pivot")
            self.ready_canvas.create_oval(tc_x-2, tc_y-2, tc_x+2, tc_y+2, fill="black", tags="pivot")

    def save_and_next(self):
        if self.ready_img is not None:
            folder_name = f"ready_{self.final_out_w}x{self.final_out_h}"
            out_dir = os.path.join(self.folder_path, folder_name)
            os.makedirs(out_dir, exist_ok=True)
            self.ready_img.save(os.path.join(out_dir, self.img_name))
            print(f"Сохранено: {self.img_name} в {folder_name}")
        self.load_next_image()

if len(sys.argv) < 2:
    root = tk.Tk(); tk.Label(root, text="Запускай через ПКМ по папке!").pack(); root.mainloop(); sys.exit()
folder_path = sys.argv[1]; app = SpriteMasterProApp(folder_path); app.mainloop()