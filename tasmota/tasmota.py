# Basic control of a Tasmota device

import logging

import requests


log = logging.getLogger(__name__)


class Command:
    def __init__(self, parent: 'Tasmota', stack=False):
        self._parent = parent

        self._commands = None
        if stack:
            self._commands = []

    def go(self, zero=False) -> dict:
        # No commands? do nothing
        if not self._commands:
            return {}

        # Single command, just use send
        if len(self._commands) == 1:
            return self._parent.send(self._commands[0])

        # Multiple commands use the backlog
        return self._parent.backlog(self._commands, zero=zero)

    def _go(self, command: str):
        if self._commands is None:
            return self._parent.send(command)

        self._commands.append(command)
        return self

    # ### Behave as a context manager ### #
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.go()

    # ### Control ### #

    def blink_count(self, count):
        return self._go(f'BlinkCount {count}')

    def power(self, state: bool):
        str_state = 'on' if state else 'off'
        return self._go(f'Power {str_state}')

    def power1(self, state: bool):
        str_state = 'on' if state else 'off'
        return self._go(f'Power1 {str_state}')

    def power2(self, state: bool):
        str_state = 'on' if state else 'off'
        return self._go(f'Power2 {str_state}')

    # ### Management ### #

    def delay(self, time: int):
        '''
        Time is in 1/10 seconds, from 2 - 3600
        '''
        assert 2 <= time <= 3600, f'Bad delay time of {time}'
        return self._go(f'Delay {time}')

    def deep_sleep_time(self, time):
        '''
        How long to enter deep sleep mode.
        0 = disable (default)
        11 - 86400 = deep sleep mode time in seconds
        '''
        return self._go(f'DeepSleepTime {time}')

    # ### WiFi ### #


class Tasmota:
    def __init__(
        self,
        ip_address: str = None,
        user: str = None,
        password: str = None,
        topic: str = None,
        mqtt_client=None
    ):
        self.ip_address = ip_address
        self.user = user
        self.password = password

        self._change_listeners = {}

        self.topic = topic
        self._mqtt_client = None
        self._set_mqtt_client(mqtt_client)

        if not self.mqtt_client and not ip_address:
            raise ValueError('Must set mqtt_client or ip_address')

        if self.mqtt_client and not self.topic:
            raise ValueError('Must define a topic when using the mqtt_client')

        # Indicate if light is on MQTT server. None=don't know.
        self._online = None

    @property
    def online(self):
        return self._online

    @property
    def mqtt_client(self):
        return self._mqtt_client

    @mqtt_client.setter
    def mqtt_client(self, client):
        self._set_mqtt_client(client)

    def _set_mqtt_client(self, client):
        if self._mqtt_client != client and self._mqtt_client:
            # de-register from old client
            try:
                del self._mqtt_client._userdata[self]
            except KeyError:
                pass

        self._mqtt_client = client
        if not client:
            # If it was set to None, perform no more actions
            return

        # Use the client userdata to store a ref to this object
        if not client._userdata:
            client.user_data_set({})
            self._setup_mqtt_client(client)
        client._userdata[self.topic] = self

    @classmethod
    def _mqtt_on_connect(cls, client, userdata, flags, rc):
        # subscribe to all channels
        log.info('MQTT Connected. Listening for any changes')
        client.subscribe('#')

    @classmethod
    def _mqtt_on_message(cls, client, userdata, msg):
        # All status messages start with "stat/"
        # topic="stat/tasmota_197CD7/POWER1" payload="ON"

        log.debug(f'MQTT Received {msg.topic} :: {msg.payload}')

        if not msg or not msg.topic or not msg.topic.startswith('stat/'):
            return

        try:
            prefix, topic, command = msg.topic.split('/')
        except ValueError:
            # If we don't have the expected count of values
            return

        if not userdata:
            return

        instance = userdata.get(topic)
        if not instance:
            return

        # Invoke the callback functions
        instance._on_change(client, command, msg.payload.decode())

    def _on_change(self, client, command, payload):
        '''
        Handle the change event message.
        '''
        log.debug(f'_on_change event for {self.topic} :: {command}')

        if command == 'LWT':
            if payload.lower() == 'online':
                self._online = True
            elif payload.lower() == 'offline':
                self._online = False

        # Call the change listener if set
        change_listener = self._change_listeners.get(command)
        if change_listener:
            change_listener(client, command, payload)
        else:
            log.info(f'No change handler for command {command}')

        # The all changes listener has an index of None
        all_changes_listener = self._change_listeners.get(None)
        if all_changes_listener:
            all_changes_listener(client, command, payload)

    @classmethod
    def _setup_mqtt_client(cls, client):
        client.on_connect = cls._mqtt_on_connect
        client.on_message = cls._mqtt_on_message

    def on_change(self, subscribed_change=None):
        '''
        A decorator to define a function to handle message changes

        to use:
        @my_button.on_change('POWER1')
        def my_handler(client, property, value):
            pass


        To subscribe to all changes, use
        @my_button.on_change()

        Only the most recent handler will be registered. Later
        handlers supercede earlier ones. That is, there can only
        be one subscriber per type of change.
        '''
        def wrapped_fn(fn):
            log.debug(f'Subscribing to {subscribed_change}')
            self._change_listeners[subscribed_change] = fn
            return fn
        return wrapped_fn

    def _send_http(self, command: str) -> dict:
        params = {'cmnd': command}
        if self.user is not None:
            params['user'] = self.user
        if self.password is not None:
            params['password'] = self.password

        url = f'http://{self.ip_address}/cm'

        log.info(f'HTTP Sending {url} :: {params}')

        response = requests.get(url, params=params)
        response.raise_for_status()

        return response.json()

    def _send_mqtt(self, command: str) -> dict:
        cmd, payload = command.split(' ', maxsplit=1)
        cmd = cmd.upper()
        topic = f'cmnd/{self.topic}/{cmd}'
        log.info(f'MQTT Sending {topic} :: {cmd}')
        self.mqtt_client.publish(topic, payload=payload)
        return {}

    def send(self, command: str | list[str]) -> dict:
        if isinstance(command, list):
            # Multiple commands are stacked with "Backlog"
            return self.backlog(command)

        log.debug(f'Sending {command}')
        if self.mqtt_client:
            return self._send_mqtt(command)
        elif self.ip_address:
            return self._send_http(command)
        else:
            log.warning('No HTTP nor MQTT to send to!')

    def backlog(self, commands: list[str], zero=False) -> dict:
        '''
        List of commands to be executed.
        Set zero to true to execute "without any delay"
          Faster execution, and seems to ignore any "delay" commands
        '''
        zero_flag = '0' if zero else ''

        command = f'Backlog{zero_flag} {"; ".join(commands)}'
        return self.send(command)

    @property
    def command_runner(self):
        return Command

    @property
    def cmd(self) -> Command:
        '''Returns an instantiated command runner'''
        return self.command_runner(parent=self)

    @property
    def cmds(self) -> Command:
        '''Returns an instantiated command runner'''
        return self.command_runner(parent=self, stack=True)

    # ### Management Commands ### #
    # The following commands are for setup and status queries

    def status(self, option: int = None) -> dict:
        '''
        option:
        = show abbreviated status information
        0 = show all status information (1 - 11)
        1 = show device parameters information
        2 = show firmware information
        3 = show logging and telemetry information
        4 = show memory information
        5 = show network information
        6 = show MQTT information
        7 = show time information
        8 = show connected sensor information
                 (retained for backwards compatibility)
        9 = show power thresholds
                 (only on modules with power monitoring)
        10 = show connected sensor information (replaces 'Status 8')
        11 = show information equal to TelePeriod state message
        12 = in case of crash to dump the call stack saved in RT memory
        '''
        opt_str = '' if None else str(option)
        return self.send(f'Status {opt_str}')

    def state(self) -> dict:
        return self.send('State')

    def modules(self) -> dict:
        '''
        Return the available modules.
        '''
        return self.send('Modules')
