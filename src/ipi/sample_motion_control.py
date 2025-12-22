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

def rotated_rectangle_coords(cx, cy, width, height, angle_deg):
    """
    Calculate the coordinates of a rotated rectangle.
    cx, cy: center of rectangle
    width, height: dimensions of rectangle
    angle_deg: rotation angle in degrees (counterclockwise)
    """
    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    # Half dimensions
    hw, hh = width / 2, height / 2

    # Rectangle corners relative to center (before rotation)
    corners = [
        (-hw, -hh),  # top-left
        ( hw, -hh),  # top-right
        ( hw,  hh),  # bottom-right
        (-hw,  hh)   # bottom-left
    ]

    # Apply rotation to each corner
    rotated = []
    for x, y in corners:
        xr = cx + x * cos_a - y * sin_a
        yr = cy + x * sin_a + y * cos_a
        rotated.extend((xr, yr))

    return rotated

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

        self.__c_sample = 0
        self.__xoff = 0
        self.__zoff = 0

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
        self.__initialize_component()
        self.handle_window()
        self.__draw_stage()

        #threading.Thread(target=self.__update_thread, daemon=True).start()
        
        #Queue processer
        self.gui_q_processing()

    def __update_thread(self):
        while True:
            time.sleep(0.1)

    def __ui_manual_motion(self):
        z = float(self.z_target.get())
        th = float(self.th_target.get())
        print(f"Moving to: {th} deg, {z} mm")
        self.__ctl.move_to(th, z)

    def __ui_sample_motion(self):
        sample = int(self.sample_target.get())

        self.__xoff = float(self.off_x.get())
        self.__zoff = float(self.off_z.get())
        self.__c_sample = sample

        sample_nums = [11, 4, 10, 3, 0, 5, 9, 2, 1, 6, 8, 7]
        self.__ctl.goto_sample(sample_nums[sample], [self.__xoff, self.__zoff])

    def __ui_nudge(self, off):
        sample = self.__c_sample

        self.__xoff += off[0]
        self.__zoff += off[1]

        sample_nums = [11, 4, 10, 3, 0, 5, 9, 2, 1, 6, 8, 7]
        self.__ctl.goto_sample(sample_nums[sample], [self.__xoff, self.__zoff])

    def __ui_change_sample(self, s):
        sample = int(self.sample_target.get())

        self.__c_sample += s

        sample_nums = [11, 4, 10, 3, 0, 5, 9, 2, 1, 6, 8, 7]
        self.__ctl.goto_sample(sample_nums[self.__c_sample], [self.__xoff, self.__zoff])

    def gui_q_processing(self):
        self.current_angle, self.current_linear_pos = self.__ctl.get_position()
        self.current_angle *= (360 / (math.pi * 2))
        #print(self.current_angle, self.current_linear_pos)
        self.update_gui_position()

        state = self.__ctl.get_state()

        status_str = ""

        if state == stage_client.STATE_IDLE:
            status_str = "Idle"
        elif state == stage_client.STATE_MOVING:
            status_str = "Moving"
        elif state == stage_client.STATE_HOMING:
            status_str = "Homing"
        elif state == stage_client.STATE_OFFLINE:
            status_str = "Offline"

        if self.__ctl.is_enabled():
            status_str += ", actuators enabled."
        else:
            status_str += ", actuators DISABLED. May take a while to start up!"

        self.update_status(status_str)

        while not self.gui_queue.empty():
            task = self.gui_queue.get_nowait()
            if isinstance(task, tuple):
                func, args, kwargs = task
                func(*args, **kwargs)
            else:
                task()
            
        self.root.after(5, self.gui_q_processing)

    def gui_safe(self, func, *args, **kwargs):
        self.gui_queue.put((func, args, kwargs))

    def set_param(self):
        self.vis_scale = 3
        self.center_x, self.center_y = 150, 350
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
        
        num = 0
        for i in [11, 4, 10, 3, 0, 5, 9, 2, 1, 6, 8, 7]:
            s = samples[i]
            s["label"] += f"\nSample #{num}"
            num += 1

        return samples

    def _styled_labeled_entry(self, parent, label_text, default_value, attr_name, row):
        label = ttk.Label(parent, text=label_text, font=('Segoe UI', 10, 'bold'))
        label.grid(row=row * 2, column=0, sticky="w", pady=(0, 2))
        
        entry = ttk.Entry(parent, font=('Segoe UI', 10), width=20)
        entry.insert(0, str(default_value))
        entry.grid(row=row * 2 + 1, column=0, sticky="ew", pady=(0, 10))
        
        setattr(self, attr_name, entry)

    def __initialize_component(self):
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
        self._styled_labeled_entry(manual_motion_frame, "Target Theta", self.target_th, attr_name="th_target", row=1)
        ttk.Button(manual_motion_frame, text="GOTO MANAL", command=self.__ui_manual_motion).grid(row=0, column=2, padx=5, sticky="ew")

        sample_motion_frame = ttk.LabelFrame(control_frame, text="Sample Select", padding=10)
        sample_motion_frame.pack(fill=tk.X, pady=(0, 10))

        self._styled_labeled_entry(sample_motion_frame, "Target Sample", self.target_sample, attr_name="sample_target", row=0)
        self._styled_labeled_entry(sample_motion_frame, "Offset X", 0, attr_name="off_x", row=1)
        self._styled_labeled_entry(sample_motion_frame, "Offset Z", 0, attr_name="off_z", row=2)
        ttk.Button(sample_motion_frame, text="GOTO SAMPLE", command=self.__ui_sample_motion).grid(row=0, column=2, padx=5, sticky="ew")

        nudge_frame = ttk.LabelFrame(control_frame, text="Nudge", padding=10)
        nudge_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(nudge_frame, text="UP", command=lambda: self.__ui_nudge([0, 1])).grid(row=0, column=1, padx=5)
        ttk.Button(nudge_frame, text="DOWN", command=lambda: self.__ui_nudge([0, -1])).grid(row=2, column=1, padx=5)
        ttk.Button(nudge_frame, text="LEFT", command=lambda: self.__ui_nudge([-1, 0])).grid(row=1, column=0, padx=5)
        ttk.Button(nudge_frame, text="RIGHT", command=lambda: self.__ui_nudge([1, 0])).grid(row=1, column=2, padx=5)
        ttk.Button(nudge_frame, text="NEXT", command=lambda: self.__ui_change_sample(1)).grid(row=2, column=2, padx=5)
        ttk.Button(nudge_frame, text="PREV", command=lambda: self.__ui_change_sample(-1)).grid(row=2, column=0, padx=5)

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

        ttk.Button(button_frame, text="HOME", command=self.__ctl.home).grid(row=0, column=0, padx=5, sticky="ew")
        ttk.Button(button_frame, text="HOME ROT", command=self.__ctl.home_rot).grid(row=0, column=1, padx=5, sticky="ew")
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

    def __draw_stage(self):
        self.canvas.delete("all")

        self.canvas.create_rectangle(
                self.center_x, self.center_y - 50, self.center_x + (LIN_LENGTH * self.vis_scale), self.center_y + 50,
                fill="lightgray",
                outline="black",
            )
        
        exposure_x = self.center_x + stage_client.EXPOSURE_OFFSET_Z * self.vis_scale
        exposure_y = self.center_y - stage_client.EXPOSURE_OFFSET_X * self.vis_scale
        #self.canvas.create_line(exposure_x, 0, exposure_x, 750, fill="red", width=3)
        self.canvas.create_text(exposure_x, exposure_y + 30, text="EXPOSURE", fill="red", angle=0, anchor="n", width=250)

        #Stage positioning
        stage_x = self.center_x + self.current_linear_pos * self.vis_scale
        
        #Rotation visualization
        platform_color = ("lightgray" if self.__ctl.is_enabled() else "darkgray")

        if not self.__ctl.is_enabled():
            if not self.__ctl.get_state() == stage_client.STATE_MOVING:
                self.canvas.create_text(stage_x, self.center_y + 300, text="Actuators disabled", fill="gray", angle=0, font=("Helvetica", 56, "bold"))
            else:
                self.canvas.create_text(stage_x, self.center_y + 300, text="Actuators starting", fill="gray", angle=0, font=("Helvetica", 56, "bold"))
        elif self.__ctl.is_at_limit():
            platform_color = "yellow"
            self.canvas.create_text(stage_x, self.center_y + 300, text="Lin actuator at limit!", fill="red", angle=0, font=("Helvetica", 56, "bold"))
        elif self.__ctl.get_state() == stage_client.STATE_HOMING:
            platform_color = "yellow"
            self.canvas.create_text(self.center_x + 500, self.center_y + 300, text="Homing process in progress", fill="red", angle=0, font=("Helvetica", 56, "bold"))

        platform_radius = 50 * self.vis_scale
        self.canvas.create_oval(
            stage_x - platform_radius, self.center_y - platform_radius,
            stage_x + platform_radius, self.center_y + platform_radius,
            fill=platform_color, outline="black"
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
            coords = rotated_rectangle_coords(x, y, side * 2, side * 2, -self.current_angle)
            self.canvas.create_polygon(
                coords,
                fill="lightgreen",
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
        self.__draw_stage()

        
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
    time.sleep(1)

    root = tk.Tk()
    app = SampleStageControl(root, ctl)
    root.mainloop()