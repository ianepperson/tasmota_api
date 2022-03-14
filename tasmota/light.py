from tasmota import Tasmota, Command

'''
Control a Tasmota light

Commands are from: https://tasmota.github.io/docs/Commands/#light
'''


class Color:
    red = '1'
    green = '2'
    blue = '3'
    orange = '4'
    light_green = '5'
    light_blue = '6'
    amber = '7'
    cyan = '8'
    purple = '9'
    yellow = '10'
    ping = '11'
    white_rgb = '12'
    step_next = '+'
    step_previous = '-'

    def __init__(self, red, green, blue, cool=None, warm=None):
        self._values = (red, green, blue, cool, warm)
        for value in self._values:
            if value is not None:
                assert 0 <= value <= 255

    def __str__(self):
        values = ['==' if val is None else f'00{hex(val)[2:]}'[-2:]
                  for val in self._values]
        return f'#{"".join(values)}'


class ColorTemp:
    cold = 153
    warm = 500
    increase = '+'
    decrease = '-'


class Effect:
    step_next = '+'
    step_previous = '-'
    single = '0'  # default: single color for entire light
    startup = '1'  # Start the wake up cycle
    cycle_up = '2'  # Cycle through the colors using the Speed option
    cycle_down = '3'
    cycle_random = '4'


class LightCommand(Command):
    def color(self, value: str, keep_dim=False):
        '''
        <value>
        r,g,b = set color by decimal value (0..255)
        #CWWW = set hex color value for CT lights
        #RRGGBB = set hex color value for RGB lights
        #RRGGBBWW = set hex color value for RGBW lights
        #RRGGBBCWWW = set hex color value for RGBCCT lights (5 PWM channels)
        Note:
        Just append an = instead of the remaining color codes, this way they
        wont get changed. For example a command like Color #00ff= would update
        the RGB part to disable red and enable geen, but would omit to update
        blue or any white channel.

        or use the Color class: Color.red
        '''
        behavior = 1
        if keep_dim:
            behavior = 2

        return self._go(f'Color{behavior} {value}')

    def color_temp(self, value):
        '''
        Value is from 153 (cold) to 500 (warm)
        or '+' and '-' to increase or decrease by 10
        '''
        return self._go(f'CT {value}')

    def dimmer(self, value):
        '''
        0..100 = set dimmer value from 0 to 100%
        + = increase by DimmerStep value (default =10)
        - = decrease by DimmerStep value (default =10)
        Use of these parameters with Fade on enables dimmer level "move down,"
        "move up," and "stop" commands (#11269)
        < = decrease to 1
        > = increase to 100
        ! = stop any dimmer fade in progress at current dimmer level
        '''
        return self._go(f'Dimmer {value}')

    def use_fade(self, value: bool = False):
        value_str = '1' if value else '0'
        return self._go(f'Fade {value_str}')

    def fade_speed(self, value):
        '''
        1..40 = set fade speed from fast 1 to very slow 40
        + = increase speed
        - = decrease speed
        The Speed value represents the time in 0.5s to fade from 0 to 100%
        (or the reverse).
        Example: Speed 4 takes 2.0s to fade from full brightness to black,
        or 0.5s to move from 75% to 100%.
        '''
        if isinstance(value, int):
            assert 1 <= value <= 40, f'Bad fade_speed value of {value}'
        else:
            assert value in ('+', '-'), f'Bad fade_speed value of {value}'
        return self._go(f'Speed {value}')

    def effect(self, value, start_color=None):
        '''
        Run a light effect from the Effect class.
        '''
        if start_color:
            return self._go(f'Scheme {value}, {start_color}')
        return self._go(f'Scheme {value}')


class TasmotaLight(Tasmota):
    @property
    def command_runner(self) -> Command:
        '''Returns the command runner'''
        return LightCommand
