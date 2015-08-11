#!/usr/bin/python
# -*- coding: UTF-8 -*-


class Item():
    """docstring for Item"""
    def __init__(self, name, function=None, goback=False):
        self.name = name
        self.function = function
        self.goback = goback

class SubMenu():
    """docstring for SubMenu"""
    def __init__(self, name, items=[]):
        self.name = name
        self.items = items
        