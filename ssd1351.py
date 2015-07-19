#!/bin/env python
# -*- coding: UTF-8 -*-
#----------------------------------------------------------------------
# ssd1351.py from https://github.com/guyc/py-gaugette
# ported by Jason Porritt,
# base on original work by Guy Carpenter for display.py
#
# This library works with 
#   Adafruit's 128x128 SPI color OLED   http://www.adafruit.com/products/1431
# 
# The code is based heavily on Adafruit's Arduino library
#   https://github.com/adafruit/Adafruit_SSD1351
# written by Limor Fried/Ladyada for Adafruit Industries.
#
# Some important things to know about this device and SPI:
#
# - The SPI interface has no MISO connection.  It is write-only.
#
# SPI and GPIO calls are made through an abstraction library that calls
# the appropriate library for the platform.
# For the RaspberryPi:
#     wiring2
#     spidev
# For the BeagleBone Black:
#     Adafruit_BBIO.SPI 
#     Adafruit_BBIO.GPIO
#
# - The pin connections between the BeagleBone Black SPI0 and OLED module are:
#
#      BBB    display
#      P9_17  -> CS
#      P9_15  -> RST   (arbirary GPIO, change at will)
#      P9_13  -> D/C   (arbirary GPIO, change at will)
#      P9_22  -> CLK
#      P9_18  -> DATA
#      P9_3   -> VIN
#      N/C    -> 3.3Vo
#      P9_1   -> GND
#----------------------------------------------------------------------

import gaugette.gpio
import gaugette.spi
import gaugette.font5x8
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

    # Class constants are externally accessible as gaugette.display.display.CONST
    # or my_instance.CONST

    # Device name will be /dev/spidev-{bus}.{device}
    # dc_pin is the data/commmand pin.  This line is HIGH for data, LOW for command.
    # We will keep d/c low and bump it high only for commands with data
    # reset is normally HIGH, and pulled LOW to reset the display

    def __init__(self, bus=0, device=0, dc_pin="P9_15", reset_pin="P9_13", buffer_rows=256, buffer_cols=128, rows=128, cols=128):
        self.cols = cols
        self.rows = rows
        self.buffer_rows = buffer_rows
        self.mem_bytes = (self.buffer_rows * self.cols) # total bytes in SSD1351 display ram
        self.dc_pin = dc_pin
        self.reset_pin = reset_pin
        self.spi = gaugette.spi.SPI(bus, device)
        self.spi.spi.max_speed_hz = 16000000
        self.gpio = gaugette.gpio.GPIO()
        self.gpio.setup(self.reset_pin, self.gpio.OUT)
        self.gpio.output(self.reset_pin, self.gpio.HIGH)
        self.gpio.setup(self.dc_pin, self.gpio.OUT)
        self.gpio.output(self.dc_pin, self.gpio.LOW)
        self.font = gaugette.font5x8.Font5x8
        self.col_offset = 0
        self.bitmap = self.Bitmap(buffer_cols, buffer_rows)
        self.flipped = False
        self.im = Image.new("RGB", (cols, rows), 'black')
        #self.im = Image.open("oled.tif")
        self.draw = ImageDraw.Draw(self.im)
        self.log = logging.getLogger(self.__class__.__name__)
        self.log.setLevel(logging.INFO)
        self.contrast = 15

    def reset(self):
        self.gpio.output(self.reset_pin, self.gpio.LOW)
        time.sleep(0.010) # 10ms
        self.gpio.output(self.reset_pin, self.gpio.HIGH)

    def command(self, cmd, cmddata=None):
        # already low
        self.gpio.output(self.dc_pin, self.gpio.LOW)

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
        self.gpio.output(self.dc_pin, self.gpio.HIGH)
        #  chunk data to work around 255 byte limitation in adafruit implementation of writebytes
        # revisit - change to 1024 when Adafruit_BBIO is fixed.
        max_xfer = 255 if gaugette.platform == 'beaglebone' else 1024
        start = 0
        remaining = len(bytes)
        while remaining>0:
            count = remaining if remaining <= max_xfer else max_xfer
            remaining -= count
            #self.log.info("writebytes: %s \r\n%r" % (len(bytes[start:start+count]), bytes[start:start+count]))
            self.spi.writebytes(bytes[start:start+count])
            start += count
        self.gpio.output(self.dc_pin, self.gpio.LOW)

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
        self.command(self.CMD_CONTRASTABC, [0xC8, 0xc8, 0xC8])
        self.set_contrast(self.contrast)
        #self.command(self.CMD_CONTRASTMASTER, 0x0F)
        self.command(self.CMD_SETVSL, [0xA0, 0xB5, 0x55])

        self.command(self.CMD_PRECHARGE2, 0x01)
        self.command(self.CMD_DISPLAYON)

    def set_contrast(self, level):
        level &= 0x0F
        self.command(self.CMD_CONTRASTMASTER, level)
        self.contrast = level

    def clear_display(self):
        self.bitmap.clear()

    def invert_display(self):
        self.command(self.CMD_INVERTDISPLAY)

    #def flip_display(self, flipped=True):
    #    self.flipped = flipped
    #    if flipped:
    #        self.command(self.COM_SCAN_INC)
    #        self.command(self.SEG_REMAP | 0x00)
    #    else:
    #        self.command(self.COM_SCAN_DEC)
    #        self.command(self.SET_COM_PINS, 0x02)

    def normal_display(self):
        self.command(self.CMD_NORMALDISPLAY)

    #def set_contrast(self, contrast=0x7f):
    #    self.command(self.SET_CONTRAST, contrast)

    def scale(self, x, inLow, inHigh, outLow, outHigh):
        return ((x - inLow) / float(inHigh) * outHigh) + outLow

    def encode_color(self, color):
        red = (color >> 16) & 0xFF
        green = (color >> 8) & 0xFF
        blue = color & 0xFF
        redScaled = int(self.scale(red, 0, 0xFF, 0, 0x1F))
        greenScaled = int(self.scale(green, 0, 0xFF, 0, 0x3F))
        blueScaled = int(self.scale(blue, 0, 0xFF, 0, 0x1F))
        # print color, redScaled, greenScaled, blueScaled
        return (((redScaled << 6) | greenScaled) << 5) | blueScaled

    def color565(self, r, g, b):
        # 15 14 13 12 11 10 9 8 7 6 5 4 3 2 1 0
        #  r  r  r  r  r  g g g g g g b b b b b
        # r = 31 g = 63 b = 31
        redScaled = int(self.scale(r, 0, 0xFF, 0, 0x1F))
        greenScaled = int(self.scale(g, 0, 0xFF, 0, 0x3F))
        blueScaled = int(self.scale(b, 0, 0xFF, 0, 0x1F))

        return (((redScaled << 6) | greenScaled) << 5) | blueScaled

    # Diagnostic print of the memory buffer to stdout
    def dump(self):
        data = list(self.im.getdata())
        for y in range(0, self.rows):
            mem_row = y * self.cols
            line = ""
            for x in range(0, self.cols):
                mem_col = x
                offset = mem_row + mem_col
                # print offset
                if sum(data[offset]) > 0:
                    line += '*'
                else:
                    line += ' '
            print('|'+line+'|')

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

    def draw_text2(self, x, y, string, color, size=2, space=1):
        font_bytes = self.font.bytes
        font_rows = self.font.rows
        font_cols = self.font.cols
        for c in string:
            p = ord(c) * font_cols
            for col in range(0, font_cols):
                mask = font_bytes[p]
                p += 1
                py = y
                for row in range(0, 8):
                    for sy in range(0, size):
                        px = x
                        for sx in range(0, size):
                            self.drawPixel(px, py, (mask & 0x1)*color)
                            px += 1
                        py += 1
                    mask >>= 1
                x += size
            x += space

    def draw_textBMP(self, x, y, string, color, size=2, space=1):
        font_bytes = self.font.bytes
        font_rows = self.font.rows
        font_cols = self.font.cols
        color = self.encode_color(color)
        for c in string:
            p = ord(c) * font_cols
            for col in range(0, font_cols):
                mask = font_bytes[p]
                p += 1
                py = y
                for row in range(0, 8):
                    for sy in range(0, size):
                        px = x
                        for sx in range(0, size):
                            self.bitmap.drawPixel(px, py, (mask & 0x1)*color)
                            px += 1
                        py += 1
                    mask >>= 1
                x += size
            x += space

    def clear_block(self, x0, y0, dx, dy):
        self.bitmap.clear_block(x0, y0, dx, dy)

    def draw_text3(self, x, y, string, font):
        return self.bitmap.draw_text(x, y, string, font)

    def text_width(self, string, font):
        return self.bitmap.text_width(string, font)

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
        self.log.debug("im2list convert")
        image = np.array(self.im).reshape(-1, 3)
        self.log.debug("im2list rgb 2 565")
        image[:,0] *= 0.121
        image[:,1] *= 0.247
        image[:,2] *= 0.121
        self.log.debug("im2list shift")
        d = np.left_shift(image, [11, 5, 0]).sum(axis=1)
        self.log.debug("im2list prepare frames")
        data =np.dstack(((d>>8)&0xff, d&0xff)).flatten()
        self.log.debug("im2list return")
        return data.tolist()

    def display(self, x=0, y=0, w=None, h=None):
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
        #self.goTo(x, y)
        self.log.debug("set display end")
        data = []
        start = y * self.cols + x
        end = h * self.cols + w
        self.log.debug("get data")

        self.data(self.im2list())
        self.log.debug("disp out")

    def dump_display(self, x=0, y=0, w=None, h=None):
        if h is None:
            h = self.rows
        if w is None:
            w = self.cols

        self.setDisplay(x, y, w-1, h-1)
        data = []
        start = y * self.cols + x
        end = h * self.cols + w
        image = list(self.im.getdata())
        line = ""
        for idx, (r, g, b) in enumerate(image[start:end]):
            if idx % self.cols < (w - x):
                c = self.color565(r, g, b)
                if c > 0:
                    line += "*"
                else:
                    line += " "
            if idx % self.cols == 0:
                print('|'+line+'|')
                line = ""

    def dump_disp(self):
        #image = list(self.im.convert("I").getdata())
        image = np.array(self.im).reshape(-1,3)
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


    class Bitmap:

        # TODO: Only functioning value is 16
        BITS_PER_PIXEL = 16
    
        # Pixels are stored in column-major order!
        # This makes it easy to reference a vertical slice of the display buffer
        # and we use the to achieve reasonable performance vertical scrolling 
        # without hardware support.
        def __init__(self, cols, rows):
            self.rows = rows
            self.cols = cols
            self.data = [0] * (self.cols * self.rows)

        def clear(self):
            for i in range(0,len(self.data)):
                self.data[i] = 0

        # Diagnostic print of the memory buffer to stdout 
        # TODO: Only works for BITS_PER_PIXEL value of 16
        def dump(self):
            for y in range(0, self.rows):
                mem_row = y * self.cols
                line = ""
                for x in range(0, self.cols):
                    mem_col = x
                    offset = mem_row + mem_col
                    # print offset
                    if self.data[offset] > 0:
                        line += '*'
                    else:
                        line += ' '
                print('|'+line+'|')
                
        def draw_pixel(self, x, y, on=True):
            if (x<0 or x>=self.cols or y<0 or y>=self.rows):
                return
            mem_col = x
            mem_row = y
            offset = y * self.rows * mem_col
    
            if on:
                self.data[offset] = 0xF
            else:
                self.data[offset] = 0

        def drawPixel(self, x, y, color):
            if (x < 0 or x >= self.cols or y < 0 or y >= self.rows):
                return
            offset = y * self.cols + x
            self.data[offset] = color


        def clear_block(self, x0,y0,dx,dy):
            for x in range(x0,x0+dx):
                for y in range(y0,y0+dy):
                    self.draw_pixel(x,y,0)

        # returns the width in pixels of the string allowing for kerning & interchar-spaces
        def text_width(self, string, font):
            x = 0
            prev_char = None
            for c in string:
                if (c<font.start_char or c>font.end_char):
                    if prev_char != None:
                        x += font.space_width + prev_width + font.gap_width
                    prev_char = None
                else:
                    pos = ord(c) - ord(font.start_char)
                    (width,offset) = font.descriptors[pos]
                    if prev_char != None:
                        x += font.kerning[prev_char][pos] + font.gap_width
                    prev_char = pos
                    prev_width = width
                    
            if prev_char != None:
                x += prev_width
                
            return x
              
        def draw_text(self, x, y, string, font):
            height = font.char_height
            prev_char = None
    
            for c in string:
                if (c<font.start_char or c>font.end_char):
                    if prev_char != None:
                        x += font.space_width + prev_width + font.gap_width
                    prev_char = None
                else:
                    pos = ord(c) - ord(font.start_char)
                    (width,offset) = font.descriptors[pos]
                    if prev_char != None:
                        x += font.kerning[prev_char][pos] + font.gap_width
                    prev_char = pos
                    prev_width = width
                    
                    bytes_per_row = (width + 7) * (self.BITS_PER_PIXEL / 8)
                    for row in range(0,height):
                        py = y + row
                        mask = 0x80
                        p = offset
                        for col in range(0,width):
                            px = x + col
                            if (font.bitmaps[p] & mask):
                                self.draw_pixel(px,py,1)  # for kerning, never draw black
                            mask >>= 1
                            if mask == 0:
                                mask = 0x80
                                p+=1
                        offset += bytes_per_row
              
            if prev_char != None:
                x += prev_width
    
            return x

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
    led = ssd1351.SSD1351(reset_pin=15, dc_pin=16, rows=96, buffer_rows=96)
    led.begin()

    now = datetime.datetime.now()
    led.text_center("init...", "red", size=16)
    led.display()
    led.clear()
    font = ImageFont.truetype("lcd.ttf", 58)

    # clock
    led.text_center(now.strftime("%H:%M"), "#3333cc", font=font)

    radio = [
        Image.open("radio_0.png"),
        Image.open("radio_1.png"),
        Image.open("radio_2.png"),
        Image.open("radio_3.png")]
    led.im.paste(radio[random.randint(0, 3)], (0, 0))
    led.draw.line([(0, 16), (128, 16)], fill="#000066")
    # clock_size = led.draw.textsize(now.strftime("%H:%M"), font=font)
    # clock_x = max((led.cols-clock_size[0])/2, 0)
    # clock_y = max((led.rows-clock_size[1])/2+4, 0)
    # led.draw_text(clock_x, clock_y, now.strftime("%H:%M"), "#2F4F70", font)
    # led.display(clock_x+90, clock_y, clock_x+118, clock_y+26)
    # led.dump_display()
    # led.dump_disp()

    hours = now.hour
    minutes = now.minute
    tick = True
    # time sync
    time.sleep(1-datetime.datetime.now().microsecond/1000.0/1000.0)
    REFRESH_RATE = 1
    SCROLLING_SPEED = 8
    scroll_txt = led.cols
    try:
        led.display()
        while True:
            now = datetime.datetime.now()
            led.clear()
            resync = 0
            # headbar
            led.im.paste(radio[random.randint(0, 3)], (0, 0))
            led.draw.line([(0, 16), (128, 16)], fill="#000066")
            clock_x, clock_y = led.text_center(now.strftime("%H:%M"), "#3333cc", font=font)
            if hours != now.hour:
                # refresh hours
                hours = now.hour
                led.display(clock_x, clock_y, clock_x+50, clock_y+41)
            if minutes != now.minute:
                # refresh minutes
                minutes = now.minute
                led.display(clock_x+77, clock_y, clock_x+128, clock_y+41)
                if (now.microsecond > 100000):
                    resync = 0 - (now.microsecond/1000.0/1000.0)
            # refresh seconds
            # led.display(clock_x+90, clock_y+1, clock_x+118, clock_y+26)
            if tick:
                led.rawFillRect(clock_x+59, clock_y+10, 6, 25, 0)
                tick = False
            else:
                led.display(clock_x+59, clock_y+10, clock_x+65, clock_y+34)
                tick = True
            # add everything else here ...

            cpu = psutil.cpu_percent()
            cpu_bar = cpu / 100.0 * led.cols
            cpu_color = "green"
            if cpu > 50:
                cpu_color = "yellow"
            if cpu >= 85:
                cpu_color = "red"
            led.draw.line([(0, 95), (cpu_bar, 95)], fill=cpu_color)
            led.display(0, 95, 128, 95)

            t_w, t_h = led.draw_text(scroll_txt, 70, " super long and boring text", "#cc00cc", size=14)
            led.display(scroll_txt, 70, scroll_txt+t_w+SCROLLING_SPEED, 70+t_h)
            scroll_txt -= SCROLLING_SPEED
            if scroll_txt <= 0 - SCROLLING_SPEED - t_w:
                scroll_txt = led.cols
            os.system('clear')
            led.dump_disp()
            # end here
            d = (datetime.datetime.now()-now).microseconds / 1000.0 / 1000.0
            s = REFRESH_RATE - d + resync
            if s > 0:
                time.sleep(s)
            if resync:
                log.info("process: %.4f sleep: %.4f total: %.4f cpu: %.2f resync: %.2fms" % (d, s, d+s, cpu, resync*1000))
    except KeyboardInterrupt, e:
        led.fillScreen(0)
