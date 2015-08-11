#!/bin/env python
# -*- coding: UTF-8 -*-

import os
import glob
import logging
import threading
import time
import psutil
from mpd import MPDClient, ConnectionError
import alsaaudio
from pythonwifi.iwlibs import Wireless
import select
import RPi.GPIO as gpio
import socket
import struct
import fcntl

gpio.setmode(gpio.BCM)


class Thread(threading.Thread):
    def __init__(self):
        super(Thread, self).__init__()
        self.log = logging.getLogger(self.__class__.__name__)
        self.log.setLevel(logging.DEBUG)
        self.must_stop = threading.Event()
        self.lock = threading.Lock()
        self.daemon = True

    def stop(self):
        self.log.debug("%s request stop" % self.name)
        self.must_stop.set()


class HWmonitor(Thread):
    """docstring for HWmonitor"""
    def __init__(self):
        super(HWmonitor, self).__init__()
        self.cpu = 0
        self.wifi_signal = 0
        self.wifi = Wireless('wlan0')

    def run(self):
        self.log.debug("%s thread started" % self.name)
        while not self.must_stop.is_set():
            cpu = psutil.cpu_percent()
            stat, qual, discard, missed_beacon = self.wifi.getStatistics()
            self.lock.acquire()
            self.cpu = cpu
            self.wifi_signal = qual.signallevel
            self.lock.release()
            self.must_stop.wait(5)

    def get_ip_address(self, ifname):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        return socket.inet_ntoa(fcntl.ioctl(
            s.fileno(),
            0x8915,  # SIOCGIFADDR
            struct.pack('256s', ifname[:15])
        )[20:24])


class MPlayerControl(Thread):
    def __init__(self, action=None, arg=None):
        super(MPlayerControl, self).__init__()
        self.mpd = MPDClient()
        self.mpd.connect("localhost", 6600)
        self.action = action
        self.arg = arg

    def run(self):
        self.log.debug("%s thread started" % self.name)
        if self.action is "play":
            self.log.debug("play song 4")
            self.mpd.play(7)
        if self.action is "stop":
            self.log.debug("stop playing")
            self.mpd.stop()
        if self.action is "next":
            self.log.debug("next track")
            self.mpd.next()
        if self.action is "prev":
            self.log.debug("previous track")
            self.mpd.previous()

        if self.action is "sleep":
            # get current volume
            volume = int(self.mpd.status()['volume'])
            if volume > 50:
                step = (volume - 50) / 120.0
            self.log.debug("sleeping mode for 120min (using step: %.2f)" % step)
            while volume > 50 and not self.must_stop.is_set():
                self.must_stop.wait(60)
                volume -= step
                self.mpd.setvol(int(volume))
            self.mpd.stop()
            self.log.debug("sleeping complete")

        if self.action is "rise":
            # minimum audible volume is ~ 50, max is 95
            # raise volume every minute for 20 minutes
            step = (95 - 50) / 20
            volume = 50
            self.mpd.setvol(volume)
            # load "clock" playlist and play song n4
            self.mpd.clear()
            self.mpd.load("clock")
            self.mpd.play(8)
            self.log.debug("play song 4, and raising volume...")
            while volume < (50 + step*20) and not self.must_stop.is_set():
                self.must_stop.wait(60)
                volume += step
                self.mpd.setvol(volume)
            self.log.debug("rising complete")
        if self.action is "vol":
            volume = int(self.arg)
            self.log.debug("changing volume %d" % volume)
            self.mpd.setvol(volume)
        self.mpd.close()


class MPlayer(Thread):
    """docstring for MPlayer"""
    def __init__(self):
        super(MPlayer, self).__init__()
        self.title = ""
        # MPlayer daemon
        self.mpd = MPDClient()
        self.mpd.connect("localhost", 6600)
        self.status = self.mpd.status()
        if self.status['state'] == "play":
            song = self.mpd.currentsong()
            if 'title' in song and 'name' in song:
                self.title = "%s - %s" % (song['title'], song['name'], )
            elif 'title' in song and 'artist' in song:
                self.title = "%s - %s" % (song['title'], song['artist'], )
        self.mpc = None

    def run(self):
        self.log.debug("%s thread started" % self.name)
        while not self.must_stop.is_set():
            try:
                events = self.mpd.idle()
                if 'player' in events:
                    status = self.mpd.status()
                    title = ""
                    if status['state'] == "play":
                        song = self.mpd.currentsong()
                        if 'title' in song and 'name' in song:
                            title = "%s - %s" % (song['title'], song['name'], )
                        elif 'title' in song and 'artist' in song:
                            title = "%s - %s" % (song['title'], song['artist'], )
                    self.log.debug("mpd event: %s state: %s song: %s" % (events, status['state'], title))
                    self.lock.acquire()
                    self.title = title
                    self.status = status
                    self.lock.release()
            except ConnectionError, e:
                # reconnect
                if self.must_stop.is_set():
                    break
                self.log.warning("lost connection, reconnecting...")
                self.mpd.connect("localhost", 6600)
                title = ""

    def stop(self):
        super(MPlayer, self).stop()
        self.mpd.close()

    def play(self):
        if self.mpc and self.mpc.is_alive():
            self.mpc.must_stop.set()
        self.mpc = MPlayerControl("play")
        self.mpc.start()

    def next(self):
        if self.mpc and self.mpc.is_alive():
            self.mpc.must_stop.set()
        self.mpc = MPlayerControl("next")
        self.mpc.start()

    def prev(self):
        if self.mpc and self.mpc.is_alive():
            self.mpc.must_stop.set()
        self.mpc = MPlayerControl("prev")
        self.mpc.start()

    def rise(self):
        if self.mpc and self.mpc.is_alive():
            self.mpc.must_stop.set()
        self.mpc = MPlayerControl("rise")
        self.mpc.start()

    def sleep(self):
        if self.mpc and self.mpc.is_alive():
            self.mpc.must_stop.set()
        self.mpc = MPlayerControl("sleep")
        self.mpc.start()

    def vol(self, volume):
        if self.mpc and self.mpc.is_alive():
            self.mpc.must_stop.set()
        if volume <= 100 and volume >= 0:
            self.mpc = MPlayerControl("vol", volume)
            self.mpc.start()

    def stop_playing(self):
        if self.mpc and self.mpc.is_alive():
            self.mpc.must_stop.set()
        self.mpc = MPlayerControl("stop")
        self.mpc.start()


class TempNode(Thread):
    def __init__(self, addr=None):
        super(TempNode, self).__init__()
        if addr is None:
            self.device = self.autodetect()
        else:
            self.device = self.get_device(addr)
        self.temp = 0

    def run(self):
        self.log.debug("%s thread started" % self.name)
        while not self.must_stop.is_set():
            temp = self.read_temp()
            self.lock.acquire()
            self.temp = temp
            self.lock.release()
            self.must_stop.wait(60*5)

    def autodetect(self):
        base_dir = '/sys/bus/w1/devices/'
        device_folder = glob.glob(base_dir + '28*')[0]
        return os.path.join(device_folder, 'w1_slave')

    def get_device(self, addr):
        return None

    def read_temp(self):
        with open(self.device, 'r') as f:
            raw = f.readlines()
        crc = raw[0].strip()[-3:]
        if crc == 'YES':
            temp_pos = raw[1].find("t=")
            if temp_pos != -1:
                temp_raw = raw[1][temp_pos+2:]
                temp_c = float(temp_raw) / 1000.0
                self.log.debug("temp: %.2f°C" % (temp_c,))
                return temp_c
        else:
            self.log.warning("crc: %s" % crc)


class Audio(Thread):
    """docstring for Audio"""
    def __init__(self):
        super(Audio, self).__init__()
        self.volume = 0

    def run(self):
        self.log.debug("%s thread started" % self.name)
        polling = select.poll()
        mix = alsaaudio.Mixer('PCM')
        with self.lock:
            self.volume = mix.getvolume()[0]
        while not self.must_stop.is_set():
            fd, evmsk = mix.polldescriptors()[0]
            polling.register(fd, evmsk)

            event = polling.poll()
            for f, e in event:
                if e & select.POLLIN:
                    mix = alsaaudio.Mixer('PCM')
                    volume = mix.getvolume()[0]
                    if volume != self.volume:
                        with self.lock:
                            self.volume = mix.getvolume()[0]
                        self.log.debug("volume: %d%%" % volume)

            polling.unregister(fd)


class Input(Thread):
    def __init__(self):
        super(Input, self).__init__()
        self.wheel = 0
        self.click = False
        self.has_input = threading.Event()
        # Rotary Encoder
        gpio.setup(17, gpio.IN, gpio.PUD_UP)
        gpio.setup(27, gpio.IN, gpio.PUD_UP)
        # Button
        gpio.setup(18, gpio.IN, gpio.PUD_UP)
        self.log.setLevel(logging.INFO)

    def run(self):
        self.log.debug("%s thread started" % self.name)
        gpio.add_event_detect(17, gpio.FALLING,
                              callback=self.on_low, bouncetime=100)
        gpio.add_event_detect(18, gpio.FALLING,
                              callback=self.on_click, bouncetime=500)

    def on_low(self, pin):
        a = gpio.input(17)
        b = gpio.input(27)
        vol = 0
        if a:
            return
        if b:
            vol = 1
        else:
            vol = -1
        if vol != 0:
            with self.lock:
                self.wheel += vol
            self.has_input.set()
            self.log.debug("rotate %s %s" % (vol, self.wheel))

    def on_click(self, pin):
        with self.lock:
            self.click = True
        self.has_input.set()
        self.log.debug("click!")


if __name__ == '__main__':
    log = logging.getLogger("main")
    logging.basicConfig(
        format='%(asctime)-23s - %(levelname)-7s - %(name)s - %(message)s')
    log.setLevel(logging.DEBUG)

    input_thread = Input()
    input_thread.start()
    while True:
        time.sleep(10)
