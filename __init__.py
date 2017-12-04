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
from mycroft.skills.core import MycroftSkill
from mycroft.util.log import LOG
from mycroft.audio import wait_while_speaking
from mycroft import intent_file_handler
from ast import literal_eval as parse_tuple
from threading import Timer
from pytz import timezone
from datetime import datetime


class Mark1(MycroftSkill):
    def __init__(self):
        super(Mark1, self).__init__("Mark1")
        self.should_converse = False
        self._settings_loaded = False
        self.converse_context = None
        self.custom_rgb = []

        # colors in (r, g, b)
        self.color_dict = {
            'red': (255, 0, 0),
            'green': (0, 128, 0),
            'yellow': (255, 255, 0),
            'blue': (0, 0, 255),
            'orange': (245, 130, 48),
            'purple': (128, 0, 128),
            'cyan': (0, 255, 255),
            'magenta': (255, 0, 255),
            'lime': (0, 255, 0),
            'pink': (250, 190, 190),
            'teal': (0, 128, 128),
            'lavendar': (230, 190, 255),
            'brown': (170, 110, 40),
            'beige': (255, 250, 200),
            'maroon': (128, 0, 0),
            'mint': (170, 255, 195),
            'olive': (128, 128, 0),
            'coral': (255, 215, 180),
            'navy': (0, 0, 128),
            'grey': (128, 128, 128),
            'gray': (128, 128, 128),
            'white': (255, 255, 255),
            'black': (0, 0, 0),
            'default': (34, 167, 240)  # mycroft blue
        }

    def initialize(self):
        self.register_entity_file('color.entity')
        if self.settings.get('auto_brightness') is None:
            self.settings['auto_brightness'] = False

    def set_eye_color(self, color=None, rgb=None, speak=True):
        """ function to set eye color

            Args:
                custom (bool): user inputed rgb
                speak (bool): to have success speak on change
        """
        if color is not None:
            color_rgb = self.color_dict.get(color, None)
            if color_rgb is not None:
                (r, g, b) = color_rgb
                self.enclosure.eyes_color(r, g, b)
        elif rgb is not None:
                (r, g, b) = rgb
                self.enclosure.eyes_color(r, g, b)
        self._current_color = (r, g, b)
        if speak is True:
            self.speak_dialog('set.color.success')

    @intent_file_handler('custom.eye.color.intent')
    def handle_custom_eye_color(self, message):
        """ Intent Callback to set custom eye colors in rgb

            Args:
                message (dict): messagebus message from intent parser
        """
        # reset list
        self.custom_rgb = []
        self.set_converse('set.custom.color')
        self.speak_dialog('set.custom.color')
        wait_while_speaking()
        self.speak_dialog(
            'need.custom',
            data={'color': 'red'},
            expect_response=True)

    @intent_file_handler('eye.color.intent')
    def handle_eye_color(self, message):
        """ Callback to set eye color from list

            Args:
                message (dict): messagebus message from intent parser
        """
        if 'color' in message.data:
            color = message.data.get('color', None)
            if color is not None:
                self.set_eye_color(color=color)
            else:
                self.set_converse('need.color')
                self.speak_dialog(
                    'color.not.found.expect.response', expect_response=True)
        else:
            self.set_converse('need.color')
            self.speak_dialog(
                'color.not.found.expect.response', expect_response=True)

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
        # color exist in dict
        if color in self.color_dict:
            return self.color_dict[color]

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

    # TODO: allow skills to update the web ui settings with
    # rgb values. This will require some mycroft-core changes
    @intent_file_handler('get.color.web.intent')
    def handle_web_settings(self):
        """ Callback to set eye color to web settings

            Args:
                message (dict): messagebus message from intent parser
        """
        self.settings.load_skill_settings()
        _color = self.settings.get('eye color', "")
        rgb = self.parse_to_rgb(_color)
        if rgb is not None:
            correct = self.is_rgb_format_correct(rgb)
            LOG.info(rgb)
            if correct:
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
                self.set_converse('need.brightness')
                self.speak_dialog('brightness.not.found', expect_response=True)
        else:
            self.set_converse('need.brightness')
            self.speak_dialog('brightness.not.found', expect_response=True)

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
        """ shcedule auto bright ness with the event scheduler

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

    def need_custom_dialog(self, error=""):
        """ handles dialog to retrieve custom color

            Args:
                error (str): to set speak_dialog to error
        """
        if len(self.custom_rgb) == 0:
            self.speak_dialog(
                '{}need.custom'.format(error),
                data={'color': 'red'},
                expect_response=True)
        elif len(self.custom_rgb) == 1:
            self.speak_dialog(
                '{}need.custom'.format(error),
                data={'color': 'green'},
                expect_response=True)
        elif len(self.custom_rgb) == 2:
            self.speak_dialog(
                '{}need.custom'.format(error),
                data={'color': 'blue'},
                expect_response=True)

    def set_converse(self, context):
        """ to invoke the converse method

            Args:  
                context (str): string to set context for converse
        """
        self.should_converse = True
        self.converse_context = context

    def reset_converse(self):
        """ set converse to false and empty converse_context """
        self.should_converse = False
        self.converse_context = None

    def converse(self, utterances, lang='en-us'):
        """ overrides MycroftSkill converse method. when return value is True,
            any utterances after will be sent through the conveerse method
            to be handled.

            Args:
                utterances (str): utterances said to mycroft
                lang (str): languge of utterance (currently not used)
        """
        utt = utterances[0] 
        if self.converse_context == 'need.color':
            found_color = False
            for color in self.color_dict:
                if color in utt.lower():
                    self.set_eye_color(color=color)
                    found_color = True
            if found_color is False:
                self.speak_dialog('color.not.found')
            self.reset_converse()
            return True
        elif self.converse_context == 'set.custom.color':
            try:
                value = int(utt)
                if 0 <= value <= 255:
                    self.custom_rgb.append(value)
                    self.need_custom_dialog()
                    if len(self.custom_rgb) == 3:
                        self.set_eye_color(rgb=self.custom_rgb)
                        self.reset_converse()
                    return True
                else:
                    raise
            except Exception as e:
                LOG.error(e)
                self.need_custom_dialog('error.')
        elif self.converse_context == 'need.brightness':
            try:
                brightness = self.parse_brightness(utt.lower())
                if not (0 <= brightness <= 100):
                    raise
                else:
                    bright_val = self.convert_brightness(brightness)
                    self.set_eye_brightness(bright_val)
                    self.reset_converse()
                    return True
            except Exception as e:
                LOG.error(e)
                self.speak_dialog('brightness.error', expect_response=True)
        return self.should_converse


def create_skill():
    return Mark1()
