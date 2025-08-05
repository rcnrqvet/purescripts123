import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path

import websockets
from pynput import mouse, keyboard
from PyQt5 import QtWidgets, QtGui, QtCore

# --- CONFIG --- 
LICENSE_FILE = "license.key"
LICENSE_SERVER_URL = "http://localhost:5000/verify"  # Replace with your real license server URL
WEBSOCKET_HOST = "localhost"
WEBSOCKET_PORT = 8765

# Dummy recoil patterns for demo:
RECOIL_PATTERNS = {
    "default": [(0, 0)],
    "operator1": [(1, -2), (1, -2), (0, -1)],
    "operator2": [(2, -1), (2, -1), (1, -1)],
}

# Globals
current_operator = "default"
sensitivity = 1.0
is_running = False
ws_clients = set()


# --- License validation functions ---

def load_local_license():
    if Path(LICENSE_FILE).exists():
        return Path(LICENSE_FILE).read_text().strip()
    return None


async def verify_license_remote(license_key):
    # This should do a real HTTPS POST request to your license server
    # For now, dummy success for demo
    await asyncio.sleep(0.5)
    # Return True/False + message
    if license_key == "VALID-LICENSE-KEY":
        return True, "License is valid."
    else:
        return False, "Invalid license key."


def save_license_locally(license_key):
    Path(LICENSE_FILE).write_text(license_key)


# --- Mouse movement (using pynput) ---

mouse_controller = mouse.Controller()

def apply_recoil_pattern():
    global is_running, current_operator, sensitivity

    while True:
        if is_running:
            pattern = RECOIL_PATTERNS.get(current_operator, RECOIL_PATTERNS["default"])
            for dx, dy in pattern:
                scaled_dx = dx * sensitivity
                scaled_dy = dy * sensitivity
                mouse_controller.move(scaled_dx, scaled_dy)
                time.sleep(0.03)  # Adjust delay for fire rate etc.
        else:
            time.sleep(0.1)


# --- WebSocket server handler ---

async def handle_client(websocket, path):
    global current_operator, sensitivity, is_running

    ws_clients.add(websocket)
    try:
        async for message in websocket:
            # Expect JSON messages from frontend
            try:
                data = json.loads(message)
            except:
                await websocket.send(json.dumps({"error": "Invalid JSON"}))
                continue

            # License verification request
            if data.get("action") == "verify_license":
                license_key = data.get("license_key", "")
                valid, msg = await verify_license_remote(license_key)
                if valid:
                    save_license_locally(license_key)
                await websocket.send(json.dumps({"action": "license_response", "valid": valid, "msg": msg}))
                continue

            # Reject commands if license not valid locally
            local_key = load_local_license()
            if not local_key:
                await websocket.send(json.dumps({"error": "No valid license found"}))
                continue

            # Settings update commands
            if data.get("action") == "update_settings":
                current_operator = data.get("operator", current_operator)
                sensitivity = float(data.get("sensitivity", sensitivity))
                is_running = data.get("running", is_running)
                await websocket.send(json.dumps({"action": "settings_updated"}))

    finally:
        ws_clients.remove(websocket)


# --- Run WebSocket server in separate thread ---

def start_ws_server():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    start_server = websockets.serve(handle_client, WEBSOCKET_HOST, WEBSOCKET_PORT)
    loop.run_until_complete(start_server)
    loop.run_forever()


# --- Qt Overlay (basic crosshair example) ---

class OverlayWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setGeometry(800, 450, 20, 20)  # Position near center, adjust as needed

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 0, 255, 180), 3))
        painter.drawLine(10, 0, 10, 20)
        painter.drawLine(0, 10, 20, 10)


def start_overlay():
    app = QtWidgets.QApplication(sys.argv)
    overlay = OverlayWidget()
    overlay.show()
    sys.exit(app.exec_())


# --- Main ---

if __name__ == "__main__":
    # Start recoil thread
    recoil_thread = threading.Thread(target=apply_recoil_pattern, daemon=True)
    recoil_thread.start()

    # Start WebSocket server thread
    ws_thread = threading.Thread(target=start_ws_server, daemon=True)
    ws_thread.start()

    # Start overlay GUI (this blocks main thread)
    start_overlay()
