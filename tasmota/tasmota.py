import requests
# Basic control of a Tasmota device


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

    # ### Control ### #

    def blink_count(self, count):
        return self._go(f'BlinkCount {count}')

    def power(self, state: bool):
        str_state = 'on' if state else 'off'
        return self._go(f'Power {str_state}')

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
        ip_address: str,
        user: str = None,
        password: str = None,
    ):
        self.ip_address = ip_address
        self.user = user
        self.password = password

    def send(self, command: str | list[str]) -> dict:
        if isinstance(command, list):
            # Multiple commands are stacked with "Backlog"
            return self.backlog(command)
        params = {'cmnd': command}
        if self.user is not None:
            params['user'] = self.user
        if self.password is not None:
            params['password'] = self.password

        url = f'http://{self.ip_address}/cm'

        response = requests.get(url, params=params)
        response.raise_for_status()

        return response.json()

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
