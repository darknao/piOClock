#!/usr/bin/python
# -*- coding: UTF-8 -*-

import daemon
import os
import sys
import logging
import locale
import ssd1351
import datetime
import time
import signal
from clock import Clock
from textwrap import wrap


class piOClock(daemon.Daemon):
    def __init__(self):
        path, filename = os.path.split(os.path.abspath(__file__))

        pidfile = os.path.join("/var/run", "piOClock.pid")
        self.logfile = os.path.join("/var/log", "piOClock.log")

        logging.basicConfig(
            format='%(asctime)-23s - %(levelname)-7s - %(name)s - %(message)s',
            file=self.logfile)
        self.log = logging.getLogger("piOClock")
        self.log.setLevel(logging.INFO)
        locale.setlocale(locale.LC_ALL, 'fr_FR.UTF-8')

        daemon.Daemon.__init__(self, pidfile,
                               stderr=self.logfile, stdout=self.logfile)

    def shutdown(self, signum=0, frame=None):
        self.log.info("Shutdown clock...")
        self.clk.clear()
        self.clk.oled.text_center("Exiting...", "blue", size=30)
        self.clk.display()
        self.clk.stop_all()
        self.clk.oled.fillScreen(0)
        os._exit(0)

    def run(self):
        # Wiringpi pin number, NOT RPI PIN! see here: http://wiringpi.com/pins/
        # Maybe use RPi instead of wiringpi...
        RESET_PIN = 15
        DC_PIN = 16
        led = ssd1351.SSD1351(reset_pin=RESET_PIN, dc_pin=DC_PIN, rows=96)
        self.clk = Clock(led)

        # handle sigterm
        signal.signal(signal.SIGTERM, self.shutdown)

        now = datetime.datetime.now()

        led.clear()

        led.log.setLevel(logging.WARNING)

        hours = now.hour
        minutes = now.minute

        # time sync
        time.sleep(1-datetime.datetime.now().microsecond/1000.0/1000.0)
        REFRESH_RATE = 1

        # Alarm (fixed for testing purpose)
        self.clk.alarm = ""  # 07:00"
        try:
            while True:
                now = datetime.datetime.now()
                resync = 0
                self.clk.clear()
                if self.clk.input_thread.has_input.is_set():
                    with self.clk.audio_thread.lock:
                        wheel = self.clk.input_thread.wheel
                        click = self.clk.input_thread.click
                    self.clk.input_thread.has_input.clear()
                    if wheel != 0 and not self.clk.in_menu:
                        new_vol = self.clk.audio_thread.volume + self.clk.input_thread.wheel
                        self.clk.d_volume(new_vol)
                    elif click or wheel != 0:
                        self.clk.d_menu(click, wheel)
                    with self.clk.input_thread.lock:
                        self.clk.input_thread.wheel = 0
                        self.clk.input_thread.click = False
                # elif clk.freeze > 0:
                #    clk.freeze -= 1
                #    clk.d_menu()
                else:
                    self.clk.in_menu = False
                    self.clk.in_volume = False
                    self.clk.freeze = 0
                self.clk.d_clock()
                if not self.clk.in_menu:
                    self.clk.d_mplayer()
                    self.clk.d_signal()
                    self.clk.d_temp()
                    self.clk.d_audio()
                    self.clk.d_alarm()
                self.clk.d_cpu()

                self.clk.display()

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
                    self.clk.input_thread.has_input.wait(s + 1*self.clk.freeze)
                if resync:
                    self.log.info("process: %.4f sleep: %.4f total: %.4f resync: %.2fms"
                                  % (d, s, d+s, resync*1000))
                elif d > 0.5:
                    self.log.info("process: %.4f sleep: %.4f total: %.4f overhead!"
                                  % (d, s, d+s))
        except KeyboardInterrupt, e:
            self.shutdown()
        except Exception, e:
            self.clk.stop_all()
            self.clk.clear()
            self.clk.oled.text_center_y(0, "ERROR!", "red", size=36)
            error_lines = wrap("%s" % e, width=self.clk.oled.cols/7)
            y = 40
            for err_line in error_lines:
                self.clk.oled.draw_text(0, y, err_line, "white", size=12)
                y += 12
            self.log.error(e)
            self.clk.display()
            raise

if __name__ == "__main__":
        daemon = piOClock()

        if len(sys.argv) == 2:
                if 'start' == sys.argv[1]:
                        daemon.start()
                elif 'stop' == sys.argv[1]:
                        daemon.stop()
                elif 'restart' == sys.argv[1]:
                        daemon.restart()
                else:
                        print "Unknown command"
                        sys.exit(2)
                sys.exit(0)
        else:
                print "usage: %s start|stop|restart" % sys.argv[0]
                sys.exit(2)
