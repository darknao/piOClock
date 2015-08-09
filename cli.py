#!/usr/bin/python
# -*- coding: UTF-8 -*-

import argparse
import ssd1351

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('text',  type=str, nargs='+',
                       help='text to display')
    args = parser.parse_args()
    led = ssd1351.SSD1351(reset_pin=15, dc_pin=16, rows=96)
    led.reset()
    led.begin()
    lines = len(args.text)
    l_space = 96 / lines
    for i, text in enumerate(args.text):
        led.draw_text(0, 0+i*10, text, "#006600")
    led.display()