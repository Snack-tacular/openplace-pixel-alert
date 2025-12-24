import threading
import time
import tkinter as tk
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from win10toast import ToastNotifier
import warnings
import re
import pystray
from PIL import Image, ImageDraw

warnings.filterwarnings("ignore", category=UserWarning)

URL = "https://openplace.live/me"
CHECK_INTERVAL = 3
toaster = ToastNotifier()
monitoring = False
driver = None
root = None
status_var = None
timer_var = None
full_time_var = None
login_btn = None
alert_cooldown = False
previous_cooldown = None
cooldown_alert_cooldown = False
current_pixels = 0
max_pixels = 0
last_full_time = 0
tray_icon = None
tray_thread = None
drag_start_x = 0
drag_start_y = 0
login_ready_var = None
overlay_label = None
status_frame = None

def create_tray_icon():
    image = Image.new('RGB', (64, 64), color='#1e1e1e')
    dc = ImageDraw.Draw(image)
    dc.rectangle([16, 16, 48, 48], fill='#00ff88')
    dc.text((28, 28), "P", fill='black')
    return image.resize((16, 16))

def position_bottom_right():
    root.update_idletasks()
    root.update()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    window_width = root.winfo_width() or 220
    window_height = root.winfo_height() or 280
    x = screen_width - window_width - 10
    y = screen_height - window_height - 50
    root.geometry(f"{int(window_width)}x{int(window_height)}+{int(x)}+{int(y)}")

def start_drag(event):
    global drag_start_x, drag_start_y
    drag_start_x = event.x_root - root.winfo_x()
    drag_start_y = event.y_root - root.winfo_y()

def do_drag(event):
    x = event.x_root - drag_start_x
    y = event.y_root - drag_start_y
    root.geometry(f"+{x}+{y}")

def format_time(minutes_total):
    hours = int(minutes_total // 60)
    minutes = int(minutes_total % 60)
    return f"{hours:02d}:{minutes:02d}"

def format_datetime(seconds_from_now):
    full_time = time.time() + seconds_from_now
    return time.strftime("%H:%M", time.localtime(full_time))

def update_recharge_timer():
    global current_pixels, max_pixels
    if current_pixels > 0 and max_pixels > 0 and previous_cooldown:
        pixels_needed = max_pixels - current_pixels
        if pixels_needed > 0:
            # ✅ Show countdown when charging
            pixels_per_second = 1000 / previous_cooldown
            minutes_needed = (pixels_needed / pixels_per_second) / 60
            timer_var.set(f"⏱️ {format_time(minutes_needed)}")
            full_time_var.set(f"⏰ {format_datetime(pixels_needed / pixels_per_second)}")
        else:
            # ✅ Show "FULL" when pixels are full
            timer_var.set("✅ FULL")
            full_time_var.set("⏰ FULL")
    else:
        timer_var.set("")
        full_time_var.set("")

def setup_driver(visible=True):
    global driver
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=300,650")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

def get_pixel_counts():
    global driver, previous_cooldown, current_pixels, max_pixels, last_full_time
    if driver is None:
        return None, None, None
    
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)
        
        page_text = driver.page_source
        
        count_match = re.search(r'"count"\s*:\s*([\d.]+)', page_text)
        max_match = re.search(r'"max"\s*:\s*([\d.]+)', page_text)
        cooldown_match = re.search(r'"cooldownMs"\s*:\s*(\d+)', page_text)
        
        if count_match and max_match and cooldown_match:
            current = float(count_match.group(1))
            maximum = float(max_match.group(1))
            cooldown = int(cooldown_match.group(1))
            print(f"✅ PARSED - count: {current}, max: {maximum}, cooldown: {cooldown}ms")
            
            current_pixels = int(current)
            max_pixels = int(maximum)
            
            if int(current) >= int(maximum) and last_full_time == 0:
                last_full_time = time.time()
            
            if previous_cooldown is not None and previous_cooldown != cooldown:
                cooldown_msg = "30s → 2s" if cooldown == 2000 else "2s → 30s"
                notify_cooldown_change(cooldown_msg)
            
            previous_cooldown = cooldown
            update_recharge_timer()
            return int(current), int(maximum), cooldown
        
        return None, None, None
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return None, None, None

def show_overlay(text, color="#ff6600", duration=5000):
    """✅ SHOW ANY TEXT in EXTRA OVERLAY BOX"""
    global overlay_label
    overlay_label.config(text=text, fg="white", bg=color, font=("Consolas", 12, "bold"))
    overlay_label.place(in_=status_frame, x=0, y=0, relwidth=1, relheight=1)
    if duration > 0:
        root.after(duration, hide_overlay)

def hide_overlay():
    """✅ HIDE OVERLAY BOX"""
    global overlay_label
    overlay_label.place_forget()

def notify_cooldown_change(change_msg):
    global cooldown_alert_cooldown
    if cooldown_alert_cooldown:
        return
    
    import subprocess
    subprocess.Popen('powershell -c "[console]::beep(600,500); [console]::beep(1000,500); [console]::beep(800,1000)"', 
                     creationflags=subprocess.CREATE_NO_WINDOW, shell=True)
    
    show_overlay(f"🔄 COOLDOWN\n{change_msg}", "#ff9900")
    cooldown_alert_cooldown = True

def notify(current, maximum):
    global alert_cooldown
    if alert_cooldown:
        return
    
    import subprocess
    subprocess.Popen('powershell -c "[console]::beep(400,800); [console]::beep(1200,600)"', 
                     creationflags=subprocess.CREATE_NO_WINDOW, shell=True)
    
    show_overlay(f"✅ PIXELS FULL!\nPLACE NOW!", "#4CAF50")
    alert_cooldown = True

def monitor_loop():
    global monitoring, alert_cooldown, cooldown_alert_cooldown
    while monitoring:
        try:
            driver.refresh()
            time.sleep(3)
            
            result = get_pixel_counts()
            current = result[0] if result and result[0] is not None else None
            maximum = result[1] if result and len(result)>1 and result[1] is not None else None
            cooldown = result[2] if result and len(result)>2 and result[2] is not None else None
            
            if current is not None and maximum is not None and cooldown is not None:
                status_var.set(f"📊{int(current)}/{int(maximum)} 🔄{cooldown/1000:.0f}s")
                
                if int(current) >= int(maximum):
                    notify(int(current), int(maximum))
                    time.sleep(10)
                    continue
                else:
                    alert_cooldown = False
                
                cooldown_alert_cooldown = False
            else:
                status_var.set("📊 Refreshing...")
            
            time.sleep(CHECK_INTERVAL - 3)
        except Exception as e:
            print(f"Monitor error: {e}")
            status_var.set("📊 Waiting...")
            time.sleep(CHECK_INTERVAL)

def on_login_ready():
    global login_ready_var, monitoring
    login_ready_var.set(1)
    status_var.set("Loading /me...")
    hide_overlay()
    root.update()
    
    try:
        driver.get(URL)
        time.sleep(3)
        
        result = get_pixel_counts()
        current = result[0] if result and result[0] is not None else None
        maximum = result[1] if result and len(result)>1 and result[1] is not None else None
        
        if current is not None and maximum is not None:
            login_ready_btn.pack_forget()
            status_var.set(f"📊{int(current)}/{int(maximum)} 🔄{result[2]/1000:.0f}s")
            driver.minimize_window()
            monitoring = True
            thread = threading.Thread(target=monitor_loop, daemon=True)
            thread.start()
        else:
            status_var.set("❌ No data - Check login")
    except Exception as e:
        status_var.set(f"❌ Error: {str(e)[:50]}...")

def test_connection():
    global driver
    try:
        if driver is None:
            status_var.set("🌐 Starting...")
            root.update()
            setup_driver(visible=True)
        
        driver.get("https://openplace.live/")
        status_var.set("📊 --/-- 🔄--s")
        
        # ✅ LOGIN INSTRUCTIONS IN OVERLAY BOX
        show_overlay("🔐 LOGIN IN CHROME\nTHEN LOGIN READY", "#9800ff")
        
        # REPLACE LOGIN → LOGIN READY
        login_btn.pack_forget()
        login_ready_btn.pack(pady=5)
        
    except Exception as e:
        status_var.set(f"❌ Error: {str(e)[:50]}...")

def show_window(icon=None, item=None):
    global tray_icon
    if tray_icon:
        try:
            tray_icon.stop()
        except Exception:
            pass
        tray_icon = None
    
    root.deiconify()
    root.lift()
    root.attributes('-topmost', True)
    root.after(50, lambda: position_bottom_right())
    root.after(100, lambda: root.attributes('-topmost', False))

def minimize_window():
    global tray_icon, tray_thread
    root.withdraw()
    if tray_icon:
        try:
            tray_icon.stop()
        except Exception:
            pass
    tray_icon = setup_tray()
    tray_thread = threading.Thread(target=tray_icon.run, daemon=True)
    tray_thread.start()

def close_window():
    quit_app(None)

def quit_app(icon_item=None):
    global monitoring, driver, tray_icon, tray_thread
    monitoring = False
    try:
        if driver:
            driver.quit()
    except Exception:
        pass
    try:
        if tray_icon:
            tray_icon.stop()
    except Exception:
        pass
    try:
        if tray_thread and tray_thread.is_alive():
            tray_thread.join(timeout=1)
    except Exception:
        pass
    try:
        root.quit()
        root.destroy()
    except Exception:
        pass

def setup_tray():
    global tray_icon
    try:
        if tray_icon:
            tray_icon.stop()
    except Exception:
        pass
    image = create_tray_icon()
    menu = (
        pystray.MenuItem("📱 Show", show_window, default=True),
        pystray.MenuItem("❌ Quit", quit_app)
    )
    tray_icon = pystray.Icon("PixelAlarm", image, "Pixel Alarm", menu=menu)
    return tray_icon

def build_gui():
    global root, status_var, timer_var, full_time_var, login_btn, tray_thread, login_ready_var, login_ready_btn, overlay_label, status_frame
    
    root = tk.Tk()
    root.geometry("180x200")
    root.configure(bg="#1e1e1e")
    root.resizable(True, True)
    
    login_ready_var = tk.IntVar(value=0)
    
    # Title bar
    title_frame = tk.Frame(root, bg="#2d2d2d", height=25)
    title_frame.pack(fill='x', padx=5, pady=(5,0))
    title_frame.pack_propagate(False)
    
    title_label = tk.Label(title_frame, text="PIXEL ALARM", bg="#2d2d2d", fg="#00ff88", 
                          font=("Arial", 10, "bold"))
    title_label.pack(side='left', padx=8, pady=4)
    
    close_btn = tk.Button(title_frame, text="✕", command=close_window,
                         bg="#cc0000", fg="white", font=("Arial", 9, "bold"),
                         width=3, height=1, relief="flat", bd=0)
    close_btn.pack(side='right')
    
    min_btn = tk.Button(title_frame, text="−", command=minimize_window,
                       bg="#666", fg="white", font=("Arial", 9, "bold"),
                       width=3, height=1, relief="flat", bd=0)
    min_btn.pack(side='right', padx=(0,2))
    
    title_frame.bind('<Button-1>', start_drag)
    title_frame.bind('<B1-Motion>', do_drag)
    title_label.bind('<Button-1>', start_drag)
    title_label.bind('<B1-Motion>', do_drag)
    
    # Main content
    main_frame = tk.Frame(root, bg="#1e1e1e")
    main_frame.pack(fill='both', expand=True, padx=10, pady=5)
    
    # STATUS FRAME - CONTAINER for pixel count + overlay
    status_frame = tk.Frame(main_frame, bg="#2d2d2d", height=35)
    status_frame.pack(pady=2, fill='x')
    status_frame.pack_propagate(False)
    
    # Pixel count - BASE LAYER
    status_var = tk.StringVar(value="📊 --/-- 🔄--s")
    status_label = tk.Label(status_frame, textvariable=status_var, bg="#2d2d2d", fg="#ffffff", 
                           font=("Consolas", 13, "bold"))
    status_label.place(relx=0.5, rely=0.5, anchor="center")
    
    # OVERLAY BOX - ALL POPUP TEXT
    overlay_label = tk.Label(status_frame, text="", bg="#ff6600", fg="white", 
                           font=("Consolas", 10, "bold"), justify="center")
    overlay_label.place_forget()
    
    # Timers
    timer_var = tk.StringVar(value="")
    timer_label = tk.Label(main_frame, textvariable=timer_var, bg="#1e1e1e", fg="#ffaa00", 
                          font=("Consolas", 20, "bold"))
    timer_label.pack(pady=5)
    timer_label.config(anchor="center")
    
    full_time_var = tk.StringVar(value="")
    full_time_label = tk.Label(main_frame, textvariable=full_time_var, bg="#1e1e1e", fg="#88ccff", 
                              font=("Consolas", 20, "bold"))
    full_time_label.pack(pady=2)
    full_time_label.config(anchor="center")
    
    login_btn = tk.Button(main_frame, text="LOGIN", command=test_connection,
                         bg="#FF9800", fg="white", font=("Consolas", 12, "bold"), 
                         relief="flat", bd=0, padx=20, pady=8)
    login_btn.pack(pady=10)
    
    login_ready_btn = tk.Button(main_frame, text="LOGIN READY", command=on_login_ready,
                               bg="#4CAF50", fg="white", font=("Consolas", 12, "bold"),
                               relief="flat", bd=0, padx=20, pady=8)
    login_ready_btn.pack_forget()
    
    root.overrideredirect(True)
    root.attributes('-topmost', True)
    
    position_bottom_right()
    tray_icon = setup_tray()
    tray_thread = threading.Thread(target=tray_icon.run, daemon=True)
    tray_thread.start()
    
    root.mainloop()

if __name__ == "__main__":
    build_gui()
