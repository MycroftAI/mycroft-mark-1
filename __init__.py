# Copyright 2017 Mycroft AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import astral
import time
import arrow
from difflib import SequenceMatcher
from mycroft.skills.core import MycroftSkill
from mycroft.util import connected
from mycroft.util.log import LOG
from mycroft.util.parse import normalize
from mycroft.audio import wait_while_speaking
from mycroft import intent_file_handler
from ast import literal_eval as parse_tuple
from pytz import timezone
from datetime import datetime


def hex_to_rgb(_hex):
    """ turns hex into rgb

        Args:
            hex (str): hex i.e #ff12ff
        Returns:
            (rgb): tuple i.e (123, 200, 155)
    """
    try:
        if '#' in _hex:
            _hex = _hex.replace('#', "").strip()
        if len(_hex) != 6:
            raise
        (r, g, b) = \
            int(_hex[0:2], 16), int(_hex[2:4], 16), int(_hex[4:6], 16)
        return (r, g, b)
    except Exception as e:
        LOG.info(e)
        LOG.info('Hex format is incorrect')
        return None


def fuzzy_match_color(color_a, color_dict):
    """ fuzzy match for colors

        Args:
            color_a (str): color as string
            color_dict (dict): dict with colors
        Returns:
            color: color from color_dict
    """
    highest_ratio = float("-inf")
    _color = None
    for color, value in color_dict.iteritems():
        s = SequenceMatcher(None, color_a, color)
        if s.ratio() > highest_ratio:
            highest_ratio = s.ratio()
            _color = color
    if highest_ratio > 0.8:
        return _color
    else:
        return None


class Mark1(MycroftSkill):
    def __init__(self):
        super(Mark1, self).__init__("Mark1")
        self.should_converse = False
        self._settings_loaded = False
        self.converse_context = None

    def initialize(self):
        # Initialize...
        if self.settings.get('auto_brightness') is None:
            self.settings['auto_brightness'] = False
        if self.settings.get('eye color') is None:
            self.settings['eye color'] = "default"

        self.color_dict = self.translate_namedvalues('colors')
        LOG.info(self.color_dict)

        # Handle changing the eye color once Mark 1 is ready to go
        # (Part of the statup sequence)
        try:
            self.add_event('mycroft.internet.connected',
                           self.handle_internet_connected)
        except:
            pass

        # TODO: Add MycroftSkill.register_entity_list() and use the
        #  self.color_dict.keys() instead of duplicating data
        self.register_entity_file('color.entity')

        if connected():
            # Connected at startup: setting eye color
            self.enclosure.mouth_reset()
            self.set_eye_color(self.settings['eye color'], initing=True)

    def handle_internet_connected(self, message):
        # System came online later after booting
        self.enclosure.mouth_reset()
        self.set_eye_color(self.settings['eye color'], speak=False)

    def set_eye_color(self, color=None, rgb=None, speak=True, initing=False):
        """ function to set eye color

            Args:
                custom (bool): user inputed rgb
                speak (bool): to have success speak on change
        """
        if color is not None:
            color_rgb = hex_to_rgb(self.color_dict.get(color, None))
            if color_rgb is not None:
                (r, g, b) = color_rgb
                self.enclosure.eyes_color(r, g, b)
        elif rgb is not None:
                (r, g, b) = rgb
                self.enclosure.eyes_color(r, g, b)
        try:
            self._current_color = (r, g, b)
            if speak and not initing:
                self.speak_dialog('set.color.success')
        except:
            self.log.debug('Bad color code: '+str(color))
            if speak and not initing:
                self.speak_dialog('error.set.color')
            if initing:
                self.enclosure.eyes_color(34, 167, 240)  # mycroft blue

    @intent_file_handler('custom.eye.color.intent')
    def handle_custom_eye_color(self, message):
        # Conversational interaction to set a custom eye color

        def is_byte(utt):
            try:
                return 0 <= int(utt) <= 255
            except:
                return False

        self.speak_dialog('set.custom.color')
        wait_while_speaking()
        r = self.get_response('get.r.value', validator=is_byte,
                              on_fail="error.rgbvalue", num_retries=2)
        if not r:
            return  # cancelled

        g = self.get_response('get.g.value', validator=is_byte,
                              on_fail="error.rgbvalue", num_retries=2)
        if not g:
            return  # cancelled

        b = self.get_response('get.b.value', validator=is_byte,
                              on_fail="error.rgbvalue", num_retries=2)
        if not b:
            return  # cancelled

        custom_rgb = [r, g, b]
        self.set_eye_color(rgb=custom_rgb)
        self.settings['eye color'] = custom_rgb

    def fuzzy_set_eye_color(self, color):
        """ set's the eye color with fuzzy matching """
        # TODO:18.02: normalize() should automatically get current intent lang
        match = fuzzy_match_color(normalize(color), self.color_dict)
        self.log.debug("Search color: "+color+"    Match color: "+match)
        if match is not None:
            self.set_eye_color(color=match)
            self.settings['eye color'] = match
        else:
            self.speak_dialog('color.not.exist')

    @intent_file_handler('eye.color.intent')
    def handle_eye_color(self, message):
        """ Callback to set eye color from list

            Args:
                message (dict): messagebus message from intent parser
        """
        color_string = (message.data.get('color', None) or
                        self.get_response('color.need'))
        if color_string:
            self.fuzzy_set_eye_color(color_string)

    def is_rgb_format_correct(self, rgb):
        """ checks for correct rgb format and value

            Args:
                rgb (tuple): tuple with integer values

            return:
                (bool): for correct rgb value
        """
        (r, g, b) = rgb
        if 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255:
            return True
        else:
            return False

    def parse_to_rgb(self, color):
        """ parse the color and returns rgb. color can be
            Hex, RGB, or color from color_dict

            Args:
                color (str): RGB, Hex, or color from color_dict

            returns:
                (r, g, b) (tuple): rgb from 0 - 255
        """
        if not color:
            return None

        # color exist in dict
        color = color.lower()
        if color in self.color_dict:
            return hex_to_rgb(self.color_dict[color])
        # color is rgb
        try:
            (r, g, b) = parse_tuple(color)
            return (r, g, b)
        except:
            LOG.info('RGB format is incorrect')

        # color is hex
        try:
            if '#' in color:
                color = color.replace('#', "")
            if len(color) != 6:
                raise
            (r, g, b) = \
                int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
            return (r, g, b)
        except:
            LOG.info('Hex format is incorrect')

        # color is None of the above
        return None

    @intent_file_handler('get.color.web.intent')
    def handle_web_settings(self):
        """ Callback to set eye color to web settings

            Args:
                message (dict): messagebus message from intent parser
        """
        self.settings.update_remote()
        _color = self.settings.get('eye color', "")
        if not _color:
            self.speak_dialog('no.web.setting')
            return

        # Try to parse the value entered there
        rgb = self.parse_to_rgb(_color)
        if rgb is not None:
            if self.is_rgb_format_correct(rgb):
                self.set_eye_color(rgb=rgb)
            else:
                self.speak_dialog('error.format')
        else:
            self.speak_dialog('error.format')

    def convert_brightness(self, percent):
        """ converts the brigtness value from percentage to
             a value arduino can read

            Args:
                percent (int): interger value from 0 to 100

            return:
                (int): value form 0 to 30
        """
        return int(float(percent)/float(100)*30)

    def parse_brightness(self, brightness):
        """ parse text for brightness level

            Args:
                brightness (str): string containing brightness level

            return:
                (int): brightness level
        """
        if '%' in brightness:
            brightness = brightness.replace("%", "").strip()
        if 'percent' in brightness:
            brightness = brightness.replace("percent", "").strip()
        return int(brightness)

    def set_eye_brightness(self, brightness, speak=True):
        """ set eye brightness """
        self.enclosure.eyes_brightness(brightness)
        if speak is True:
            brightness = int(float(brightness)*float(100)/float(30))
            self.speak_dialog(
                'brightness.set', data={'val': str(brightness)+'%'})

    def brightness_validator(self, brightness):
        """ validate brightness is int or between 0 to 100
            Args:
                brightness (int): integer of brightness
            Returns:
                bool
        """
        try:
            return 0 <= int(brightness) <= 100
        except:
            return False

    def set_brightness_converse(self):
        """ setoff converse method for brightness """
        response = self.get_response(
                    'brightness.not.found',
                    validator=self.brightness_validator,
                    num_retries=1)
        if response is not None:
            bright_val = self.convert_brightness(response)
            self.set_eye_brightness(bright_val)
        else:
            self.speak_dialog('brightness.not.found.final')

    @intent_file_handler('brightness.intent')
    def handle_brightness(self, message):
        """ Intent Callback to set custom eye colors in rgb

            Args:
                message (dict): messagebus message from intent parser
        """
        LOG.info(message.data)
        self.auto_brightness = False
        if 'brightness' in message.data:
            try:
                brightness = self.parse_brightness(
                                    message.data.get('brightness'))
                if (0 <= brightness <= 100) is False:
                    raise
                else:
                    bright_val = self.convert_brightness(brightness)
                    self.set_eye_brightness(bright_val)
            except Exception as e:
                LOG.error(e)
                self.set_brightness_converse()
        else:
            self.set_brightness_converse()

    def _get_auto_time(self):
        """ get dawn, sunrise, noon, sunset, and dusk time

            returns:
                times (dict): dict with associated (datetime, brightnes)
        """
        tz = self.location['timezone']['code']
        lat = self.location['coordinate']['latitude']
        lon = self.location['coordinate']['longitude']
        ast_loc = astral.Location()
        ast_loc.timezone = tz
        ast_loc.lattitude = lat
        ast_loc.longitude = lon

        user_set_tz = \
            timezone(tz).localize(datetime.now()).strftime('%Z')
        device_tz = time.tzname

        if user_set_tz in device_tz:
            sunrise = ast_loc.sun()['sunrise']
            noon = ast_loc.sun()['noon']
            sunset = ast_loc.sun()['sunset']
        else:
            secs = int(self.location['timezone']['offset']) / -1000
            sunrise = arrow.get(
                ast_loc.sun()['sunrise']).shift(
                    seconds=secs).replace(tzinfo='UTC').datetime
            noon = arrow.get(
                ast_loc.sun()['noon']).shift(
                    seconds=secs).replace(tzinfo='UTC').datetime
            sunset = arrow.get(
                ast_loc.sun()['sunset']).shift(
                    seconds=secs).replace(tzinfo='UTC').datetime

        return {
            'Sunrise': (sunrise, 20),
            'Noon': (noon, 30),
            'Sunset': (sunset, 5)
        }

    def schedule_brightness(self, time_of_day, pair):
        """ schedule auto brightness with the event scheduler

            Args:
                time_of_day (str): Sunrise, Noon, Sunset
                pair (tuple): (datetime, brightness)
        """
        d_time = pair[0]
        brightness = pair[1]
        now = arrow.now()
        arw_d_time = arrow.get(d_time)
        data = (time_of_day, brightness)
        if now.timestamp > arw_d_time.timestamp:
            d_time = arrow.get(d_time).shift(hours=+24)
            self.schedule_event(self._handle_eye_brightness_event, d_time,
                                data=data, name=time_of_day)
        else:
            self.schedule_event(self._handle_eye_brightness_event, d_time,
                                data=data, name=time_of_day)

    # TODO: this is currently set by voice.
    # allow setting from faceplate and web ui
    @intent_file_handler('brightness.auto.intent')
    def handle_auto_brightness(self, message):
        """ brightness varies depending on time of day

            Args:
                message (dict): messagebus message from intent parser
        """
        self.auto_brightness = True
        auto_time = self._get_auto_time()
        nearest_time_to_now = (float('inf'), None, None)
        for time_of_day, pair in auto_time.iteritems():
            self.schedule_brightness(time_of_day, pair)
            now = arrow.now().timestamp
            t = arrow.get(pair[0]).timestamp
            if abs(now - t) < nearest_time_to_now[0]:
                nearest_time_to_now = (abs(now - t), pair[1], time_of_day)
        LOG.info(nearest_time_to_now)
        self.set_eye_brightness(nearest_time_to_now[1], speak=False)
        tod = nearest_time_to_now[2]
        if tod == 'Sunrise':
            self.speak_dialog('auto.sunrise')
        elif tod == 'Sunset':
            self.speak_dialog('auto.sunset')
        elif tod == 'Noon':
            self.speak_dialog('auto.noon')

    def _handle_eye_brightness_event(self, message):
        """ wrapper for setting eye brightness from
            eventscheduler

            Args:
                message (dict): messagebus message
        """
        if self.auto_brightness is True:
            time_of_day = message.data[0]
            brightness = message.data[1]
            self.cancel_scheduled_event(time_of_day)
            self.set_eye_brightness(brightness, speak=False)
            pair = self._get_auto_time()[time_of_day]
            self.schedule_brightness(time_of_day, pair)


def create_skill():
    return Mark1()
