import os
from seam import Seam

def _client():
    return Seam(api_key=os.environ["SEAM_API_KEY"])

def _thermostat():
    seam = _client()
    device_id = os.environ.get("SEAM_DEVICE_ID")
    if device_id:
        return seam.devices.get(device_id=device_id)
    thermostats = seam.thermostats.list()
    if not thermostats:
        raise RuntimeError("No thermostats found in Seam account")
    return thermostats[0]


def get_status():
    try:
        device = _thermostat()
        p = device.properties
        temp = p.get("temperature_fahrenheit")
        humidity = p.get("relative_humidity")
        setting = p.get("current_climate_setting", {})
        mode = setting.get("hvac_mode_setting", "unknown")
        heat_sp = setting.get("heating_set_point_fahrenheit")
        cool_sp = setting.get("cooling_set_point_fahrenheit")

        parts = [f"Current temp: {temp}°F"]
        if humidity is not None:
            parts.append(f"Humidity: {round(humidity * 100)}%")
        parts.append(f"Mode: {mode}")
        if heat_sp is not None:
            parts.append(f"Heat setpoint: {heat_sp}°F")
        if cool_sp is not None:
            parts.append(f"Cool setpoint: {cool_sp}°F")
        return " | ".join(parts)
    except Exception as e:
        return f"Thermostat error: {e}"


def set_temperature(heating_setpoint=None, cooling_setpoint=None):
    try:
        seam = _client()
        device = _thermostat()
        device_id = device.device_id
        setting = device.properties.get("current_climate_setting", {})
        mode = setting.get("hvac_mode_setting", "heat_cool")

        if heating_setpoint and cooling_setpoint:
            seam.thermostats.heat_cool(
                device_id=device_id,
                heating_set_point_fahrenheit=heating_setpoint,
                cooling_set_point_fahrenheit=cooling_setpoint,
            )
            return f"Set heat to {heating_setpoint}°F, cool to {cooling_setpoint}°F ✓"
        elif heating_setpoint:
            seam.thermostats.heat(device_id=device_id, heating_set_point_fahrenheit=heating_setpoint)
            return f"Heat set to {heating_setpoint}°F ✓"
        elif cooling_setpoint:
            seam.thermostats.cool(device_id=device_id, cooling_set_point_fahrenheit=cooling_setpoint)
            return f"Cool set to {cooling_setpoint}°F ✓"
        else:
            return "No setpoint provided."
    except Exception as e:
        return f"Thermostat error: {e}"


def set_mode(mode):
    try:
        seam = _client()
        device = _thermostat()
        seam.thermostats.set_hvac_mode(device_id=device.device_id, hvac_mode=mode)
        return f"Thermostat mode set to {mode} ✓"
    except Exception as e:
        return f"Thermostat error: {e}"
