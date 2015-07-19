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


class HWmonitor(threading.Thread):
    """docstring for HWmonitor"""
    def __init__(self):
        super(HWmonitor, self).__init__()
        self.log = logging.getLogger(self.__class__.__name__)
        self.log.setLevel(logging.DEBUG)
        self.cpu = 0
        self.must_stop = threading.Event()
        self.lock = threading.Lock()

    def run(self):
        self.log.debug("%s thread started" % self.name)
        while not self.must_stop:
            cpu = psutil.cpu_percent()
            self.lock.acquire()
            self.cpu = cpu
            self.lock.release()
            self.must_stop.wait(5)

    def stop(self):
        self.log.debug("%s request stop" % self.name)
        self.must_stop.set()


class MPlayer(threading.Thread):
    """docstring for MPlayer"""
    def __init__(self):
        super(MPlayer, self).__init__()
        self.log = logging.getLogger(self.__class__.__name__)
        self.log.setLevel(logging.DEBUG)
        self.title = ""
        # MPlayer daemon
        self.mpd = MPDClient()
        self.mpd.connect("localhost", 6600)
        self.status = self.mpd.status()
        if self.status['state'] == "play":
            song = self.mpd.currentsong()
            if 'title' in song:
                self.title = "%s - %s" % (song['title'], song['name'], )

        self.must_stop = False
        self.lock = threading.Lock()

    def run(self):
        self.log.debug("%s thread started" % self.name)
        while not self.must_stop:
            try:
                events = self.mpd.idle()
                if 'player' in events:
                    status = self.mpd.status()
                    if status['state'] == "play":
                        song = self.mpd.currentsong()
                        if 'title' in song:
                            title = "%s - %s" % (song['title'], song['name'], )
                    else:
                        title = ""
                    self.log.debug("mpd event: %s state: %s song: %s" % (events, status['state'], title))
                    self.lock.acquire()
                    self.title = title
                    self.status = status
                    self.lock.release()
            except ConnectionError, e:
                # reconnect
                if self.must_stop:
                    break
                self.log.warning("lost connection, reconnecting...")
                self.mpd.connect("localhost", 6600)
                title = ""

    def stop(self):
        self.log.debug("%s request stop" % self.name)
        self.must_stop = True
        self.mpd.close()


class TempNode(threading.Thread):
    def __init__(self, addr=None):
        threading.Thread.__init__(self)
        if addr is None:
            self.device = self.autodetect()
        else:
            self.device = self.get_device(addr)
        self.log = logging.getLogger(self.__class__.__name__)
        self.log.setLevel(logging.DEBUG)
        self.temp = 0
        self.must_stop = threading.Event()
        self.lock = threading.Lock()

    def run(self):
        self.log.debug("%s thread started" % self.name)
        while not self.must_stop.is_set():
            temp = self.read_temp()
            self.lock.acquire()
            self.temp = temp
            self.lock.release()
            self.must_stop.wait(60*5)

    def stop(self):
        self.log.debug("%s request stop" % self.name)
        self.must_stop.set()

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


class Audio(threading.Thread):
    """docstring for Audio"""
    def __init__(self):
        super(Audio, self).__init__()
        self.log = logging.getLogger(self.__class__.__name__)
        self.log.setLevel(logging.DEBUG)
        self.volume = 0
        self.must_stop = threading.Event()
        self.lock = threading.Lock()

    def run(self):
        self.log.debug("%s thread started" % self.name)
        while not self.must_stop.is_set():
            volume = alsaaudio.Mixer('PCM').getvolume()[0]
            #self.log.debug("volume: %d" % volume)
            self.lock.acquire()
            self.volume = volume
            self.lock.release()
            self.must_stop.wait(10)

    def stop(self):
        self.log.debug("%s request stop" % self.name)
        self.must_stop.set()
