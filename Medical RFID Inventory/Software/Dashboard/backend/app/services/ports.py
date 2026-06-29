from serial.tools import list_ports


def list_available_ports() -> list[dict[str, str]]:
    ports = []
    for port in list_ports.comports():
        ports.append(
            {
                "device": port.device,
                "description": port.description or "",
                "hwid": port.hwid or "",
            }
        )
    return ports
