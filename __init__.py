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
from ast import literal_eval as parse_tuple
from pytz import timezone
from datetime import datetime

from mycroft.messagebus.message import Message
from mycroft.skills.core import MycroftSkill
from mycroft.util.log import LOG
from mycroft.util.parse import normalize
from mycroft.audio import wait_while_speaking
from mycroft import intent_file_handler


def _hex_to_rgb(_hex):
    """ Convert hex color code to RGB tuple
    Args:
        hex (str): Hex color string, e.g '#ff12ff' or 'ff12ff'
    Returns:
        (rgb): tuple i.e (123, 200, 155) or None
    """
    try:
        if '#' in _hex:
            _hex = _hex.replace('#', "").strip()
        if len(_hex) != 6:
            return None
        (r, g, b) = int(_hex[0:2], 16), int(_hex[2:4], 16), int(_hex[4:6], 16)
        return (r, g, b)
    except Exception:
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
    for color, value in color_dict.items():
        s = SequenceMatcher(None, color_a, color)
        if s.ratio() > highest_ratio:
            highest_ratio = s.ratio()
            _color = color
    if highest_ratio > 0.8:
        return _color
    else:
        return None


class Mark1(MycroftSkill):

    IDLE_CHECK_FREQUENCY = 6  # in seconds

    def __init__(self):
        super(Mark1, self).__init__("Mark1")
        self.should_converse = False
        self._settings_loaded = False
        self.converse_context = None
        self.idle_count = 99
        self.hourglass_info = {}
        self.interaction_id = 0
        self._current_color = (34, 167, 240)  # Mycroft blue

        self.settings['auto_brightness'] = False
        self.settings['auto_dim_eyes'] = True
        self.settings['use_listening_beep'] = True
        self.settings['eye color'] = "default"
        self.settings['current_eye_color'] = self.settings['eye color']

    def initialize(self):
        # Initialize...
        self.brightness_dict = self.translate_namedvalues('brightness.levels')
        self.color_dict = self.translate_namedvalues('colors')
        self.settings['web eye color'] = self.settings['eye color']

        try:
            # Handle changing the eye color once Mark 1 is ready to go
            # (Part of the statup sequence)
            self.add_event('mycroft.internet.connected',
                           self.handle_internet_connected)

            self.add_event('mycroft.eyes.default',
                           self.handle_default_eyes)

            # Handle the 'waking' visual
            self.add_event('recognizer_loop:record_begin',
                           self.handle_listener_started)
            self.start_idle_check()

            # Handle the 'busy' visual
            self.bus.on('mycroft.skill.handler.start',
                        self.on_handler_started)
            self.bus.on('mycroft.skill.handler.complete',
                        self.on_handler_complete)

            self.bus.on('recognizer_loop:audio_output_start',
                        self.on_handler_interactingwithuser)
            self.bus.on('enclosure.mouth.think',
                        self.on_handler_interactingwithuser)
            self.bus.on('enclosure.mouth.events.deactivate',
                        self.on_handler_interactingwithuser)
            self.bus.on('enclosure.mouth.text',
                        self.on_handler_interactingwithuser)

            self.bus.on('mycroft.ready', self.reset_face)
        except Exception:
            LOG.exception('In Mark 1 Skill')

        # TODO: Add MycroftSkill.register_entity_list() and use the
        #  self.color_dict.keys() instead of duplicating data
        self.register_entity_file('color.entity')

        # Update use of wake-up beep
        self._sync_wake_beep_setting()

        self.settings_change_callback = self.on_websettings_changed

    def reset_face(self, message):
        self.enclosure.mouth_reset()
        self.set_eye_color(self.settings['current_eye_color'], initing=True)

    def shutdown(self):
        # Gotta clean up manually since not using add_event()
        self.bus.remove('mycroft.skill.handler.start',
                        self.on_handler_started)
        self.bus.remove('mycroft.skill.handler.complete',
                        self.on_handler_complete)
        self.bus.remove('recognizer_loop:audio_output_start',
                        self.on_handler_interactingwithuser)
        self.bus.remove('enclosure.mouth.think',
                        self.on_handler_interactingwithuser)
        self.bus.remove('enclosure.mouth.events.deactivate',
                        self.on_handler_interactingwithuser)
        self.bus.remove('enclosure.mouth.text',
                        self.on_handler_interactingwithuser)
        super(Mark1, self).shutdown()

    #####################################################################
    # Manage "busy" visual

    def on_handler_started(self, message):
        handler = message.data.get("name", "")
        # Ignoring handlers from this skill and from the background clock
        if "Mark1" in handler:
            return
        if "TimeSkill.update_display" in handler:
            return

        self.hourglass_info[handler] = self.interaction_id
        time.sleep(0.25)
        if self.hourglass_info.get(handler) == self.interaction_id:
            # Nothing has happend to indicate to the user that we are active,
            # so start a thinking interaction
            self.hourglass_info[handler] = -1
            self.enclosure.mouth_think()

    def on_handler_interactingwithuser(self, message):
        # Every time we do something that the user would notice, increment
        # an interaction counter.
        self.interaction_id += 1

    def on_handler_complete(self, message):
        handler = message.data.get("name", "")
        # Ignoring handlers from this skill and from the background clock
        if "Mark1" in handler:
            return
        if "TimeSkill.update_display" in handler:
            return

        if handler in self.hourglass_info:
            if self.hourglass_info[handler] == -1:
                self.enclosure.reset()
            self.hourglass_info[handler] = None

    #####################################################################
    # Manage "idle" visual state

    def start_idle_check(self):
        # Clear any existing checker
        self.cancel_scheduled_event('IdleCheck')

        if self.settings['auto_dim_eyes']:
            # Schedule a check every few seconds
            self.schedule_repeating_event(self.check_for_idle, 60,
                                          Mark1.IDLE_CHECK_FREQUENCY,
                                          name='IdleCheck')

    def check_for_idle(self):
        if not self.settings['auto_dim_eyes']:
            self.cancel_scheduled_event('IdleCheck')
            return

        if self.enclosure.display_manager.get_active() in ['', Mark1]:
            # No activity, start to fall asleep
            self.idle_count += 1

            if self.idle_count == 2:
                # Go into a 'sleep' visual state
                self.enclosure.eyes_look('d')

                # Lower the eyes
                time.sleep(0.5)  # prevent overwriting of eye down animation
                rgb = self._current_color
                self.enclosure.eyes_setpixel(3, r=rgb[0], g=rgb[1], b=rgb[2])
                self.enclosure.eyes_setpixel(8, r=rgb[0], g=rgb[1], b=rgb[2])
                self.enclosure.eyes_setpixel(15, r=rgb[0], g=rgb[1], b=rgb[2])
                self.enclosure.eyes_setpixel(20, r=rgb[0], g=rgb[1], b=rgb[2])
            elif self.idle_count > 2:
                self.cancel_scheduled_event('IdleCheck')

                # Go into an 'inattentive' visual state
                rgb = self._darker_color(self._current_color)
                for idx in range(0, 3):
                    self.enclosure.eyes_setpixel(idx, r=0, g=0, b=0)
                    time.sleep(0.05)  # hack to prevent serial port overflow
                for idx in range(3, 9):
                    self.enclosure.eyes_setpixel(idx,
                                                 r=rgb[0], g=rgb[1], b=rgb[2])
                    time.sleep(0.05)  # hack to prevent serial port overflow
                for idx in range(9, 15):
                    self.enclosure.eyes_setpixel(idx, r=0, g=0, b=0)
                    time.sleep(0.05)  # hack to prevent serial port overflow
                for idx in range(15, 21):
                    self.enclosure.eyes_setpixel(idx,
                                                 r=rgb[0], g=rgb[1], b=rgb[2])
                    time.sleep(0.05)  # hack to prevent serial port overflow
                for idx in range(21, 24):
                    self.enclosure.eyes_setpixel(idx, r=0, g=0, b=0)
                    time.sleep(0.05)  # hack to prevent serial port overflow
        else:
            self.idle_count = 0

    def _darker_color(self, rgb):
        r, g, b = rgb
        darker_r = int(r) // 2
        darker_g = int(g) // 2
        darker_b = int(b) // 2

        return darker_r, darker_g, darker_b

    def handle_listener_started(self, message):
        if not self.settings['auto_dim_eyes']:
            self.cancel_scheduled_event('IdleCheck')
            return

        # Check if in 'idle' state and visually come to attention
        if self.idle_count > 2:
            # Perform 'waking' animation
            self.enclosure.eyes_blink('b')
            rgb = self._current_color
            self.enclosure.eyes_color(rgb[0], rgb[1], rgb[2])
            # Begin checking for the idle state again
            self.idle_count = 0
            self.start_idle_check()

    #####################################################################
    # Manage network connction feedback

    def handle_internet_connected(self, message):
        pass

    #####################################################################
    # Reset eye appearance

    def handle_default_eyes(self, message):
        self.set_eye_color(self.settings['current_eye_color'], speak=False)

    #####################################################################
    # Web settings

    def on_websettings_changed(self):
        # Update eye color if necessary
        _color = self.settings.get('eye color')

        # TODO: This is a bit of a hack.  The on_web_settings() is being called
        # much more often than it should, not just when the setting actually
        # has changed.  This was overriding local eye color changes constantly.
        if self.settings['web eye color'] != _color:
            if _color and self._parse_to_rgb(_color):
                self.set_eye_color(color=_color, speak=False)
            self.settings['web eye color'] = _color

        # Update eye state if auto_dim_eyes changes...
        if self.settings.get("auto_dim_eyes"):
            self.start_idle_check()
        else:
            # No longer dimming, show open eyes if closed...
            self.cancel_scheduled_event('IdleCheck')
            if self.idle_count > 2:
                self.idle_count = 0
                rgb = self._current_color
                self.enclosure.eyes_color(rgb[0], rgb[1], rgb[2])

        # Update use of wake-up beep
        self._sync_wake_beep_setting()

    def _sync_wake_beep_setting(self):
        from mycroft.configuration.config import (
            LocalConf, USER_CONFIG, Configuration
        )
        config = Configuration.get()
        use_beep = self.settings.get("use_listening_beep") is True
        if not config['confirm_listening'] == use_beep:
            # Update local (user) configuration setting
            new_config = {
                'confirm_listening': use_beep
            }
            user_config = LocalConf(USER_CONFIG)
            user_config.merge(new_config)
            user_config.store()
            self.bus.emit(Message('configuration.updated'))

    #####################################################################
    # Color interactions

    def set_eye_color(self, color=None, rgb=None, speak=True, initing=False):
        """ Change the eye color on the faceplate, update saved setting
        Args:
            custom (bool): user provided rgb
            speak (bool): to have success speak on change
        """
        if color is not None:
            color_rgb = self._parse_to_rgb(color)
            if color_rgb is not None:
                (r, g, b) = color_rgb
        elif rgb is not None:
            (r, g, b) = rgb
        else:
            return  # no color provided!

        try:
            self.enclosure.eyes_color(r, g, b)
            self.idle_count = 0  # changing the color resets eyes to open
            self._current_color = (r, g, b)
            if speak and not initing:
                self.speak_dialog('set.color.success')

            # Update saved color if necessary
            _color = self._parse_to_rgb(self.settings.get('current_eye_color'))
            if self._current_color != _color:
                if color is not None:
                    self.settings['current_eye_color'] = color
                else:
                    self.settings['current_eye_color'] = [r, g, b]
        except Exception:
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
            except Exception:
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

    @intent_file_handler('eye.color.intent')
    def handle_eye_color(self, message):
        """ Callback to set eye color from list

            Args:
                message (dict): messagebus message from intent parser
        """
        color_str = (message.data.get('color', None) or
                     self.get_response('color.need'))
        if color_str:
            # TODO:18.02: normalize() should automatically get current lang
            match = fuzzy_match_color(normalize(color_str), self.color_dict)
            if match is not None:
                self.set_eye_color(color=match)
            else:
                self.speak_dialog('color.not.exist')

    def _parse_to_rgb(self, color):
        """ Convert color descriptor to RGB

        Parse a color name ('dark blue'), hex ('#000088') or rgb tuple
        '(0,0,128)' to an RGB tuple.

        Args:
            color (str): RGB, Hex, or color from color_dict
        Returns:
            (r, g, b) (tuple): Tuple of rgb values (0-255) or None
        """
        if not color:
            return None

        # check if named color in dict
        try:
            if color.lower() in self.color_dict:
                return _hex_to_rgb(self.color_dict[color.lower()])
        except Exception:
            pass

        # check if rgb tuple like '(0,0,128)'
        try:
            (r, g, b) = parse_tuple(color)
            if 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255:
                return (r, g, b)
            else:
                return None
        except Exception:
            pass

        # Finally check if color is hex, like '#0000cc' or '0000cc'
        return _hex_to_rgb(color)

    #####################################################################
    # Brightness intent interaction

    def percent_to_level(self, percent):
        """ converts the brigtness value from percentage to
             a value arduino can read

            Args:
                percent (int): interger value from 0 to 100

            return:
                (int): value form 0 to 30
        """
        return int(float(percent)/float(100)*30)

    def parse_brightness(self, brightness):
        """ parse text for brightness percentage

            Args:
                brightness (str): string containing brightness level

            return:
                (int): brightness as percentage (0-100)
        """

        try:
            # Handle "full", etc.
            name = normalize(brightness)
            if name in self.brightness_dict:
                return self.brightness_dict[name]

            if '%' in brightness:
                brightness = brightness.replace("%", "").strip()
                return int(brightness)
            if 'percent' in brightness:
                brightness = brightness.replace("percent", "").strip()
                return int(brightness)

            i = int(brightness)
            if i < 0 or i > 100:
                return None

            if i < 30:
                # Assmume plain 0-30 is "level"
                return int((i*100.0)/30.0)

            # Assume plain 31-100 is "percentage"
            return i
        except Exception:
            return None  # failed in an int() conversion

    def set_eye_brightness(self, level, speak=True):
        """ Actually change hardware eye brightness

            Args:
                level (int): 0-30, brightness level
                speak (bool): when True, speak a confirmation
        """
        self.enclosure.eyes_brightness(level)
        if speak is True:
            percent = int(float(level)*float(100)/float(30))
            self.speak_dialog(
                'brightness.set', data={'val': str(percent)+'%'})

    def _set_brightness(self, brightness):
        # brightness can be a number or word like "full", "half"
        percent = self.parse_brightness(brightness)
        if percent is None:
            self.speak_dialog('brightness.not.found.final')
        elif int(percent) is -1:
            self.handle_auto_brightness(None)
        else:
            self.auto_brightness = False
            self.set_eye_brightness(self.percent_to_level(percent))

    @intent_file_handler('brightness.intent')
    def handle_brightness(self, message):
        """ Intent Callback to set custom eye colors in rgb

            Args:
                message (dict): messagebus message from intent parser
        """
        brightness = (message.data.get('brightness', None) or
                      self.get_response('brightness.not.found'))
        if brightness:
            self._set_brightness(brightness)

    def _get_auto_time(self):
        """ get dawn, sunrise, noon, sunset, and dusk time

            returns:
                times (dict): dict with associated (datetime, level)
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
            'Sunrise': (sunrise, 20),  # high
            'Noon': (noon, 30),        # full
            'Sunset': (sunset, 5)      # dim
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
        for time_of_day, pair in auto_time.items():
            self.schedule_brightness(time_of_day, pair)
            now = arrow.now().timestamp
            t = arrow.get(pair[0]).timestamp
            if abs(now - t) < nearest_time_to_now[0]:
                nearest_time_to_now = (abs(now - t), pair[1], time_of_day)
        self.set_eye_brightness(nearest_time_to_now[1], speak=False)

        # SSP: I'm disabling this for now.  I don't think we
        # should announce this every day, it'll get tedious.
        #
        # tod = nearest_time_to_now[2]
        # if tod == 'Sunrise':
        #     self.speak_dialog('auto.sunrise')
        # elif tod == 'Sunset':
        #     self.speak_dialog('auto.sunset')
        # elif tod == 'Noon':
        #     self.speak_dialog('auto.noon')

    def _handle_eye_brightness_event(self, message):
        """ wrapper for setting eye brightness from
            eventscheduler

            Args:
                message (dict): messagebus message
        """
        if self.auto_brightness is True:
            time_of_day = message.data[0]
            level = message.data[1]
            self.cancel_scheduled_event(time_of_day)
            self.set_eye_brightness(level, speak=False)
            pair = self._get_auto_time()[time_of_day]
            self.schedule_brightness(time_of_day, pair)


def create_skill():
    return Mark1()
