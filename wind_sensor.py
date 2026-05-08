import socket
import math
import tkinter as tk
from collections import deque
import numpy as np

MCAST_ADDR = "239.192.0.4"
PORT = 60004
INTERFACE_IP = "131.217.64.26" 

# -----------------------
# Networking
# -----------------------
def create_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", PORT))

    membership = socket.inet_aton(MCAST_ADDR) + socket.inet_aton(INTERFACE_IP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)

    sock.setblocking(False)  # important for GUI
    return sock


def read_packet(sock):
    try:
        data, _ = sock.recvfrom(1024)
        text = data.decode("ascii").strip()
        parts = text.split(",")

        direction_deg = float(parts[2])
        speed_mps = float(parts[4])

        return direction_deg, speed_mps
    except:
        return None, None


# -----------------------
# GUIs
# -----------------------
class WindWidget:
    def __init__(self, root, sock):
        self.sock = sock

        self.canvas = tk.Canvas(root, width=300, height=300, bg="#333333")
        self.canvas.pack()
        self.canvas.create_text(150,20, text="N", fill="white", font=("Ariel",16))
        self.canvas.create_text(280,150, text="E", fill="white", font=("Ariel",16))
        self.canvas.create_text(150,280, text="S", fill="white", font=("Ariel",16))
        self.canvas.create_text(20,150, text="W", fill="white", font=("Ariel",16))

        self.label = self.canvas.create_text(15, 15,
                                             text="0 km/h", font=("Arial", 18),
                                             fill="white",
                                             anchor=tk.NW)
        self.label15av = self.canvas.create_text(15, 285,
                                                 text="15s: 0 km/h",
                                                 font=("Arial", 14),
                                                 fill="white",
                                                 anchor=tk.SW)
        self.label60av = self.canvas.create_text(15, 265,
                                                 text="60s: 0 km/h",
                                                 font=("Arial", 14),
                                                 fill="white",
                                                 anchor=tk.SW)
        
        self.axes1 = self.canvas.create_line(150, 40, 150, 260, fill="#aaa",
                                            tags="overlay")
        self.axes2 = self.canvas.create_line(40, 150, 260, 150, fill="#aaa",
                                            tags="overlay")
        self.circle = self.canvas.create_oval(50,50,250,250, outline="#aaa",
                                            tags="overlay")
        
        
        # self.label.pack()

        self.center = (150, 150)
        self.radius = 100

        # draw initial arrow
        self.arrow = None
        self.current_angle = 0.0
        self.target_angle = 0.0
        self.smoothing = 0.15  # 0.05 = very smooth, 0.3 = snappy
        self.windspeeds = deque()
        self.directions = deque()
        self.wind60av = 0.0
        self.wind60sd = 0.0
        self.dir60av = 0.0
        self.dir60sd = 0.0
        self.wind15av = 0.0
        self.wind15sd = 0.0
        self.dir15av = 0.0
        self.dir15sd = 0.0
        self.counter = 0
        self.c = None
        self.c15 = "white"
        self.c60 = "white"

        self.update()

    def draw_arrow(self, angle_rad, color="#99ff99"):
        cx, cy = self.center
        r = self.radius

        # arrow ends
        shorten = 30
        x = cx + (r-shorten) * math.sin(angle_rad)
        y = cy - (r-shorten) * math.cos(angle_rad)
        ex = cx - (r-shorten) * math.sin(angle_rad)
        ey = cy + (r-shorten) * math.cos(angle_rad)
        
        if self.arrow:
            self.canvas.delete(self.arrow)

        self.arrow = self.canvas.create_line(
            ex, ey, x, y,
            fill=color,
            width=3,
            arrow=tk.LAST
        )
    
    def draw_wedge(self, outer_angle_rad, outer_std_deg, inner_angle_rad, inner_std_deg):

        cx, cy = self.center
        r_outer = self.radius
        r_inner = self.radius * 0.80   # inner wedge smaller
        
        # std_deg is a single standard deviation
        outer_half = outer_std_deg
        inner_half = inner_std_deg
    
        # convert to Tk coords
        outer_deg = math.degrees(outer_angle_rad)
        inner_deg = math.degrees(inner_angle_rad)
    
        outer_start = 90 - (outer_deg + outer_half)
        inner_start = 90 - (inner_deg + inner_half)
    
        # delete old
        if hasattr(self, "wedge1"):
            self.canvas.delete(self.wedge1)
        if hasattr(self, "wedge2"):
            self.canvas.delete(self.wedge2)
    
        # --- outer wedge ---
        self.wedge1 = self.canvas.create_arc(
            cx - r_outer, cy - r_outer,
            cx + r_outer, cy + r_outer,
            start=outer_start,
            extent=2*outer_std_deg,
            fill="#444444",
            outline=""
        )
    
        # --- inner wedge (smaller radius) ---
        self.wedge2 = self.canvas.create_arc(
            cx - r_inner, cy - r_inner,
            cx + r_inner, cy + r_inner,
            start=inner_start,
            extent=2*inner_std_deg,
            fill="#666666",
            outline=""
        )
    
    def circular_mean_std(self, angles_deg):
        angles_rad = np.radians(angles_deg)
    
        sin_sum = np.mean(np.sin(angles_rad))
        cos_sum = np.mean(np.cos(angles_rad))
    
        mean_angle = math.atan2(sin_sum, cos_sum)
    
        # circular std dev
        R = math.sqrt(sin_sum**2 + cos_sum**2)
        std = math.sqrt(-2 * math.log(R)) if R > 0 else 0
    
        return math.degrees(mean_angle), math.degrees(std)

    def update(self):
        interval = 15  # update interval on average calculations
        minsp = 5
        maxsp = 30
        Noffset = 30
        direction, speed = read_packet(self.sock)
        if direction is not None:
            # North is sort of offset
            direction = direction + Noffset
        if self.c is None:
            self.c = "#99ff99"
            
        def var_colour(percent):
            '''
            Generates a variable colour based on percentage input.
            0% = green
            100% = red
            Smooth-ish transition between them. Arbitrarily chosen by what I
            think looks good
            '''
            r = int(25.5 * math.sqrt(percent))
            g = int(255-2.55*percent)
            b = 50
            # return a hexcode colour
            return f"#{r:02x}{g:02x}{b:02x}"
        
        # maintain a 60s windspeed 'history'
        if direction is not None and speed is not None and speed > 1:
            self.windspeeds.append(speed)
            self.directions.append(direction)
            
            if len(self.windspeeds) > 60:
                self.windspeeds.popleft()  # drop oldest entry
                self.directions.popleft()
           
        if direction is not None:
            self.target_angle = math.radians(direction)
    
            speed_kph = speed * 3.6
            self.canvas.itemconfig(self.label, text=f"{speed_kph:.1f} km/h")
            # ignore this jank, basically:
                # 0-min km/h is always 0% (max(speed, 10))
                # min-max km/h ramps up in percentage 
                # anything over max km/h is 100% 
            percent = 100*((min(max(speed_kph,minsp)-minsp,maxsp)/maxsp))
            self.c = var_colour(percent)
            
            # calculate some statistics every interval seconds
            #if self.counter % interval == 0 and self.counter >= 1:
            self.wind60av = np.mean(self.windspeeds)
            self.wind60sd = np.std(self.windspeeds)
            # stats on last interval seconds
            self.wind15av = np.mean(list(self.windspeeds)[-interval:])
            self.wind15sd = np.std(list(self.windspeeds)[-interval:])
            self.dir60av, self.dir60sd = self.circular_mean_std(list(self.directions))
            self.dir15av, self.dir15sd = self.circular_mean_std(list(self.directions)[-interval:])
            p15 = 100*((min(max(self.wind15av*3.6,minsp)-minsp,maxsp)/maxsp))
            p60 = 100*((min(max(self.wind60av*3.6,minsp)-minsp,maxsp)/maxsp))
            self.c15 = var_colour(p15)
            self.c60 = var_colour(p60)
            self.canvas.itemconfig(self.label15av,
                                   text=f"15s: {self.wind15av*3.6:.1f} km/h",
                                   fill=self.c15)
            self.canvas.itemconfig(self.label60av,
                                   text=f"60s: {self.wind60av*3.6:.1f} km/h",
                                   fill=self.c60)
            
        # --- Smooth angle interpolation ---
        delta = self.target_angle - self.current_angle
    
        # wrap-around fix (important!)
        delta = (delta + math.pi) % (2 * math.pi) - math.pi
    
        self.current_angle += delta * self.smoothing
        self.draw_wedge(math.radians(self.dir60av), self.dir60sd,
                        math.radians(self.dir15av), self.dir15sd)
        
        self.draw_arrow(self.current_angle, color=self.c)
        self.canvas.tag_raise("overlay")
        self.canvas.tag_raise(self.arrow)   # keep arrow on top too
        self.canvas.tag_raise(self.label)   # keep text visible
        self.canvas.after(50, self.update)  # faster refresh = smoother
        self.counter += 1
        
        


# -----------------------
# Main
# -----------------------
def main():
    sock = create_socket()

    root = tk.Tk()
    root.title("Wind Monitor")

    app = WindWidget(root, sock)

    root.mainloop()


if __name__ == "__main__":
    main()