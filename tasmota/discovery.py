import json
import logging


log = logging.getLogger(__name__)


class Device:
    def __init__(self, sn, client):
        self.sn = sn
        self._mqtt_client = client
        self._config = {}
        self._sensors = {}

        self.on_change = None

    @property
    def config(self):
        return self._config

    @config.setter
    def config(self, value):
        self._config = value
        if self.on_change is not None:
            self.on_change(self)

    @property
    def sensors(self):
        return self._sensors

    @sensors.setter
    def sensors(self, value):
        self._sensors = value
        if self.on_change is not None:
            self.on_change(self)

    @property
    def ip_address(self):
        return self._config.get('ip')

    @property
    def topic(self):
        return self._config.get('t')


class Discover:
    def __init__(self, mqtt_client):
        self.client = mqtt_client
        self.devices = {}

        self._other_on_connect = mqtt_client.on_connect
        self._other_on_message = mqtt_client.on_message
        self._new_device_callbacks = []

        mqtt_client.on_connect = self._on_connect
        mqtt_client.on_message = self._on_message

    @property
    def on_new_device(self):
        return self._new_device_callbacks

    @on_new_device.setter
    def on_new_device(self, value):
        if value not in self._new_device_callbacks:
            self._new_device_callbacks.append(value)

    def _discovery_msg(self, msg):
        try:
            _, _, sn, msg_type = msg.topic
        except ValueError:
            log.debug(f'_discovery_msg unkown format for {msg.topic}')
            return

        device = self.devices.get(sn)
        if not device:
            device = Device(sn, self.client)
            self.devices[sn] = device
            log.info(f'discovered new device "{sn}"')
            for fn in self._new_device_callbacks:
                fn(device)

        if msg_type.lower() == 'config':
            try:
                config = json.loads(msg.payload)
            except Exception:
                log.debug(f'_discovery_msg bad format for {msg.payload}')
                return

            device.config = config
            log.debug(f'updated config for {sn}')

        elif msg_type.lower() == 'sensors':
            try:
                sensors = json.loads(msg.payload)
            except Exception:
                # bad payload
                return

            log.debug(f'updated sensors for {sn}')
            device.sensors = sensors.get('sn', {})

    def _on_connect(self, *args, **kwargs):
        if self._other_on_connect:
            self._other_on_connect(*args, **kwargs)

    def _on_message(self, client, userdata, msg):
        if msg.topic.startswith('tasmota/discovery/'):
            log.debug(f'received discovery message')
            self._discovery_msg(msg)

        if self._other_on_message:
            self._other_on_message(client, userdata, msg)
