#!/bin/env python
# -*- coding: UTF-8 -*-

import datetime
import time
import ssd1351
import random
from PIL import Image, ImageFont
import psutil
import logging
import os
import locale
import th
import threading

log = logging.getLogger("main")
logging.basicConfig(
    format='%(asctime)-23s - %(levelname)-7s - %(name)s - %(message)s')
log.setLevel(logging.INFO)
locale.setlocale(locale.LC_ALL, 'fr_FR.UTF-8')
path, filename = os.path.split(os.path.abspath(__file__))
op = os.path

class Clock(object):
    """docstring for Clock"""
    alarm = ""
    alarm_running = False

    def __init__(self, oled):
        self.log = logging.getLogger(self.__class__.__name__)
        self.log.setLevel(logging.DEBUG)
        # OLED display
        self.oled = oled
        self.font_clk = ImageFont.truetype(op.join(path, "lcd.ttf"), 58)
        self.font_txt = ImageFont.truetype(op.join(path, "vermin_vibes_1989.ttf"), 20)
        self.font_big = ImageFont.truetype(op.join(path, "wendy.ttf"), 70)
        # self.tick = True
        self.oled.reset()
        self.oled.begin()
        size = (96 / 6) - 2
        title_y = 0
        self.oled.text_center_y(title_y, "init...", "red", size=size)
        title_y += size + 2
        self.oled.display()
        self.oled.set_contrast(10)
        self.clear = self.oled.clear
        self.display = self.oled.display
        # wifi signal ressourses
        self.signal = [
            Image.open(op.join(path, "radio_0.png")),
            Image.open(op.join(path, "radio_1.png")),
            Image.open(op.join(path, "radio_2.png")),
            Image.open(op.join(path, "radio_3.png"))]
        self.alarm_img = Image.open(op.join(path, "alarm.png"))
        # scrolling text settings
        self.scroll_txt = oled.cols
        self.SCROLLING_SPEED = 8
        # current time
        self.now = datetime.datetime.now()

        # MPlayer daemon
        w, h = self.oled.draw_text(0, title_y, "MPD :", "white", size=size)
        self.display()
        try:
            self.mpd_thread = th.MPlayer()
            self.mpd_thread.start()
            self.oled.draw_text(w+2, title_y, "OK", "green", size=size)
        except Exception, e:
            self.oled.draw_text(w+2, title_y, "KO", "red", size=size)
            self.d_mplayer = self.d_void
        self.display()
        title_y += size + 2

        # Temp sensor
        w, h = self.oled.draw_text(0, title_y, "Temp :", "white", size=size)
        self.display()
        try:
            self.temp_node = th.TempNode()
            self.temp_node.start()
            self.oled.draw_text(w+2, title_y, "OK", "green", size=size)
        except Exception, e:
            self.oled.draw_text(w+2, title_y, "KO", "red", size=size)
            self.d_temp = self.d_void
        self.display()
        title_y += size + 2

        # HWmonitor
        w, h = self.oled.draw_text(0, title_y, "HWmon :", "white", size=size)
        self.display()
        self.hwm_thread = th.HWmonitor()
        self.hwm_thread.start()
        self.oled.draw_text(w+2, title_y, "OK", "green", size=size)
        self.display()
        title_y += size + 2

        # Audio Control
        w, h = self.oled.draw_text(0, title_y, "Audio :", "white", size=size)
        self.display()
        self.audio_thread = th.Audio()
        self.audio_thread.start()
        self.oled.draw_text(w+2, title_y, "OK", "green", size=size)
        self.display()
        title_y += size + 2

        # Input Thread
        w, h = self.oled.draw_text(0, title_y, "Input :", "white", size=size)
        self.display()
        self.input_thread = th.Input()
        self.input_thread.start()
        self.oled.draw_text(w+2, title_y, "OK", "green", size=size)
        self.display()
        title_y += size + 2

        # Menu
        self.in_menu = False
        self.freeze = 0
        self.menu = {
            "player": {
                "play": self.mpd_thread.play,
                "stop": self.mpd_thread.stop_playing,
                "next": self.mpd_thread.next,
                "previous": self.mpd_thread.prev,
                "sleep": self.mpd_thread.sleep,
            },
            "stats": self.d_stats,
            "enable alarm (7h00)": self.alarm_on,
            "disable alarm": self.alarm_off,
        }
        self.menu_sub = None
        self.menu_cursor = 0


    def stop_all(self):
        self.log.debug("stopping all thread...")
        for thread in threading.enumerate():
            # self.log.debug("send stop to  %s" % thread.__class__.__name__)
            if thread.__class__.__name__ in ("_MainThread", "_DummyThread"):
                continue
            thread.stop()
        # for thread in threading.enumerate():
        #     if thread.name == "MainThread":
        #         continue
        #     thread.join()
        self.log.debug("stopping all thread complete!")

    def d_clock(self):
        now = datetime.datetime.now()
        font = ImageFont.truetype(op.join(path, "wendy.ttf"), 14)
        self.oled.text_center(now.strftime("%H:%M"), "#3333cc", font=self.font_clk)
        date = now.strftime("%a %d %b")
        w, h = self.oled.draw.textsize(date, font=font)

        self.oled.draw_text(self.oled.cols - w, 12, date, "#3333cc", font=font)

        if now.second % 2 > 0:
            self.oled.draw.rectangle([(58, 37), (67, 60)], fill="#000000")
        self.now = now

    def d_alarm(self):
        if self.alarm != "":
            self.oled.im.paste(self.alarm_img, (23 ,0))
            # check alarm
            if not self.alarm_running and self.now.strftime("%H:%M") == self.alarm:
                # wake up!
                self.log.info("Wake up !")
                # start mpc
                with self.mpd_thread.lock:
                    status = self.mpd_thread.status
                if status['state'] != "play":
                    try:
                        self.mpd_thread.rise()
                        self.alarm_running = True
                    except Exception, e:
                        self.log.exception(e)
                else:
                    self.log.warning("radio already playing? ok...")
                    self.alarm_running = True
            if self.alarm_running and self.now.hour > int(self.alarm.split(":")[0]) + 1:
                self.log.info("time to shut up!")
                self.mpd_thread.stop_playing()
                self.alarm_running = False

    def d_signal(self):
        """get signal power and display it on screen"""
        with self.hwm_thread.lock:
            wifi = self.hwm_thread.wifi_signal
        signal = int(wifi / 100.0 * 4)
        self.oled.im.paste(self.signal[signal], (0, 0))

    def d_cpu(self):
        self.hwm_thread.lock.acquire()
        cpu = self.hwm_thread.cpu
        self.hwm_thread.lock.release()
        cpu_bar = cpu / 100.0 * self.oled.cols
        cpu_color = "#003300"
        if cpu > 50:
            cpu_color = "#333300"
        if cpu >= 85:
            cpu_color = "#330000"
        self.oled.draw.line([(0, 95), (cpu_bar, 95)], fill=cpu_color)

    def d_mplayer(self):
        # refresh every minute
        self.mpd_thread.lock.acquire()
        status = self.mpd_thread.status
        title = self.mpd_thread.title
        self.mpd_thread.lock.release()

        if status['state'] == "play":
            if len(title) > 0:
                t_w, t_h = self.oled.draw_text(self.scroll_txt, 73, title, "#009900", font=self.font_txt)
                self.scroll_txt -= self.SCROLLING_SPEED
                if self.scroll_txt <= 0 - self.SCROLLING_SPEED - t_w:
                    self.scroll_txt = self.oled.cols
            # draw play icon here...
            if self.oled.contrast != 10:
                self.oled.set_contrast(10)
        else:
            # draw pause or whatever icon here...
            # alarm is not running anymore (if any)
            if self.alarm_running and self.now.strftime("%H:%M") != self.alarm:
                self.alarm_running = False
            # reset scrolling
            self.scroll_txt = self.oled.cols
            if self.oled.contrast != 1:
                self.oled.set_contrast(1)

    def d_temp(self):
        self.temp_node.lock.acquire()
        tempC = "%.1f'C" % self.temp_node.temp
        self.temp_node.lock.release()
        font = ImageFont.truetype(op.join(path, "wendy.ttf"), 20)
        w, h = self.oled.draw.textsize(tempC, font=font)
        self.oled.draw_text(self.oled.cols - w +2, -4, tempC, "#666666", font=font)

    def d_audio(self):
        with self.audio_thread.lock:
            volume = self.audio_thread.volume
        # background
        self.oled.draw.rectangle([(44, 3), (84, 5)], fill="#000000", outline="#333333")
        volume_bar = volume / 100.0 * 40
        self.oled.draw.rectangle([(44, 3), (44+volume_bar, 5)], fill="#006600")

    def d_volume(self, vol):
        if vol <= 100 and vol >= 0:
            self.mpd_thread.vol(vol)
        if self.oled.contrast != 10:
            self.oled.set_contrast(10)
        new_vol = min(max(vol, 0), 100)
        self.oled.text_center_y(15, "volume", "#006600", font=self.font_txt)
        self.oled.text_center_y(25, "%s %%" % (new_vol,), "#3333cc", font=self.font_big)

    def d_menu(self, click=False, pos=0):
        if self.oled.contrast != 10:
            self.oled.set_contrast(10)
        if click:
            self.freeze = 2
        if not self.in_menu:
            # reinit cursor
            self.menu_cursor = 0
            self.menu_sub = None
        if not self.menu_sub:
            menu = self.menu
        else:
            menu = self.menu[self.menu_sub]
        if self.in_menu and click:
            selected_item = menu[menu.keys()[self.menu_cursor]]
            if type(selected_item) == dict:
                # is menu
                self.menu_sub = menu.keys()[self.menu_cursor]
                menu = selected_item
                self.menu_cursor = 0
            else:
                if selected_item():
                    return
        self.oled.text_center_y(0, "M E N U", "#D93BD6", font=self.font_txt)
        self.menu_cursor = (self.menu_cursor + pos) % len(menu)

        for i, item in enumerate(menu.keys()):
            if i == self.menu_cursor:
                self.oled.draw_text(0, 15+i*10, ">", "white")
            self.oled.draw_text(10, 15+i*10, item, "#3333cc")
        self.in_menu = True

    def d_stats(self):
        self.oled.clear()
        self.oled.text_center_y(0, "stats", "#D93BD6", font=self.font_txt)
        return True

    def alarm_on(self):
        self.alarm = "07:00"
        self.freeze = 0

    def alarm_off(self):
        self.alarm = ""
        self.freeze = 0

    def d_void(self):
        pass


if __name__ == '__main__':
    # Wiringpi pin number, NOT RPI PIN! see here: http://wiringpi.com/pins/
    # Maybe use RPi instead of wiringpi...
    RESET_PIN = 15
    DC_PIN = 16
    led = ssd1351.SSD1351(reset_pin=RESET_PIN, dc_pin=DC_PIN, rows=96)
    clk = Clock(led)

    # For buttons, or encoders, check for interrupts (https://pythonhosted.org/RPIO/rpio_py.html)
    now = datetime.datetime.now()

    led.clear()
    font = ImageFont.truetype("lcd.ttf", 58)

    led.log.setLevel(logging.WARNING)

    hours = now.hour
    minutes = now.minute

    # time sync
    time.sleep(1-datetime.datetime.now().microsecond/1000.0/1000.0)
    REFRESH_RATE = 1

    # Alarm (fixed for testing purpose)
    clk.alarm = "" # 07:00"
    big = ImageFont.truetype("wendy.ttf", 70)
    try:
        while True:
            now = datetime.datetime.now()
            resync = 0
            clk.clear()
            if clk.input_thread.has_input.is_set():
                with clk.audio_thread.lock:
                    wheel = clk.input_thread.wheel
                    click = clk.input_thread.click
                if wheel != 0 and not clk.in_menu:
                    new_vol = clk.audio_thread.volume + clk.input_thread.wheel
                    clk.d_volume(new_vol)
                elif click or wheel != 0:
                    clk.d_menu(click, wheel)
                with clk.input_thread.lock:
                    clk.input_thread.wheel = 0
                    clk.input_thread.click = False
                clk.input_thread.has_input.clear()
            elif clk.freeze > 0:
                clk.freeze -= 1
                clk.d_menu()
            else:
                clk.in_menu = False
                clk.d_clock()
                clk.d_mplayer()
            if not clk.in_menu:
                clk.d_signal()
                clk.d_temp()
                clk.d_audio()
                clk.d_alarm()
            clk.d_cpu()

            clk.display()

            if minutes != now.minute:
                # refresh minutes
                minutes = now.minute
                if (now.microsecond > 100000):
                    resync = 0 - (now.microsecond/1000.0/1000.0)

            # end here
            d = (datetime.datetime.now()-now).total_seconds()
            s = max(REFRESH_RATE - d + resync, 0)
            if s > 0:
                # time.sleep(s)
                clk.input_thread.has_input.wait(s)
            if resync:
                log.info("process: %.4f sleep: %.4f total: %.4f resync: %.2fms"
                         % (d, s, d+s, resync*1000))
            elif d > 0.5:
                log.info("process: %.4f sleep: %.4f total: %.4f overhead!"
                         % (d, s, d+s))
    except KeyboardInterrupt, e:
        clk.clear()
        clk.oled.text_center("Exiting...", "blue", size=30)
        clk.display()
        clk.stop_all()
        clk.oled.fillScreen(0)
    except:
        clk.stop_all()
        clk.clear()
        clk.oled.text_center("ERROR!", "red", size=36)
        clk.display()
        raise
