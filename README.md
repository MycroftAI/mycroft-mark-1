## Mycroft Mark 1
A skill that can control the Mark 1 specific enclosure

## Description 
A skill that is specific to the Mark 1 enclosure! Do some fun stuff with the Mark 1 via the [enclosure api] (https://github.com/MycroftAI/mycroft-core/blob/dev/mycroft/client/enclosure/api.py). Pull request and contributions appreciated! Let's do some cool stuff with the Mark 1

Features
* Set the eye color via voice and settings in the web UI 
* Set custom eye color via voice and web UI (accepts values in RGB values)
* Set brightness of faceplate via voice (value from 0 to 30)
* Turn on auto brightness for faceplate via voice

Available default colors and RGB values
* 'red': (255, 0, 0)
* 'green': (0, 128, 0)
* 'yellow': (255, 255, 0)
* 'blue': (0, 0, 255)
* 'orange': (245, 130, 48)
* 'purple': (128, 0, 128)
* 'cyan': (0, 255, 255)
* 'magenta': (255, 0, 255)
* 'lime': (0, 255, 0)
* 'pink': (250, 190, 190)
* 'teal': (0, 128, 128)
* 'lavendar': (230, 190, 255)
* 'brown': (170, 110, 40)
* 'beige': (255, 250, 200)
* 'maroon': (128, 0, 0)
* 'mint': (170, 255, 195)
* 'olive': (128, 128, 0)
* 'coral': (255, 215, 180)
* 'navy': (0, 0, 128)
* 'grey': (128, 128, 128)
* 'gray': (128, 128, 128)
* 'white': (255, 255, 255)
* 'black': (0, 0, 0)
* 'default': (34, 167, 240)  # mycroft blue


## Examples 
* "Hey Mycroft, set eye color to red"
* "Hey Mycroft, set a custom eye color"
* "Hey Mycroft, set brightness to 25"
* "Hey Mycroft, turn on auto brightness"

## Credits 
Mycroft Inc

## Require 
platform_mark1 
