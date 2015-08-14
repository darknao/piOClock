#!/usr/bin/python
# -*- coding: UTF-8 -*-
from subprocess import call


class Action():
    """docstring for Action"""
    def __init__(self, name, action=None, arg=None, goback=False):
        self.name = name
        self.action = action
        self.goback = goback
        self.arg = arg

    def function(self):
        if self.arg:
            return self.action(self.arg)
        else:
            return self.action()


class Command():
    """docstring for Command"""
    def __init__(self, name, command=None, goback=False):
        self.name = name
        self.command = command
        self.goback = goback

    def function(self):
        """ run command """
        call(self.command)


class MenuBack(Action):
    """docstring for MenuBack"""
    def __init__(self, name):
        self.name = name

    def function(self):
        pass


class SubMenu():
    """docstring for SubMenu"""
    def __init__(self, name, items=[]):
        self.name = name
        self.items = items
        self.items.append(MenuBack("<< back"))


class Screen():
    """docstring for Screen"""
    def __init__(self, name, function=None):
        self.name = name
        self.function = function
