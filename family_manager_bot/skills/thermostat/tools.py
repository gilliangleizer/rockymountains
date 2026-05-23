from .seam import get_status, set_temperature, set_mode

SYSTEM_PROMPT_SECTION = """## Thermostat
Controls the home Ecobee thermostat via Seam.
- "what's the temperature", "how warm is it at home" → get_thermostat_status
- "set heat to X", "set it to X degrees", "make it warmer/cooler" → set_thermostat_temperature with heating_setpoint or cooling_setpoint
- "turn off the heat/AC", "set to heat only", "set to cool only", "set to auto" → set_thermostat_mode (off/heat/cool/heat_cool)
- For "set it to X", infer heat vs cool from context or current season; if unclear, ask."""

TOOLS = [
    {
        "name": "get_thermostat_status",
        "description": "Get current temperature, humidity, mode, and setpoints from the home thermostat",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "set_thermostat_temperature",
        "description": "Set the heating and/or cooling setpoints on the thermostat",
        "input_schema": {
            "type": "object",
            "properties": {
                "heating_setpoint": {"type": "number", "description": "Heating setpoint in °F"},
                "cooling_setpoint": {"type": "number", "description": "Cooling setpoint in °F"},
            },
        },
    },
    {
        "name": "set_thermostat_mode",
        "description": "Set the HVAC mode",
        "input_schema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["heat", "cool", "heat_cool", "off"],
                    "description": "heat, cool, heat_cool (auto), or off",
                },
            },
            "required": ["mode"],
        },
    },
]

HANDLERS = {
    "get_thermostat_status": lambda inp: get_status(),
    "set_thermostat_temperature": lambda inp: set_temperature(
        heating_setpoint=inp.get("heating_setpoint"),
        cooling_setpoint=inp.get("cooling_setpoint"),
    ),
    "set_thermostat_mode": lambda inp: set_mode(inp["mode"]),
}
