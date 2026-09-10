import network
import socket
import machine
import dht
import time
import json
import ssd1306

# ==========================================
# CONFIGURATION & PINS
# ==========================================
AP_SSID = "smart-garden"
AP_PASSWORD = "enikariyilla" # Must be at least 8 characters

# Pin Definitions
PIN_DHT           = 4   # DHT22 Air Sensor
PIN_SOIL_MOISTURE = 32  # Soil Moisture Sensor (Analog ADC1)
PIN_LIGHT_LDR     = 35  # LDR Light Sensor (Analog ADC1)
PIN_FLOAT_LEVEL   = 33  # Float Level Sensor (Digital input)
PIN_MOTOR         = 26  # Relay module triggering the Water Pump
PIN_SDA           = 21  # OLED SDA
PIN_SCL           = 22  # OLED SCL

# ==========================================
# INITIALIZATION
# ==========================================
# 1. Motor / Relay (Start OFF)
motor = machine.Pin(PIN_MOTOR, machine.Pin.OUT)
motor.value(0)

# 2. Float Level Sensor (Digital with Pull-Up)
float_sensor = machine.Pin(PIN_FLOAT_LEVEL, machine.Pin.IN, machine.Pin.PULL_UP)

# 3. Analog Sensors (Soil Moisture & LDR)
adc_soil = machine.ADC(machine.Pin(PIN_SOIL_MOISTURE))
adc_soil.atten(machine.ADC.ATTN_11V)

adc_light = machine.ADC(machine.Pin(PIN_LIGHT_LDR))
adc_light.atten(machine.ADC.ATTN_11V)

# 4. DHT22 Air Sensor
sensor_dht = dht.DHT22(machine.Pin(PIN_DHT))

# 5. OLED Display
try:
    i2c = machine.SoftI2C(scl=machine.Pin(PIN_SCL), sda=machine.Pin(PIN_SDA))
    oled = ssd1306.SSD1306_I2C(128, 64, i2c)
    oled.fill(0)
    oled.text("Starting AP...", 0, 0)
    oled.show()
except Exception as e:
    print("OLED Init Error:", e)
    oled = None

# ==========================================
# HTML FRONTEND 
# ==========================================
HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
    <title>Smart Plant Telemetry</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: 'Segoe UI', Tahoma, sans-serif; background-color: #121212; color: #ffffff; text-align: center; margin: 0; padding: 20px; }
        h1 { color: #00d2ff; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; max-width: 900px; margin: 20px auto; }
        .card { background: #1e1e1e; padding: 25px; border-radius: 12px; box-shadow: 0 4px 8px rgba(0,0,0,0.3); border-top: 4px solid #00d2ff; }
        .card h3 { margin: 0 0 10px 0; color: #a0a0a0; font-size: 1.2em; text-transform: uppercase; }
        .value { font-size: 2.5em; font-weight: bold; color: #4CAF50; }
        .error { color: #ff4c4c; font-size: 1.2em; }
        .motor-btn { width: 100%; padding: 15px; font-size: 1.5em; font-weight: bold; color: white; border: none; border-radius: 8px; cursor: pointer; transition: 0.3s; }
        .motor-on { background-color: #f44336; box-shadow: 0 0 15px #f44336; }
        .motor-off { background-color: #4CAF50; box-shadow: 0 0 15px #4CAF50; }
    </style>
</head>
<body>
    <h1>Plant Telemetry Dashboard</h1>
    
    <div class="card" style="max-width: 900px; margin: 0 auto 20px auto; border-top: 4px solid #ff9800;">
        <h3>Water Pump Control</h3>
        <button id="motor_btn" class="motor-btn motor-off" onclick="toggleMotor()">Loading...</button>
    </div>

    <div class="grid">
        <div class="card"><h3>Air Temperature</h3><div id="air_temp" class="value">-- &deg;C</div></div>
        <div class="card"><h3>Air Humidity</h3><div id="air_hum" class="value">-- %</div></div>
        <div class="card"><h3>Soil Moisture</h3><div id="soil_moist" class="value">--</div></div>
        <div class="card"><h3>Light Level</h3><div id="light" class="value">--</div></div>
        <div class="card"><h3>Tank Water Level</h3><div id="water_lvl" class="value">--</div></div>
    </div>
    
    <script>
        function updateUI(id, val, unit) {
            const el = document.getElementById(id);
            if (val === "Error") el.innerHTML = `<span class="error">${val}</span>`;
            else el.innerHTML = val + unit;
        }

        function updateMotorBtn(state) {
            const btn = document.getElementById('motor_btn');
            if(state === 1) {
                btn.className = "motor-btn motor-on";
                btn.innerHTML = "PUMP IS ON (Tap to turn OFF)";
            } else {
                btn.className = "motor-btn motor-off";
                btn.innerHTML = "PUMP IS OFF (Tap to turn ON)";
            }
        }

        function toggleMotor() {
            fetch('/motor/toggle')
                .then(res => res.json())
                .then(data => updateMotorBtn(data.motor))
                .catch(err => console.error(err));
        }

        function fetchData() {
            fetch('/data').then(res => res.json()).then(data => {
                updateUI('air_temp', data.air_temp, ' &deg;C'); 
                updateUI('air_hum', data.air_hum, ' %');
                updateUI('soil_moist', data.soil_moist, ''); 
                updateUI('light', data.light, '');
                updateUI('water_lvl', data.water_lvl, '');
                updateMotorBtn(data.motor); 
            }).catch(err => console.error(err));
        }
        
        setInterval(fetchData, 1000); fetchData();
    </script>
</body>
</html>
"""

# ==========================================
# CORE LOGIC
# ==========================================
def host_wifi():
    sta = network.WLAN(network.STA_IF)
    sta.active(False)
    
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid=AP_SSID, password=AP_PASSWORD)
    
    while not ap.active():
        time.sleep(0.1)
        
    ip = ap.ifconfig()[0]
    print('Broadcasting Wi-Fi:', AP_SSID)
    print('Web Server IP:', ip)
    return ip

def get_sensor_data():
    float_val = "OK (Normal)" if float_sensor.value() == 1 else "LOW (Refill!)"
    
    data = {
        "air_temp": "Error", 
        "air_hum": "Error", 
        "soil_moist": "Error",
        "light": "Error",
        "water_lvl": float_val,
        "motor": motor.value() 
    }
    
    try: data["soil_moist"] = adc_soil.read()
    except: pass

    try: data["light"] = adc_light.read()
    except: pass
    
    try:
        sensor_dht.measure()
        data["air_temp"] = round(sensor_dht.temperature(), 1)
        data["air_hum"] = round(sensor_dht.humidity(), 1)
    except: pass
    
    return data

def update_oled_display(data, ip):
    if not oled: return
    try:
        oled.fill(0)
        oled.text(f"IP:{ip}", 0, 0)
        oled.text(f"Air: {data['air_temp']}C {data['air_hum']}%", 0, 13)
        oled.text(f"Soil:{data['soil_moist']} Lgt:{data['light']}", 0, 26)
        
        tank_status = "OK" if 'OK' in str(data['water_lvl']) else "LOW"
        m_state = "ON" if data['motor'] else "OFF"
        oled.text(f"Tank:{tank_status} M:{m_state}", 0, 39)
        
        oled.show()
    except Exception as e:
        print("OLED Draw Error:", e)

# ==========================================
# NON-BLOCKING SERVER LOOP
# ==========================================
def start_server():
    ip = host_wifi()
    
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('', 80))
    s.listen(5)
    s.settimeout(0.2) 
    
    last_read_time = 0
    current_data = get_sensor_data()

    while True:
        now = time.ticks_ms()
        
        if time.ticks_diff(now, last_read_time) >= 1000:
            current_data = get_sensor_data()
            update_oled_display(current_data, ip)
            last_read_time = now

        try:
            conn, addr = s.accept()
            request = conn.recv(1024)
            req_str = str(request)
            
            if req_str.find('GET /motor/toggle') != -1:
                motor.value(not motor.value())
                resp = 'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{"motor": ' + str(motor.value()) + '}'
                conn.sendall(resp.encode('utf-8'))
                
            elif req_str.find('GET /data') != -1:
                json_str = json.dumps(current_data)
                resp = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nAccess-Control-Allow-Origin: *\r\n\r\n" + json_str
                conn.sendall(resp.encode('utf-8'))
                
            elif req_str.find('GET / ') != -1:
                resp = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n" + HTML_PAGE
                conn.sendall(resp.encode('utf-8'))
                
            else:
                resp = "HTTP/1.1 404 Not Found\r\n\r\n"
                conn.sendall(resp.encode('utf-8'))
            
            conn.close()
            
        except OSError:
            pass
        except Exception as e:
            print("Server exception:", e)
            try: conn.close()
            except: pass

if __name__ == "__main__":
    start_server()