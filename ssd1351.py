#!/bin/env python
# -*- coding: UTF-8 -*-
# ----------------------------------------------------------------------
# ssd1351.py from https://github.com/guyc/py-gaugette
# ported by Jason Porritt,
# and reworked by darknao,
# based on original work by Guy Carpenter for display.py
#
# This library works with
#   Adafruit's 128x96 SPI color OLED   http://www.adafruit.com/products/1673
#
# The code is based heavily on Adafruit's Arduino library
#   https://github.com/adafruit/Adafruit_SSD1351
# written by Limor Fried/Ladyada for Adafruit Industries.
#
# It has the following dependencies:
# wiringpi2 for GPIO
# spidev for SPI
# PIL for easy drawing capabilities
# numpy for fast RGB888 to RGB565 convertion
# ----------------------------------------------------------------------

# NEED HEAVY CLEANING !

import wiringpi2
import spidev
import time
import sys
from PIL import Image, ImageDraw, ImageFont
import logging
import numpy as np
import tools


class SSD1351:
    # SSD1351 Commands

    EXTERNAL_VCC   = 0x1
    SWITCH_CAP_VCC = 0x2

    MEMORY_MODE_HORIZ = 0x00
    MEMORY_MODE_VERT  = 0x01

    CMD_SETCOLUMN         = 0x15
    CMD_SETROW            = 0x75
    CMD_WRITERAM          = 0x5C
    CMD_READRAM           = 0x5D
    CMD_SETREMAP          = 0xA0
    CMD_STARTLINE         = 0xA1
    CMD_DISPLAYOFFSET     = 0xA2
    CMD_DISPLAYALLOFF     = 0xA4
    CMD_DISPLAYALLON      = 0xA5
    CMD_NORMALDISPLAY     = 0xA6
    CMD_INVERTDISPLAY     = 0xA7
    CMD_FUNCTIONSELECT    = 0xAB
    CMD_DISPLAYOFF        = 0xAE
    CMD_DISPLAYON         = 0xAF
    CMD_PRECHARGE         = 0xB1
    CMD_DISPLAYENHANCE    = 0xB2
    CMD_CLOCKDIV          = 0xB3
    CMD_SETVSL            = 0xB4
    CMD_SETGPIO           = 0xB5
    CMD_PRECHARGE2        = 0xB6
    CMD_SETGRAY           = 0xB8
    CMD_USELUT            = 0xB9
    CMD_PRECHARGELEVEL    = 0xBB
    CMD_VCOMH             = 0xBE
    CMD_CONTRASTABC       = 0xC1
    CMD_CONTRASTMASTER    = 0xC7
    CMD_MUXRATIO          = 0xCA
    CMD_COMMANDLOCK       = 0xFD
    CMD_HORIZSCROLL       = 0x96
    CMD_STOPSCROLL        = 0x9E
    CMD_STARTSCROLL       = 0x9F

    # Device name will be /dev/spidev-{bus}.{device}
    # dc_pin is the data/commmand pin.  This line is HIGH for data, LOW for command.
    # We will keep d/c low and bump it high only for commands with data
    # reset is normally HIGH, and pulled LOW to reset the display

    def __init__(self, bus=0, device=0, dc_pin="P9_15", reset_pin="P9_13", rows=128, cols=128):
        self.cols = cols
        self.rows = rows
        self.dc_pin = dc_pin
        self.reset_pin = reset_pin
        # SPI
        self.spi = spidev.SpiDev(bus, device)
        self.spi.max_speed_hz = 16000000    # 16Mhz
        # GPIO
        self.gpio = wiringpi2.GPIO(wiringpi2.GPIO.WPI_MODE_PINS)
        self.gpio.pinMode(self.reset_pin, self.gpio.OUTPUT)
        self.gpio.digitalWrite(self.reset_pin, self.gpio.HIGH)
        self.gpio.pinMode(self.dc_pin, self.gpio.OUTPUT)
        self.gpio.digitalWrite(self.dc_pin, self.gpio.LOW)
        # Drawing tools
        self.im = Image.new("RGB", (cols, rows), 'black')
        self.draw = ImageDraw.Draw(self.im)
        # logging
        self.log = logging.getLogger(self.__class__.__name__)
        self.log.setLevel(logging.INFO)
        self.contrast = 15

    def reset(self):
        self.gpio.digitalWrite(self.reset_pin, self.gpio.LOW)
        time.sleep(0.010) # 10ms
        self.gpio.digitalWrite(self.reset_pin, self.gpio.HIGH)

    def command(self, cmd, cmddata=None):
        # already low
        # self.gpio.digitalWrite(self.dc_pin, self.gpio.LOW)

        if type(cmd) == list:
            self.spi.writebytes(cmd)
        else:
            self.spi.writebytes([cmd])

        if cmddata is not None:
            if type(cmddata) == list:
                self.data(cmddata)
            else:
                self.data([cmddata])

    def data(self, bytes):
        self.gpio.digitalWrite(self.dc_pin, self.gpio.HIGH)
        max_xfer = 1024
        start = 0
        remaining = len(bytes)
        while remaining>0:
            count = remaining if remaining <= max_xfer else max_xfer
            remaining -= count
            self.spi.writebytes(bytes[start:start+count])
            start += count
        self.gpio.digitalWrite(self.dc_pin, self.gpio.LOW)

    def begin(self, vcc_state = SWITCH_CAP_VCC):
        time.sleep(0.001) # 1ms
        self.reset()
        self.command(self.CMD_COMMANDLOCK, 0x12)
        self.command(self.CMD_COMMANDLOCK, 0xB1)
        self.command(self.CMD_DISPLAYOFF)
        self.command(self.CMD_CLOCKDIV, 0xF1)

        # support for 128x128 line mode
        self.command(self.CMD_MUXRATIO, 127)
        self.command(self.CMD_SETREMAP, 0x74)

        self.command(self.CMD_SETCOLUMN, [0x00, self.cols-1])
        self.command(self.CMD_SETROW, [0x00, self.rows-1])

        # TODO Support 96-row display
        self.command(self.CMD_STARTLINE, 96)
        self.command(self.CMD_DISPLAYOFFSET, 0x00)
        self.command(self.CMD_SETGPIO, 0x00)
        self.command(self.CMD_FUNCTIONSELECT, 0x01)

        self.command(self.CMD_PRECHARGE, 0x32)
        self.command(self.CMD_VCOMH, 0x05)
        self.command(self.CMD_NORMALDISPLAY)
        self.set_contrast(200) # c8 -> 200
        self.set_master_contrast(10)
        self.command(self.CMD_SETVSL, [0xA0, 0xB5, 0x55])

        self.command(self.CMD_PRECHARGE2, 0x01)
        self.command(self.CMD_DISPLAYON)

    def set_master_contrast(self, level):
        # 0 to 15
        level &= 0x0F
        self.command(self.CMD_CONTRASTMASTER, level)

    def set_contrast(self, level):
        # 0 to 255
        level &= 0xFF
        self.command(self.CMD_CONTRASTABC, [level, level, level])
        self.contrast = level

    def invert_display(self):
        self.command(self.CMD_INVERTDISPLAY)

    def normal_display(self):
        self.command(self.CMD_NORMALDISPLAY)

    def scale(self, x, inLow, inHigh, outLow, outHigh):
        return ((x - inLow) / float(inHigh) * outHigh) + outLow

    def encode_color(self, color):
        red = (color >> 16) & 0xFF
        green = (color >> 8) & 0xFF
        blue = color & 0xFF
        redScaled = int(self.scale(red, 0, 0xFF, 0, 0x1F))
        greenScaled = int(self.scale(green, 0, 0xFF, 0, 0x3F))
        blueScaled = int(self.scale(blue, 0, 0xFF, 0, 0x1F))
        return (((redScaled << 6) | greenScaled) << 5) | blueScaled

    def color565(self, r, g, b):
        # 15 14 13 12 11 10 9 8 7 6 5 4 3 2 1 0
        #  r  r  r  r  r  g g g g g g b b b b b
        # r = 31 g = 63 b = 31
        redScaled = int(self.scale(r, 0, 0xFF, 0, 0x1F))
        greenScaled = int(self.scale(g, 0, 0xFF, 0, 0x3F))
        blueScaled = int(self.scale(b, 0, 0xFF, 0, 0x1F))

        return (((redScaled << 6) | greenScaled) << 5) | blueScaled

    def goTo(self, x, y):
        if x >= self.cols or y >= self.rows:
            return

        # set x and y coordinate
        self.command(self.CMD_SETCOLUMN, [x, self.cols-1])
        self.command(self.CMD_SETROW, [y, self.rows-1])
        self.command(self.CMD_WRITERAM)

    def drawPixel(self, x, y, color):
        if x >= self.cols or y >= self.rows:
            return

        if x < 0 or y < 0:
            return

        color = self.encode_color(color)

        # set location
        self.goTo(x, y)
        self.data([color >> 8, color & 0xFF])

    def clear(self):
        """Clear display buffer"""
        self.im = Image.new("RGB", (self.cols, self.rows), 'black')
        self.draw = ImageDraw.Draw(self.im)

    def text_center(self, string, color, font=None, size=10):
        if font is None:
            font = ImageFont.truetype("/usr/share/fonts/truetype/droid/DroidSansMono.ttf", size)

        text_size = self.draw.textsize(string, font=font)
        text_x = max((self.cols-text_size[0])/2, 0)
        text_y = max((self.rows-text_size[1])/2, 0)
        self.draw_text(text_x, text_y, string, color, font=font, size=size)
        return text_x, text_y

    def text_center_y(self, text_y, string, color, font=None, size=10):
        if font is None:
            font = ImageFont.truetype("/usr/share/fonts/truetype/droid/DroidSansMono.ttf", size)

        text_size = self.draw.textsize(string, font=font)
        text_x = max((self.cols-text_size[0])/2, 0)
        self.draw_text(text_x, text_y, string, color, font=font, size=size)
        return text_x, text_y

    def draw_text(self, x, y, string, color, font=None, size=10):
        if font is None:
            font = ImageFont.truetype("/usr/share/fonts/truetype/droid/DroidSansMono.ttf", size)
        self.draw.text((x, y), string, font=font, fill=color)
        return self.draw.textsize(string, font=font)

    def fillScreen(self, fillcolor):
        self.rawFillRect(0, 0, self.cols, self.rows, fillcolor)

    def rawFillRect(self, x, y, w, h, fillcolor):
        self.log.debug("fillScreen start")
        # Bounds check
        if (x >= self.cols) or (y >= self.rows):
            return

        # Y bounds check
        if y+h > self.rows:
            h = self.rows - y - 1

        # X bounds check
        if x+w > self.cols:
            w = self.cols - x - 1

        self.setDisplay(x, y, x+(w-1), y+(h-1))
        color = self.encode_color(fillcolor)

        self.data([color >> 8, color & 0xFF] * w*h)
        self.log.debug("fillScreen end")

    def setDisplay(self, startx, starty, endx, endy):
        if startx >= self.cols or starty >= self.rows:
            return

        # Y bounds check
        if endx > self.cols - 1:
            endx = self.cols - 1

        # X bounds check
        if endy > self.rows - 1:
            endy = self.rows - 1

        # set x and y coordinate
        # print "x:%d y:%d endx:%d endy:%d" % (startx, starty, endx, endy)
        self.command(self.CMD_SETCOLUMN, [startx, endx])
        self.command(self.CMD_SETROW, [starty, endy])
        self.command(self.CMD_WRITERAM)

    def im2list(self):
        """Convert PIL RGB888 Image to SSD1351 RAM buffer"""
        image = np.array(self.im).reshape(-1, 3)
        image[:,0] *= 0.121
        image[:,1] *= 0.247
        image[:,2] *= 0.121
        d = np.left_shift(image, [11, 5, 0]).sum(axis=1)
        data =np.dstack(((d>>8)&0xff, d&0xff)).flatten()
        return data.tolist()

    def display(self, x=0, y=0, w=None, h=None):
        """Send display buffer to the device"""
        self.log.debug("disp in")
        if h is None:
            h = self.rows
        if w is None:
            w = self.cols

        x = max(x, 0)
        y = max(y, 0)
        w = min(w, self.cols)
        h = min(h, self.rows)
        if w-x < 0:
            return
        self.log.debug("set display")
        self.setDisplay(x, y, w-1, h-1)
        self.log.debug("set display end")
        data = []
        start = y * self.cols + x
        end = h * self.cols + w
        self.log.debug("get data")

        self.data(self.im2list())
        self.log.debug("disp out")

    @tools.timed
    def dump_disp(self):
        """Dump display buffer on screen,
           for debugging purpose"""
        image = np.array(self.im).reshape(-1, 3)
        for r in range(0, self.rows,2):
            txt = [None,] * self.cols
            start = r*self.cols
            end = start + self.cols * 2
            line = image[start:end]
            for c in range(len(line)):
                idx = c % self.cols
                if line[c].sum() > 0:
                    if txt[idx] is None:
                        txt[idx] = '▀'
                    elif txt[idx] == '▀':
                        txt[idx] = '█'
                    else:
                        txt[idx] = '▄'
                else:
                    if txt[idx] is None:
                        txt[idx] = ' '
            print ''.join(txt) + '║'

    @tools.timed
    def dump_disp2(self):
        #image = list(self.im.convert("I").getdata())
        image = np.array(self.im)
        for row, r in enumerate(image):
            if row % 2 == 0:
                txt = [None,] * self.cols
            for idx, c in enumerate(r):
                if c.sum() > 0:
                    if txt[idx] is None:
                        txt[idx] = '▀'
                    elif txt[idx] == '▀':
                        txt[idx] = '█'
                    else:
                        txt[idx] = '▄'
                else:
                    if txt[idx] is None:
                        txt[idx] = ' '
            print ''.join(txt) + '║'


if __name__ == '__main__':
    import datetime
    import time
    import ssd1351
    import random
    from PIL import ImageFont
    import psutil
    import logging
    import os

    log = logging.getLogger("clock")
    logging.basicConfig(
        format='%(asctime)-23s - %(levelname)-7s - %(name)s - %(message)s')
    log.setLevel(logging.INFO)

    RESET_PIN = 15
    DC_PIN = 16
    led = ssd1351.SSD1351(reset_pin=15, dc_pin=16, rows=96)
    led.begin()
    led.fillScreen(0)
    color = 0x000000
    bands = 10
    color_step = 0xFF / bands
    color_width = led.cols / 3

    for x in range(0, led.rows, led.rows/bands):
        led.rawFillRect(0, x, color_width, bands, color&0xff0000)
        led.rawFillRect(color_width, x, color_width*2, bands, color&0xff00)
        led.rawFillRect(color_width*2, x, color_width*3, bands, color&0xff)
        color = (color + (color_step << 16) + (color_step << 8) + (color_step)) & 0xFFFFFF

