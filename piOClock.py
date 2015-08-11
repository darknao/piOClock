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
from clock import Clock

class piOClock(daemon.Daemon):
    def __init__(self):
        path, filename = os.path.split(os.path.abspath(__file__))

        pidfile = os.path.join(path, "piOClock.pid" )
        self.logfile = os.path.join(path, "piOClock.log" )

        logging.basicConfig(
            format='%(asctime)-23s - %(levelname)-7s - %(name)s - %(message)s',
            file=self.logfile)
        self.log = logging.getLogger("piOClock")
        self.log.setLevel(logging.INFO)
        locale.setlocale(locale.LC_ALL, 'fr_FR.UTF-8')

        daemon.Daemon.__init__(self, pidfile, stderr = self.logfile, stdout = self.logfile)

    def run(self):
        # main loop
        # Wiringpi pin number, NOT RPI PIN! see here: http://wiringpi.com/pins/
        # Maybe use RPi instead of wiringpi...
        RESET_PIN = 15
        DC_PIN = 16
        led = ssd1351.SSD1351(reset_pin=RESET_PIN, dc_pin=DC_PIN, rows=96)
        clk = Clock(led)

        # For buttons, or encoders, check for interrupts (https://pythonhosted.org/RPIO/rpio_py.html)
        now = datetime.datetime.now()

        led.clear()

        led.log.setLevel(logging.WARNING)

        hours = now.hour
        minutes = now.minute

        # time sync
        time.sleep(1-datetime.datetime.now().microsecond/1000.0/1000.0)
        REFRESH_RATE = 1

        # Alarm (fixed for testing purpose)
        clk.alarm = "" # 07:00"
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
                # elif clk.freeze > 0:
                #    clk.freeze -= 1
                #    clk.d_menu()
                else:
                    clk.in_menu = False
                    clk.freeze = 0
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
                    clk.input_thread.has_input.wait(s + 1*clk.freeze)
                if resync:
                    self.log.info("process: %.4f sleep: %.4f total: %.4f resync: %.2fms"
                             % (d, s, d+s, resync*1000))
                elif d > 0.5:
                    self.log.info("process: %.4f sleep: %.4f total: %.4f overhead!"
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
