#hi2
import socket
import threading
import json
import tkinter as tk
from tkinter import colorchooser, simpledialog, messagebox
import uuid


class WhiteboardApp:
    def __init__(self, root):
        self.root = root
        self.username = simpledialog.askstring("Username", "Enter your username:", parent=root)
        if not self.username:
            self.username = "Anonymous"
        self.root.title(f"Collaborative Whiteboard - {self.username}")

        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.HOST = '192.168.0.173'
        self.PORT = 5006
        self.connect_to_server()

        # Theme configuration
        self.themes = {
            "light": {"canvas_bg": "white", "root_bg": "white", "toolbar_bg": "lightgray", "text_fg": "black"},
            "dark": {"canvas_bg": "gray20", "root_bg": "gray20", "toolbar_bg": "gray30", "text_fg": "white"},
            "custom": {"canvas_bg": "white", "root_bg": "white", "toolbar_bg": "lightgray", "text_fg": "black"}
        }
        self.current_theme = tk.StringVar(value="light")

        # GUI setup
        self.canvas = tk.Canvas(root, bg=self.themes["light"]["canvas_bg"], width=800, height=600)
        self.canvas.pack(pady=10)

        self.status_label = tk.Label(root, text="",
                                     fg=self.themes["light"]["text_fg"],
                                     bg=self.themes["light"]["root_bg"])
        self.status_label.pack()

        self.current_color = 'black'
        self.pen_width = 2
        self.eraser_width = 10
        self.eraser_on = False
        self.last_x = None
        self.last_y = None
        self.current_stroke = []
        self.current_stroke_id = None
        self.own_strokes = {}          # stroke_id -> [lines]
        self.undo_stack = []
        self.redo_stack = []
        self.other_users_strokes = {}  # username -> {stroke_id -> [lines]}
        self.drawing_bubbles = {}
        self.undone_strokes = {}       # Store undone strokes for redo

        # Toolbar setup
        self.toolbar = tk.Frame(root, bg=self.themes["light"]["toolbar_bg"])
        self.toolbar.pack(fill=tk.X)
        tk.Button(self.toolbar, text="Color", command=self.choose_color).pack(side=tk.LEFT, padx=5)
        tk.Button(self.toolbar, text="Eraser", command=self.use_eraser).pack(side=tk.LEFT, padx=5)
        tk.Button(self.toolbar, text="Clear", command=self.clear_canvas).pack(side=tk.LEFT, padx=5)
        tk.Button(self.toolbar, text="Undo", command=self.undo).pack(side=tk.LEFT, padx=5)
        tk.Button(self.toolbar, text="Redo", command=self.redo).pack(side=tk.LEFT, padx=5)
        tk.OptionMenu(self.toolbar, self.current_theme, "light", "dark", "custom",
                      command=self.apply_theme).pack(side=tk.LEFT, padx=5)
        tk.Button(self.toolbar, text="Custom Background",
                  command=self.choose_custom_background).pack(side=tk.LEFT, padx=5)

        self.size_slider = tk.Scale(self.toolbar, from_=1, to=50, orient=tk.HORIZONTAL,
                                    label="Size", command=self.change_tool_size,
                                    bg=self.themes["light"]["toolbar_bg"],
                                    fg=self.themes["light"]["text_fg"])
        self.size_slider.set(self.pen_width)
        self.size_slider.pack(side=tk.LEFT, padx=10)

        self.canvas.bind("<Button-1>", self.start_drawing)
        self.canvas.bind("<B1-Motion>", self.draw)
        self.canvas.bind("<ButtonRelease-1>", self.stop_drawing)

        self.running = True
        threading.Thread(target=self.receive_data, daemon=True).start()

        self.update_status()

    def connect_to_server(self):
        try:
            self.client_socket.connect((self.HOST, self.PORT))
            self.send_message({"type": "join", "username": self.username})
        except Exception as e:
            messagebox.showerror("Connection Error", f"Failed to connect: {e}")
            self.root.quit()

    def choose_color(self):
        color = colorchooser.askcolor(title="Choose Color")[1]
        if color:
            self.current_color = color
            self.eraser_on = False
            self.size_slider.set(self.pen_width)
            self.update_status()

    def use_eraser(self):
        self.eraser_on = True
        self.current_color = self.themes[self.current_theme.get()]["canvas_bg"]
        self.size_slider.set(self.eraser_width)
        self.update_status()

    def clear_canvas(self):
        self.canvas.delete("all")
        self.send_message({"type": "clear"})
        self.own_strokes.clear()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.other_users_strokes.clear()
        self.undone_strokes.clear()

    def change_tool_size(self, value):
        size = int(value)
        if self.eraser_on:
            self.eraser_width = size
        else:
            self.pen_width = size
        self.update_status()

    def update_status(self):
        active_tool = "Eraser" if self.eraser_on else "Pen"
        width = self.eraser_width if self.eraser_on else self.pen_width
        self.status_label.config(
            text=f"Connected as {self.username} | Tool: {active_tool} | Size: {width} | Theme: {self.current_theme.get().capitalize()}",
            fg=self.themes[self.current_theme.get()]["text_fg"],
            bg=self.themes[self.current_theme.get()]["root_bg"]
        )

    def apply_theme(self, theme):
        self.current_theme.set(theme)
        theme_settings = self.themes[theme]
        self.canvas.config(bg=theme_settings["canvas_bg"])
        self.root.config(bg=theme_settings["root_bg"])
        self.toolbar.config(bg=theme_settings["toolbar_bg"])
        self.status_label.config(bg=theme_settings["root_bg"], fg=theme_settings["text_fg"])
        self.size_slider.config(bg=theme_settings["toolbar_bg"], fg=theme_settings["text_fg"])
        if self.eraser_on:
            self.current_color = theme_settings["canvas_bg"]
        self.update_status()

    def choose_custom_background(self):
        if self.current_theme.get() == "custom":
            color = colorchooser.askcolor(title="Choose Canvas Background")[1]
            if color:
                self.themes["custom"]["canvas_bg"] = color
                self.apply_theme("custom")

    def start_drawing(self, event):
        self.last_x, self.last_y = event.x, event.y
        self.current_stroke = []
        self.current_stroke_id = str(uuid.uuid4())  # Unique ID for this stroke
        self.send_message({"type": "status", "username": self.username, "status": "drawing"})

    def draw(self, event):
        if self.last_x is not None and self.last_y is not None:
            color = self.current_color
            width = self.eraser_width if self.eraser_on else self.pen_width
            line = {
                "type": "draw",
                "x1": self.last_x,
                "y1": self.last_y,
                "x2": event.x,
                "y2": event.y,
                "color": color,
                "width": width,
                "username": self.username,
                "stroke_id": self.current_stroke_id
            }
            self.canvas.create_line(line["x1"], line["y1"], line["x2"], line["y2"],
                                    fill=line["color"], width=line["width"], capstyle=tk.ROUND)
            self.current_stroke.append(line)
            self.send_message(line)
        self.last_x, self.last_y = event.x, event.y

    def stop_drawing(self, event):
        if self.current_stroke:
            self.own_strokes[self.current_stroke_id] = self.current_stroke
            self.undo_stack.append(self.current_stroke_id)
            self.redo_stack.clear()
            self.current_stroke = []
        self.last_x, self.last_y = None, None
        self.current_stroke_id = None
        self.send_message({"type": "status", "username": self.username, "status": "idle"})

    def undo(self):
        if self.undo_stack:
            stroke_id = self.undo_stack.pop()
            self.redo_stack.append(stroke_id)
            self.send_message({"type": "undo", "stroke_id": stroke_id, "username": self.username})
            if stroke_id in self.own_strokes:
                self.undone_strokes[stroke_id] = self.own_strokes[stroke_id]  # Store stroke for redo
                del self.own_strokes[stroke_id]
            self.redraw_canvas()

    def redo(self):
        if self.redo_stack:
            stroke_id = self.redo_stack.pop()
            self.undo_stack.append(stroke_id)
            if stroke_id in self.undone_strokes:
                self.own_strokes[stroke_id] = self.undone_strokes[stroke_id]  # Restore stroke locally
                # Send each line of the stroke to other clients
                for line in self.undone_strokes[stroke_id]:
                    self.send_message(line)  # Send draw message for each line
                del self.undone_strokes[stroke_id]  # Remove from undone strokes
            self.redraw_canvas()

    def redraw_canvas(self):
        self.canvas.delete("all")
        for stroke_id in self.undo_stack:
            stroke_lines = self.own_strokes.get(stroke_id, [])
            for line in stroke_lines:
                self.canvas.create_line(
                    line["x1"], line["y1"], line["x2"], line["y2"],
                    fill=line["color"], width=line["width"], capstyle=tk.ROUND
                )
        for user_strokes in self.other_users_strokes.values():
            for stroke_lines in user_strokes.values():
                for line in stroke_lines:
                    self.canvas.create_line(
                        line["x1"], line["y1"], line["x2"], line["y2"],
                        fill=line["color"], width=line["width"], capstyle=tk.ROUND
                    )

    def send_message(self, message):
        try:
            data = json.dumps(message).encode('utf-8') + b'\n'
            self.client_socket.sendall(data)
        except Exception as e:
            print(f"Error sending message: {e}")

    def receive_data(self):
        buffer = ''
        while self.running:
            try:
                data = self.client_socket.recv(4096).decode('utf-8')
                if not data:
                    break
                buffer += data
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line:
                        message = json.loads(line)
                        self.root.after(0, self.process_message, message)
            except Exception as e:
                break

    def process_message(self, message):
        msg_type = message.get("type")
        if msg_type == "draw":
            stroke_id = message.get("stroke_id")
            if message["username"] != self.username:
                user_strokes = self.other_users_strokes.setdefault(message["username"], {})
                stroke = user_strokes.setdefault(stroke_id, [])
                stroke.append(message)
                self.canvas.create_line(
                    message["x1"], message["y1"],
                    message["x2"], message["y2"],
                    fill=message["color"],
                    width=message["width"],
                    capstyle=tk.ROUND
                )
        elif msg_type == "clear":
            self.canvas.delete("all")
            self.other_users_strokes.clear()
            self.own_strokes.clear()
            self.undone_strokes.clear()
        elif msg_type == "join":
            self.status_label.config(text=f"{message['username']} joined")
        elif msg_type == "leave":
            self.status_label.config(text=f"{message['username']} left")
            if message["username"] in self.drawing_bubbles:
                self.drawing_bubbles[message["username"]].destroy()
                del self.drawing_bubbles[message["username"]]
            if message["username"] in self.other_users_strokes:
                del self.other_users_strokes[message["username"]]
        elif msg_type == "status":
            if message["status"] == "drawing":
                self.show_drawing_bubble(message["username"])
            else:
                self.hide_drawing_bubble(message["username"])
        elif msg_type == "undo":
            stroke_id = message.get("stroke_id")
            if message["username"] != self.username:
                strokes = self.other_users_strokes.get(message["username"], {})
                if stroke_id in strokes:
                    del strokes[stroke_id]
                self.redraw_canvas()
        elif msg_type == "redo":
            stroke_id = message.get("stroke_id")
            username = message.get("username")
            if username != self.username:
                user_strokes = self.other_users_strokes.get(username, {})
                # Redo is handled via draw messages, so no action needed here
                pass

    def show_drawing_bubble(self, username):
        if username == self.username:
            return
        if username in self.drawing_bubbles:
            return
        bubble = tk.Label(self.canvas, text=f"{username} is drawing...",
                          bg="lightyellow",
                          fg=self.themes[self.current_theme.get()]["text_fg"],
                          relief="solid")
        bubble.place(x=10, y=10 + 20 * len(self.drawing_bubbles))
        self.drawing_bubbles[username] = bubble

    def hide_drawing_bubble(self, username):
        bubble = self.drawing_bubbles.pop(username, None)
        if bubble:
            bubble.destroy()

    def on_closing(self):
        self.running = False
        self.send_message({"type": "leave", "username": self.username})
        self.client_socket.close()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = WhiteboardApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()