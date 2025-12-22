import tkinter as tk
from tkinter import ttk
from labjack import ljm
import time
import math
import threading
from math import cos, sin, radians
from queue import Queue
import stage_client

LIN_LENGTH = 90

class SampleStageControl:
    def __init__(self, root, ctl : stage_client.StageController):
        self.root = root
        root.title("Sample Stage Control")

        self.__ctl = ctl
        
        self.set_param()

        #Labjack setup
        #Initial positions
        self.current_angle = 0  #degrees
        self.current_linear_pos = 50  #Outer ring position start (41.783 mm, 0 degrees)

        self.target_z = 0
        self.target_th = 0
        self.target_sample = 0

        #Rotation config
        self.visual_angle = 0
        self.visual_rotation_active = False
        self.rotation_direction = 1  #1 for CW, -1 for CCW
        
        #Sample config
        self.samples = self.__build_sample_data()
        self.ring_radii = {1: 21.209, 2: 41.783}  #mm (converted from 0.835" and 1.645" from Max's diagram)
        self.exposure_pos = 100  #Linear position for exposure (rightmost)
        
        #GUI update queue
        self.gui_queue = Queue()
        
        #GUI setup 
        self.widgetter()
        self.handle_window()
        self.stager()

        threading.Thread(target=self.__update_thread, daemon=True).start()
        
        #Queue processer
        self.gui_q_processing()

    def __update_thread(self):
        while True:
            time.sleep(0.1)

    def __ui_manual_motion(self):
        print(f"Moving to: {self.target_th} deg, {self.target_z} mm")
        self.__ctl.move_to(self.target_th, self.target_z)

    def __ui_sample_motion(self):
        self.__ctl.goto_sample(self.target_sample)

    def gui_q_processing(self):
        

        while not self.gui_queue.empty():
            print(self.gui_queue.empty())
            task = self.gui_queue.get_nowait()
            if isinstance(task, tuple):
                func, args, kwargs = task
                func(*args, **kwargs)
            else:
                task()
            
        self.root.after(50, self.gui_q_processing)

    def gui_safe(self, func, *args, **kwargs):
        self.gui_queue.put((func, args, kwargs))

    def set_param(self):
        self.vis_scale = 4
        self.center_x, self.center_y = 100, 350
        self.last_draw_time = 0

    def __build_sample_data(self):
        samples = []
        inner_radius_mm = 0.835 * 25.4
        outer_radius_mm = 1.645 * 25.4
        
        #Inner targets (processed second)
        for quadrant in range(4):
            angle = 45 + 90 * quadrant
            samples.append({
                'ring': 1,
                'position': quadrant,
                'angle': angle,
                'label': f"Inner-Q{quadrant+1}",
                'radius': inner_radius_mm,
                'shape': 'square',
                'size': 2,
                'exposed': False,
                'exposure_time': 5.0
            })
        
        #Outer targets (processed first)
        for quadrant in range(4):
            base_angle = 90 * quadrant
            for i, offset in enumerate([21.04, 68.96]):
                angle = base_angle + offset
                samples.append({
                    'ring': 2,
                    'position': quadrant * 2 + i,
                    'angle': angle,
                    'label': f"Outer-Q{quadrant+1}-{i+1}",
                    'radius': outer_radius_mm,
                    'shape': 'square',
                    'size': 2,
                    'exposed': False,
                    'exposure_time': 5.0
                })
        return samples

    def _styled_labeled_entry(self, parent, label_text, default_value, attr_name, row):
        label = ttk.Label(parent, text=label_text, font=('Segoe UI', 10, 'bold'))
        label.grid(row=row * 2, column=0, sticky="w", pady=(0, 2))
        
        entry = ttk.Entry(parent, font=('Segoe UI', 10), width=20)
        entry.insert(0, str(default_value))
        entry.grid(row=row * 2 + 1, column=0, sticky="ew", pady=(0, 10))
        
        setattr(self, attr_name, entry)

    def widgetter(self):
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        #Left panel container for controls
        left_container = ttk.Frame(main_frame)
        left_container.grid(row=0, column=0, sticky="nsew", padx=5)

        #Scrollbar - does not work with light mousepad scrolling. You have to click and drag
        canvas = tk.Canvas(left_container)
        scrollbar = ttk.Scrollbar(left_container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        #Control panel
        control_frame = ttk.LabelFrame(scrollable_frame, text="Stage Control Panel", padding=10)
        control_frame.pack(fill=tk.BOTH, expand=True)

        #Speed controls
        manual_motion_frame = ttk.LabelFrame(control_frame, text="Manual Motion", padding=10)
        manual_motion_frame.pack(fill=tk.X, pady=(0, 10))

        self._styled_labeled_entry(manual_motion_frame, "Target Z", self.target_z, attr_name="z_target", row=0)
        self._styled_labeled_entry(manual_motion_frame, "Target Theta", self.target_th, attr_name="rot_target", row=1)
        ttk.Button(manual_motion_frame, text="GOTO MANAL", command=self.__ui_manual_motion).grid(row=0, column=2, padx=5, sticky="ew")

        sample_motion_frame = ttk.LabelFrame(control_frame, text="Sample Select", padding=10)
        sample_motion_frame.pack(fill=tk.X, pady=(0, 10))

        self._styled_labeled_entry(sample_motion_frame, "Target Sample", self.target_sample, attr_name="rot_target", row=1)
        ttk.Button(sample_motion_frame, text="GOTO SAMPLE", command=self.__ui_sample_motion).grid(row=0, column=2, padx=5, sticky="ew")

        canvas.config(scrollregion=canvas.bbox("all"))

        #Status updates
        status_frame = ttk.LabelFrame(control_frame, text="Stage Status", padding=10)
        status_frame.pack(fill=tk.X, pady=(0, 10))

        self.position_label = ttk.Label(status_frame, text="ROT: 0.0 deg, LIN: 0.0 mm", font=('Segoe UI', 11, 'bold'))
        self.position_label.pack(anchor="w", pady=5)

        self.status_label = ttk.Label(status_frame,
                                    text="Disconnected",
                                    foreground="red",
                                    font=('Segoe UI', 10, 'italic'))
        self.status_label.pack(anchor="w", pady=(5, 0))
        #Control buttons
        button_frame = ttk.LabelFrame(main_frame, text="Controls", padding=10)
        button_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        button_frame.columnconfigure((0, 1, 2, 3), weight=1)

        ttk.Button(button_frame, text="HOME", command=None).grid(row=0, column=0, padx=5, sticky="ew")
        ttk.Button(button_frame, text="GOTO SAMPLE", command=None).grid(row=0, column=1, padx=5, sticky="ew")
        #ttk.Button(button_frame, text="✖ EMERGENCY STOP", command=self.emergency_stop, style="Emergency.TButton").grid(row=0, column=3, padx=5, sticky="ew")

        #Stage visualization
        vis_frame = ttk.LabelFrame(main_frame, text="Sample Stage View", padding=10)
        vis_frame.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=5, pady=5)
        self.canvas = tk.Canvas(vis_frame, width=1000, height=1000, bg='white', highlightthickness=1, highlightbackground="#888")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        #Layout config
        main_frame.columnconfigure(0, weight=0)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=0)

        #Stylish buttons and labels
        style = ttk.Style()
        style.configure("TButton", font=('Segoe UI', 10))
        style.configure("TLabel", font=('Segoe UI', 0))
        style.configure("Emergency.TButton", foreground="#aa0000", background="#aa0000",
                        font=('Segoe UI', 10, 'bold'))
        style.configure("TLabelframe.Label", font=('Segoe UI', 15, 'bold', 'underline'))
        style.map("Emergency.TButton", background=[('active', '#cc0000')])

    def stager(self):
        self.canvas.delete("all")

        self.canvas.create_rectangle(
                self.center_x, self.center_y - 50, self.center_x + (LIN_LENGTH * self.vis_scale), self.center_y + 50,
                fill="lightgray",
                outline="black",
            )
        
        exposure_x = self.center_x + stage_client.EXPOSURE_OFFSET_Z * self.vis_scale
        exposure_y = self.center_y + stage_client.EXPOSURE_OFFSET_X * self.vis_scale
        #self.canvas.create_line(exposure_x, 0, exposure_x, 750, fill="red", width=3)
        self.canvas.create_text(exposure_x, exposure_y + 30, text="EXPOSURE", fill="red", angle=0, anchor="n", width=250)

        #Stage positioning
        stage_x = self.center_x + self.current_linear_pos * self.vis_scale
        
        #Rotation visualization
        platform_radius = 200
        self.canvas.create_oval(
            stage_x - platform_radius, self.center_y - platform_radius,
            stage_x + platform_radius, self.center_y + platform_radius,
            fill="lightgray", outline="black"
        )
        
        #Center marker for reference
        self.canvas.create_oval(stage_x-5, self.center_y-5, stage_x+5, self.center_y+5, fill="blue")
        
        #Concentric rings for reference
        for ring, radius_mm in self.ring_radii.items():
            radius_px = radius_mm * self.vis_scale
            self.canvas.create_oval(stage_x-radius_px, self.center_y-radius_px, 
                                stage_x+radius_px, self.center_y+radius_px, 
                                outline="gray", width=2)
        
        #Samples
        for sample in self.samples:
            display_angle = sample['angle'] - self.current_angle
            radius = sample['radius'] * self.vis_scale
            x = stage_x + radius * cos(math.radians(display_angle))
            y = self.center_y + radius * sin(radians(display_angle))

            side = math.sqrt(sample['size']) * 10 * self.vis_scale/1.75
            self.canvas.create_rectangle(
                x-side, y-side, x+side, y+side,
                fill="crimson" if sample['exposed'] else "lightgreen",
                outline="black",
            )
            self.canvas.create_text(x, y, text=sample['label'])
        
        self.canvas.create_oval(exposure_x - 15, exposure_y-15, exposure_x+15, exposure_y+15, fill="red")
        self.canvas.update_idletasks()

    def update_gui_position(self):
        """Thread-safe GUI position update"""
        self.position_label.config(
            text=f"ROT: {self.current_angle:.2f} deg, LIN: {self.current_linear_pos:.2f} mm"
        )
        self.stager()

        
    def update_status(self, text):
        self.gui_safe(lambda t: self.status_label.config(text=t), text)

    def handle_window(self):
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        self.cleanup()
        self.root.destroy()

    def cleanup(self):
        self.open_gui = False

    def show_error_message(self, message):
        def _show_error():
            error_window = tk.Toplevel(self.root)
            error_window.title("Error")
            ttk.Label(error_window, text=message).pack(padx=20, pady=20)
            ttk.Button(error_window, text="OK", command=error_window.destroy).pack(pady=10)
        
        self.gui_safe(_show_error)

if __name__ == "__main__":
    client = stage_client.StepperClient(11756, ("10.193.124.226", 11755))
    ctl = stage_client.StageController(client)

    root = tk.Tk()
    app = SampleStageControl(root, ctl)
    root.mainloop()