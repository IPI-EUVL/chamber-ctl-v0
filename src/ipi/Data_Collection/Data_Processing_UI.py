import tkinter as tk 
from tkinter import filedialog
from tkinter import messagebox
import process_snapshot
import process_snapshots 
import process_snapshots_no_chopper
import os
import sys
import runpy
import threading
from tkinterweb import HtmlFrame
import webview
import time


class Data_Processing_UI(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.widgetsnbuttons()
        master.bind("<Return>", self.trigger_processing_scripts)
        self.SCRIPT_PATH = "./"
        self.grid()

    def widgetsnbuttons(self):
        #Labels////////

        labelframe = tk.Frame(self, bg="black")
        labelframe.grid(row = 11, column = 0, columnspan = 3, sticky = "we")
        self.label = tk.Label(self, text="Select Processing Method", fg="black")
        self.status = tk.Label(self, text="No processing selected", fg="black")
        self.data = tk.Label(labelframe, text="No data", fg = "darkgreen", bg = "black")

        #Variables//////////////
        self.processing_script = tk.StringVar(self, value="ps")
        self.data_directory = tk.StringVar(self, value = "")

        #Buttons////////
        self.button = tk.Button(self, text="Select Folder", font=("Arial", 12), 
                                command=self.select_exposure, fg = "white",
                                bg="Teal")
        tk.Radiobutton(self, text = "Individual Pulse", variable = self.processing_script, value = "ps").grid(row = 1, column = 0, sticky = "W", pady = (10,0))
        #tk.Radiobutton(self, text = "All Pulses w Chopper", variable = self.processing_script, value = "piss").grid(row = 3, column = 0, sticky = "W")
        tk.Radiobutton(self, text = "All Pulses w/o Chopper", variable = self.processing_script, value = "psnc").grid(row = 5, column = 0, sticky = "W")
        
        #Positions////
        self.button.grid(row = 1, column = 2,rowspan=3, sticky = "nwse", padx=20)
        self.label.grid(row = 0, column = 0, sticky = "W")
        self.status.grid(row = 10, column = 0, columnspan = 3, sticky = "we", pady = 20)
        self.data.grid(row = 2, column = 0, rowspan = 3, columnspan = 3, sticky = "nswe", pady = 20)

    def select_exposure(self):
        directory = filedialog.askdirectory()
        self.data_directory = tk.StringVar(value=directory)
        if directory == "":
            self.status.config(text="No folder selected")
        else:
            self.status.config(text="Processing " + directory.split("/")[-1])    

    def trigger_processing_scripts(self, event=None):
        script = self.processing_script.get()
        data = self.data_directory.get()

        if data == "":
            tk.messagebox.showwarning("Warning", "No data selected")
            return
        else:
            if script == "ps":
                self.status.config(text="Processing individual snapshot...")
                self.status.update_idletasks()
                script_path = os.path.join(self.SCRIPT_PATH, "process_snapshot")
                sys.argv = [script_path, data]
                process_snapshots_no_chopper.main()
                sys.argv = [script_path, data, 0]
                process_snapshot.main()
                time.sleep(5)
                #Process single snapshot

            #elif script == "piss":
            #    self.status.config(text="Processing multiple snapshots with chopper...")
            #    self.status.update_idletasks()
            #    script_path = os.path.join(self.SCRIPT_PATH, "process_snapshots")
            #    sys.argv = [script_path, data]

            #    process_snapshots.main()
                #Process multiple snapshots without chopper

            elif script == "psnc":
                self.status.config(text="Processing multiple snapshots without chopper...")
                self.status.update_idletasks()
                script_path = os.path.join(self.SCRIPT_PATH, "process_snapshots_no_chopper")
                sys.argv = [script_path, data]

                process_snapshots_no_chopper.main()
                #Process multiple snapshots with chopper
            
            self.status.after(0, self.status.config(text = "Processing completed"))
            window = None

            with open(os.path.join(os.getcwd(), "plot.html"), "r") as f:
                html = f.read()
            with open(os.path.join(os.getcwd(), "dose.txt"), "r") as f:
                dose = f.readlines()

            self.status.after(100, self.status.config(text="Processing " + data.split("/")[-1]))
            self.status.update_idletasks()
            self.data.after(100, self.data.config(text=f"{dose[0]}\n{dose[1]}\n{dose[2]}"))
            self.data.update_idletasks()

            while True:
                if window == None:
                    try:
                        webview.create_window(
                                "PD Voltage Reading",
                                html=html,
                                width=1000,
                                height=600
                            )
                        window = "one"
                        break
                    except webview.errors.WebViewException:
                        webview.create_window(
                                "PD Voltage Reading",
                                html=html,
                                width=1000,
                                height=600
                            )
                        window = "one"
                else:
                    break
            time.sleep(5)
            threading.Thread(target=webview.start()).start()






root = tk.Tk()
root.title("Data Processing")
root.geometry("300x300")
root.resizable(False, False)

ui = Data_Processing_UI(root)
root.mainloop()
