# piOClock #

piOClock is a python alarm clock webradio running on a raspberryPi.

My cat didn't like my old alarm clock and toss it to the ground, hard enough to break it.
He told me he wanted something coolest, 2015 style, with tons of useless features.

![preview_v0.1](https://cloud.githubusercontent.com/assets/693402/8767852/5df5122a-2e6a-11e5-9c40-31f5d0efe695.jpg)

This is how the first version looks like.

## Features ##
- Clock, obviously
- Music player (using mpd)
- Ambient Temperature sensor
- Wifi for network capabilities (NTP, webradio, mpd controller)
- (*) Multiples alarms
- (*) Input controls

(*) planned features

## Components ##
- RaspberryPi A+
- [adafruit OLED 1.27" display](http://www.adafruit.com/products/1673) (it's damn small, maybe too much)

## Dependencies ##
- [spidev](https://pypi.python.org/pypi/spidev) (SPI)
- wiringpi2 (GPIO)
- [pillow](https://pypi.python.org/pypi/Pillow/2.9.0) (ImageDraw)
- numpy (fast RGB565 convertion)
- [python-mpd2](https://pypi.python.org/pypi/python-mpd2) (mpd client)
- alsaaudio (mixer control)
