"""
USB Phone Camera Manager Service.
Handles detection of Android devices connected via physical USB Data Cable,
ADB discovery, port forwarding (adb forward tcp:X tcp:Y), camera stream probing,
and hardware PnP detection for devices connected without USB Debugging.
"""

import os
import shutil
import subprocess
import logging
import cv2
import time
from typing import List, Dict, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# Known standard ADB install locations on Windows
COMMON_ADB_PATHS = [
    r"C:\Program Files\SmartFusionLabs\Remote Gamepad\adb\adb.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
    os.path.expandvars(r"%USERPROFILE%\AppData\Local\Android\Sdk\platform-tools\adb.exe"),
    r"C:\platform-tools\adb.exe",
    r"C:\Program Files\Android\platform-tools\adb.exe",
]

class USBPhoneManager:
    """Manages physical USB Android camera discovery, ADB port forwarding, and stream validation."""

    def __init__(self):
        self._adb_path = self._locate_adb()
        self._active_forwards: Dict[str, Dict[str, Any]] = {} # camera_id or serial -> forward metadata

    def _locate_adb(self) -> Optional[str]:
        """Locate adb.exe from known paths or system PATH."""
        for path in COMMON_ADB_PATHS:
            if os.path.isfile(path):
                logger.info(f"[USBPhoneManager] Found ADB at common path: {path}")
                return path
        
        path_in_env = shutil.which("adb")
        if path_in_env:
            logger.info(f"[USBPhoneManager] Found ADB in system PATH: {path_in_env}")
            return path_in_env
            
        logger.warning("[USBPhoneManager] adb.exe not found in standard paths or PATH.")
        return None

    def get_adb_path(self) -> Optional[str]:
        """Return the current ADB binary path, re-checking if needed."""
        if not self._adb_path or not os.path.isfile(self._adb_path):
            self._adb_path = self._locate_adb()
        return self._adb_path

    def _run_cmd(self, args: List[str], timeout: int = 6) -> Tuple[int, str, str]:
        """Run a subprocess command safely with timeout."""
        try:
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0

            res = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                startupinfo=startupinfo,
                check=False
            )
            return res.returncode, res.stdout.strip(), res.stderr.strip()
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except Exception as e:
            return -1, "", str(e)

    def check_windows_pnp_devices(self) -> List[Dict[str, str]]:
        """
        Fallback check for physical USB-attached Android devices in Windows PnP.
        Useful when device is plugged in via USB data cable but USB Debugging is turned OFF.
        """
        if os.name != "nt":
            return []

        ps_cmd = (
            "Get-PnpDevice -PresentOnly | "
            "Where-Object { $_.Class -in @('WPD','AndroidUsbDeviceClass','USB') -and "
            "($_.FriendlyName -match 'Android|Galaxy|Pixel|Xiaomi|Redmi|Realme|OnePlus|Oppo|Vivo|Motorola|Phone|Composite') } | "
            "Select-Object FriendlyName, InstanceId, Status | ConvertTo-Json"
        )
        
        ret, stdout, stderr = self._run_cmd(["powershell", "-NoProfile", "-Command", ps_cmd], timeout=8)
        detected = []
        if ret == 0 and stdout:
            import json
            try:
                data = json.loads(stdout)
                if isinstance(data, dict):
                    data = [data]
                for item in data:
                    name = item.get("FriendlyName") or "Android/Portable USB Device"
                    inst = item.get("InstanceId") or ""
                    # Filter out standard host controllers/hubs
                    if any(ignore in name.lower() for ignore in ["root hub", "host controller", "intel", "amd"]):
                        continue
                    detected.append({
                        "name": name,
                        "instance_id": inst,
                        "status": item.get("Status", "OK")
                    })
            except Exception as e:
                logger.debug(f"[USBPhoneManager] PnP parse error: {e}")
        return detected

    def detect_devices(self) -> Dict[str, Any]:
        """
        Detect connected Android devices via ADB and check Windows PnP as fallback.
        Returns:
            {
                "adb_available": bool,
                "adb_path": str,
                "devices": [
                    {
                        "serial": str,
                        "state": "device" | "unauthorized" | "offline",
                        "model": str,
                        "product": str,
                        "usb_info": str,
                        "authorized": bool
                    }
                ],
                "pnp_hardware_detected": [ ... ],
                "instructions": [ ... ]
            }
        """
        adb = self.get_adb_path()
        result: Dict[str, Any] = {
            "adb_available": bool(adb),
            "adb_path": adb,
            "devices": [],
            "pnp_hardware_detected": [],
            "instructions": []
        }

        if not adb:
            # Check PnP to see if physical cable is connected
            pnp = self.check_windows_pnp_devices()
            result["pnp_hardware_detected"] = pnp
            result["instructions"] = [
                "ADB executable was not detected on this system.",
                "Install Android Platform Tools (ADB) or use an app like DroidCam/Remote Gamepad which provides ADB.",
                "Ensure Developer Options and USB Debugging are enabled on your Android phone."
            ]
            return result

        # Ensure ADB server is running
        self._run_cmd([adb, "start-server"], timeout=5)

        # Run `adb devices -l`
        ret, stdout, stderr = self._run_cmd([adb, "devices", "-l"], timeout=8)
        devices = []
        if ret == 0:
            lines = stdout.splitlines()
            for line in lines[1:]: # Skip "List of devices attached"
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    serial = parts[0]
                    state = parts[1]
                    model = "Unknown Android"
                    product = ""
                    usb = ""
                    for part in parts[2:]:
                        if part.startswith("model:"):
                            model = part.split("model:", 1)[1].replace("_", " ")
                        elif part.startswith("product:"):
                            product = part.split("product:", 1)[1]
                        elif part.startswith("usb:"):
                            usb = part.split("usb:", 1)[1]

                    devices.append({
                        "serial": serial,
                        "state": state,
                        "model": model,
                        "product": product,
                        "usb_info": usb,
                        "authorized": (state == "device")
                    })

        result["devices"] = devices

        # If no ADB devices detected, query Windows PnP to assist troubleshooting
        if not devices:
            pnp = self.check_windows_pnp_devices()
            result["pnp_hardware_detected"] = pnp
            if pnp:
                result["instructions"] = [
                    f"Physical USB device detected: {pnp[0]['name']}.",
                    "However, USB Debugging is not active or ADB connection was not accepted.",
                    "1. Open Phone Settings -> Developer Options.",
                    "2. Enable 'USB Debugging'.",
                    "3. Unplug and replug the USB Data Cable.",
                    "4. When the phone shows 'Allow USB debugging?', tap 'Always allow from this computer' and tap OK."
                ]
            else:
                result["instructions"] = [
                    "No Android device detected over USB.",
                    "1. Connect phone using a high-quality USB Data Cable (not charge-only).",
                    "2. Set USB mode on phone to 'File Transfer / MTP'.",
                    "3. Enable USB Debugging in Developer Options."
                ]
        elif any(d["state"] == "unauthorized" for d in devices):
            result["instructions"] = [
                "Device detected but unauthorized.",
                "Please unlock your phone screen and tap 'Always allow from this computer' on the USB Debugging prompt."
            ]
        elif any(d["state"] == "device" for d in devices):
            result["instructions"] = [
                "Device connected and authorized via USB Data Cable.",
                "Launch your phone camera streaming app (e.g. IP Webcam on port 8080 or DroidCam on port 4747), then click 'Connect Camera'."
            ]

        return result

    def is_local_port_available(self, port: int) -> bool:
        """Test if a local TCP port is free to bind on 127.0.0.1 without conflicts."""
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", port))
            s.close()
            return True
        except OSError:
            return False

    def find_available_local_port(self, start_port: int = 8090, max_attempts: int = 40) -> int:
        """Find the first available local TCP port starting from start_port (default 8090)."""
        for p in range(start_port, start_port + max_attempts):
            if self.is_local_port_available(p):
                return p
        return start_port

    def forward_port(self, local_port: int, phone_port: int, serial: Optional[str] = None) -> Tuple[bool, str]:
        """
        Execute `adb forward tcp:local_port tcp:phone_port` over USB.
        """
        adb = self.get_adb_path()
        if not adb:
            return False, "ADB executable not found"

        cmd = [adb]
        if serial:
            cmd.extend(["-s", serial])
        cmd.extend(["forward", f"tcp:{local_port}", f"tcp:{phone_port}"])

        ret, stdout, stderr = self._run_cmd(cmd, timeout=8)
        if ret == 0:
            key = f"{serial or 'default'}:{local_port}"
            self._active_forwards[key] = {
                "serial": serial,
                "local_port": local_port,
                "phone_port": phone_port,
                "forwarded_at": time.time()
            }
            logger.info(f"[USBPhoneManager] Successfully forwarded tcp:{local_port} -> tcp:{phone_port} (device: {serial or 'any'})")
            return True, f"Port {local_port} -> {phone_port} forwarded successfully"
        else:
            err_msg = stderr or stdout or "Unknown ADB error"
            logger.error(f"[USBPhoneManager] Failed to forward port {local_port}: {err_msg}")
            return False, err_msg

    def forward_port_with_fallback(
        self,
        preferred_local_port: int = 8090,
        phone_port: int = 8080,
        serial: Optional[str] = None,
        auto_find: bool = True
    ) -> Tuple[bool, int, str]:
        """
        Attempt to forward tcp:local_port tcp:phone_port.
        If preferred_local_port fails due to binding errors (e.g. Windows error 10013 / occupied),
        and auto_find is True, automatically finds and binds the next available port (8090, 8091, 8092, ...).
        Returns: (success, actual_local_port, message)
        """
        candidate_ports = [preferred_local_port]
        if auto_find:
            fallback_ports = [p for p in range(8090, 8120) if p != preferred_local_port]
            candidate_ports.extend(fallback_ports)

        last_err = ""
        for port in candidate_ports:
            # Check if host socket is available
            if not self.is_local_port_available(port):
                logger.debug(f"[USBPhoneManager] Port {port} is occupied on PC, testing next port...")
                continue

            ok, msg = self.forward_port(local_port=port, phone_port=phone_port, serial=serial)
            if ok:
                return True, port, f"Port forwarded successfully: 127.0.0.1:{port} -> Phone :{phone_port}"
            else:
                last_err = msg
                # If error is hardware or device offline/unauthorized, don't keep iterating ports
                low = msg.lower()
                if "no devices" in low or "offline" in low or "unauthorized" in low or "device not found" in low:
                    return False, port, msg

        return False, preferred_local_port, f"Failed to forward port: {last_err}"

    def remove_forward(self, local_port: int, serial: Optional[str] = None) -> bool:
        """Remove an active port forwarding rule."""
        adb = self.get_adb_path()
        if not adb:
            return False
        cmd = [adb]
        if serial:
            cmd.extend(["-s", serial])
        cmd.extend(["forward", "--remove", f"tcp:{local_port}"])
        ret, _, _ = self._run_cmd(cmd, timeout=5)
        key = f"{serial or 'default'}:{local_port}"
        self._active_forwards.pop(key, None)
        return ret == 0

    def probe_stream(self, stream_url: str, timeout_seconds: float = 3.5) -> Tuple[bool, Optional[Tuple[int, int]], str]:
        """
        Probe a stream URL (e.g. http://127.0.0.1:8080/video) using OpenCV to verify
        that video frames can be retrieved cleanly.
        Returns: (success, (width, height), message)
        """
        logger.info(f"[USBPhoneManager] Probing camera stream at {stream_url}...")
        cap = cv2.VideoCapture(stream_url)
        if not cap.isOpened():
            return False, None, f"Could not connect to camera stream at {stream_url}. Ensure the phone app server is started."

        start_t = time.time()
        read_success = False
        frame_shape = None

        while time.time() - start_t < timeout_seconds:
            ret, frame = cap.read()
            if ret and frame is not None and frame.size > 0:
                h, w = frame.shape[:2]
                frame_shape = (w, h)
                read_success = True
                break
            time.sleep(0.1)

        cap.release()

        if read_success and frame_shape:
            return True, frame_shape, f"Camera feed validated: {frame_shape[0]}x{frame_shape[1]} resolution"
        else:
            return False, None, "Connected to port, but no valid video frames received. Check stream endpoint path."

# Singleton instance
usb_phone_manager = USBPhoneManager()
