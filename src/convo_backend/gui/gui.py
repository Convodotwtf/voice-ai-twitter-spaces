import tkinter as tk
from tkinter import ttk
import logging
import asyncio
from convo_backend.core.core import ConvoCore
from logging import Handler
import sys
from convo_backend.config import Config

class LogHandler(Handler):
    def __init__(self, tree_widget: ttk.Treeview):
        super().__init__()
        self.tree = tree_widget
        self.queue = asyncio.Queue()
        self.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.loop = asyncio.get_event_loop()  # Store the event loop when created
        
        # Start the process_logs task
        asyncio.create_task(self.process_logs())
        
    def emit(self, record):
        msg = self.format(record)
        # Use the stored event loop reference
        self.loop.call_soon_threadsafe(
            self.queue.put_nowait, msg
        )
    
    async def process_logs(self):
        while True:
            try:
                msg = await self.queue.get()
                parts = msg.split(' - ', 2)
                if len(parts) == 3:
                    time, level, message = parts
                    
                    if level.lower() == "error":
                        self.tree.insert('', 'end', values=(time, level, message), tags=('error',))
                        self.tree.tag_configure('error', foreground='red')
                    else:
                        self.tree.insert('', 'end', values=(time, level, message))
                        
                    # Keep only the last 1000 entries
                    if len(self.tree.get_children()) > 1000:
                        self.tree.delete(self.tree.get_children()[0])
                    
            except Exception as e:
                print(f"Error processing log: {e}")

class ConvoGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Convo")
        self.root.geometry("525x700")
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.root.iconbitmap(f"{Config.ASSETS_PATH}/convo.ico")

        self.convo_instance = None

        # Create main frame with padding
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Device selection
        ttk.Label(self.main_frame, text="Audio Device:").grid(
            row=0, column=0, sticky=tk.W, pady=5
        )
        self.device_var = tk.StringVar(value="vb-cables")
        devices = ["vb-cables", "blackhole", "default"]
        for i, device in enumerate(devices):
            ttk.Radiobutton(
                self.main_frame, text=device, variable=self.device_var, value=device
            ).grid(row=i + 1, column=0, sticky=tk.W, padx=20)

        # Checkboxes for flags
        self.roam_var = tk.BooleanVar()
        ttk.Checkbutton(
            self.main_frame,
            text="Enable X-roaming",
            variable=self.roam_var,
            command=lambda: self.spaces_entry.config(
                state=tk.NORMAL if self.roam_var.get() else tk.DISABLED
            ),
        ).grid(row=4, column=0, sticky=tk.W, pady=5)

        # Desired spaces input
        self.spaces_label = ttk.Label(
            self.main_frame, text="Desired Spaces (comma-separated):"
        )
        self.spaces_label.grid(row=7, column=0, sticky=tk.W, pady=5)
        self.spaces_var = tk.StringVar()
        self.spaces_entry = ttk.Entry(
            self.main_frame, textvariable=self.spaces_var, state=tk.DISABLED
        )
        self.spaces_entry.grid(row=8, column=0, sticky=(tk.W, tk.E), pady=5)

        # Start button
        ttk.Button(
            self.main_frame, text="Start Convo", command=self._start_button_clicked
        ).grid(row=10, column=0, columnspan=2, pady=20)

        # Create log frame
        log_frame = ttk.LabelFrame(self.main_frame, text="Logs", padding="5")
        log_frame.grid(row=11, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)

        # Configure grid to allow expansion
        self.main_frame.grid_rowconfigure(11, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        # Create Treeview widget with scrollbars
        self.log_tree = ttk.Treeview(log_frame, columns=('Time', 'Level', 'Message'), show='headings')
        
        # Configure columns
        self.log_tree.heading('Time', text='Time')
        self.log_tree.heading('Level', text='Level')
        self.log_tree.heading('Message', text='Message')
        
        # Set column widths and prevent wrapping by setting minwidth
        self.log_tree.column('Time', width=100, minwidth=100, stretch=False)
        self.log_tree.column('Level', width=70, minwidth=70, stretch=False)
        self.log_tree.column('Message', width=300, minwidth=300, stretch=True)

        # Add scrollbars
        vsb = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_tree.yview)
        hsb = ttk.Scrollbar(log_frame, orient="horizontal", command=self.log_tree.xview)
        self.log_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        # Grid the treeview and scrollbars
        self.log_tree.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        vsb.grid(row=0, column=1, sticky=(tk.N, tk.S))
        hsb.grid(row=1, column=0, sticky=(tk.E, tk.W))

        # Configure log frame grid
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        # Create log handler
        self.log_handler = LogHandler(self.log_tree)
        logging.getLogger().addHandler(self.log_handler)

        # create stop button
        self.stop_button = ttk.Button(
            self.main_frame,
            text="Stop Convo",
            command=self._stop_button_clicked,
            state=tk.DISABLED,
        )
        self.stop_button.grid(row=12, column=0, columnspan=2, pady=20)

        # After creating the log_tree, add these bindings
        self.log_tree.bind('<Button-3>', self._show_context_menu)  # Right click
        self.log_tree.bind('<Control-c>', self._copy_selection)    # Ctrl+C

        # Create context menu
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Copy", command=self._copy_selection)

    def get_config(self):
        """Return the current configuration as a dictionary"""
        spaces = (
            [s.strip() for s in self.spaces_var.get().split(",")]
            if self.spaces_var.get()
            else None
        )

        return {
            "device": self.device_var.get(),
            "roam": self.roam_var.get(),
            "monitor": False,  # TODO: fix monitoring and we can change this to be a checkbox
            "desired_spaces": spaces,
        }

    def _start_button_clicked(self):
        """Synchronous callback for start button"""
        # Disable only interactive widgets
        for widget in self.main_frame.winfo_children():
            if isinstance(widget, (ttk.Entry, ttk.Button, ttk.Radiobutton, ttk.Checkbutton)):
                widget.configure(state=tk.DISABLED)
        # Enable stop button
        self.stop_button.configure(state=tk.NORMAL)
        self.start_task = asyncio.create_task(self.start_convo())

    def _stop_button_clicked(self):
        """Synchronous callback for stop button"""
        # Enable only interactive widgets
        for widget in self.main_frame.winfo_children():
            if isinstance(widget, (ttk.Entry, ttk.Button, ttk.Radiobutton, ttk.Checkbutton)):
                widget.configure(state=tk.NORMAL)
        # Disable stop button
        self.stop_button.configure(state=tk.DISABLED)
        self.stop_task = asyncio.create_task(self.stop_convo())

    def _on_closing(self):
        """Handle window close event"""
        self.update_task.cancel()

    async def start_convo(self):
        """Start convo core instance"""
        self.config = self.get_config()
        # Create ConvoCore instance with configuration
        self.convo_instance = ConvoCore(**self.config)
        logging.info(f"Starting Convo with configuration: {self.config}")
        # Start convo
        await self.convo_instance.start()

    async def stop_convo(self):
        """Stop convo core instance"""
        logging.info("Stopping Convo")
        # Stop convo
        await self.convo_instance.stop()

    async def update(self):
        """Periodic update for GUI to process async events"""
        try:
            while True:
                self.root.update()
                await asyncio.sleep(0.1)  # Small delay to prevent CPU hogging
        except asyncio.CancelledError:
            pass

    async def run_async(self):
        """Run the GUI asynchronously"""
        self.update_task = asyncio.create_task(self.update())
        try:
            await self.update_task
        except Exception as e:
            logging.error(f"GUI error: {e}")
        finally:
            if self.convo_instance:
                await self.convo_instance.stop()
            self.root.destroy()

    def run(self):
        """Return the GUI coroutine"""
        return self.run_async()

    def _show_context_menu(self, event):
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def _copy_selection(self, event=None):
        selected_items = self.log_tree.selection()
        if not selected_items:
            return
        
        item = selected_items[0]  # Get the first selected item
        values = self.log_tree.item(item)['values']
        if values:
            text = ' - '.join(str(v) for v in values)
            self.root.clipboard_clear()
            self.root.clipboard_append(text)


if __name__ == "__main__":
    gui = ConvoGUI()
    gui.run()
