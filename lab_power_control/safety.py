"""Target limits. The DP832 is the authoritative source limiting layer."""
from dataclasses import dataclass
import json
import math
from pathlib import Path


from .errors import SafetyError


def number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SafetyError('expected a numeric value')
    if not math.isfinite(value) or not low <= value <= high:
        raise SafetyError(f'value must be finite and in [{low}, {high}]')
    return float(value)


@dataclass(frozen=True)
class SafetyPolicy:
    channels: tuple = (1,)
    voltage_min: float = 0.0
    voltage_max: float = 3.3
    current_max: float = 0.2
    load_current_max: float = 0.1
    power_max: float = 0.66
    rigol_vendor: str = 'RIGOL TECHNOLOGIES'
    rigol_model: str = 'DP832'
    siglent_vendor: str = 'Siglent Technologies'
    siglent_model: str = 'SDL1030X-E'

    def __post_init__(self):
        object.__setattr__(self, 'channels', tuple(self.channels))
        if not self.channels or len(set(self.channels)) != len(self.channels):
            raise SafetyError('channels must be nonempty and unique')
        for channel in self.channels:
            self.channel(channel)
        number(self.voltage_max, 0, 5 if 3 in self.channels else 30)
        number(self.voltage_min, 0, self.voltage_max)
        number(self.current_max, 0, 3)
        number(self.load_current_max, 0, 30)
        number(self.power_max, 0, 195)
        for kind, model in [('rigol', 'DP832'), ('siglent', 'SDL1030X-E')]:
            if getattr(self, kind + '_model') != model:
                raise SafetyError('unsupported model')
            vendor = getattr(self, kind + '_vendor')
            if not isinstance(vendor, str) or not vendor.strip():
                raise SafetyError('expected vendor required')

    def channel(self, channel):
        if type(channel) is not int or channel not in (1, 2, 3):
            raise SafetyError('unknown channel')
        if channel not in self.channels:
            raise SafetyError('channel not permitted')

    def source(self, channel, voltage, current):
        self.channel(channel)
        number(voltage, self.voltage_min, self.voltage_max)
        number(current, 0, self.current_max)
        number(voltage * current, 0, self.power_max)

    def load(self, current):
        number(current, 0, self.load_current_max)
        number(self.voltage_max * current, 0, self.power_max)

    @classmethod
    def load_file(cls, path):
        return cls(**json.loads(Path(path).read_text()))
