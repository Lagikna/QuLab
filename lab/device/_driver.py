# -*- coding: utf-8 -*-
import copy
import importlib
import logging
import os
import re
import string

import visa

from .. import db
from .util import IEEE_488_2_BinBlock

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


def _load_driver(driver_name):
    log.debug('Loading driver %s ...' % driver_data.name)
    fullname = 'qulab.drivers.%s' % driver_name
    mod = importlib.import_module(fullname)
    return getattr(mod, 'Driver')


ats_addr = re.compile(
    r'^(ATS)(9360|9850|9870)::SYSTEM([0-9]+)::([0-9]+)(|::INSTR)$')
# gpib_addr = re.compile(r'^GPIB[0-9]?::[0-9]+(::.+)？$')
zi_addr = re.compile(r'^(ZI)::([a-zA-Z]+[0-9]*)::([a-zA-Z-]+[0-9]*)(|::INSTR)$')
pxi_addr = re.compile(r'^(PXI)[0-9]?::CHASSIS([0-9]*)::SLOT([0-9]*)::FUNC([0-9]*)::INSTR$')
#其他类型 (OTHER)::(Key):(Value)::INSTR
other_addr = re.compile(r'^(OTHER)::([a-zA-Z-]+):(.*)::INSTR$')


def _parse_ats_resource_name(m, addr):
    type = m.group(1)
    model = m.group(1)+str(m.group(2))
    systemID = int(m.group(3))
    boardID = int(m.group(4))
    return dict(
        type=type,
        ins=None,
        company='AlazarTech',
        model=model,
        systemID=systemID,
        boardID=boardID,
        addr=addr)

def _parse_zi_resource_name(z, addr):
    type = z.group(1)
    model = z.group(2)
    deviceID = z.group(3)
    return dict(
        type=type,
        ins=None,
        company='ZurichInstruments',
        model=model,
        deviceID=deviceID,
        addr=addr)

def _parse_pxi_resource_name(pxi, addr):
    type = pxi.group(1)
    CHASSIS = int(pxi.group(2))
    SLOT = int(pxi.group(3))
    return dict(
        type=type,
        ins=None,
        company='KeySight',
        CHASSIS=CHASSIS,
        SLOT=SLOT,
        addr=addr)

def _parse_other_resource_name(m, addr):
    type = m.group(1)
    key = m.group(2)
    value = m.group(3)
    kw={key:value}
    kw.update(
        type=type,
        ins=None,
        company=None,
        addr=addr)
    return kw

def _parse_resource_name(addr):
    type = None
    for addr_re in [ats_addr,zi_addr,pxi_addr,other_addr]:
        m = addr_re.search(addr)
        if m is not None:
            type = m.group(1)
            break
    if type == 'ATS':
        return _parse_ats_resource_name(m, addr)
    elif type == 'ZI':
        return _parse_zi_resource_name(m, addr)
    elif type == 'PXI':
        return _parse_pxi_resource_name(m, addr)
    elif type == 'OTHER':
        return _parse_other_resource_name(m, addr)
    else:
        return dict(type='Visa', addr=addr)


class DriverManager(object):
    def __init__(self):
        self.__drivers = []
        self.__instr = {}

    def __del__(self):
        for ins in self.__instr.values():
            ins.close()

    def __getitem__(self, key):
        return self.get(key)

    def get(self, key):
        return self.__instr.get(key, None)

    def _open_resource(self, addr, driver_name, **kw):
        info = _parse_resource_name(addr)
        Driver = _load_driver(driver_name)
        info.update(kw)
        ins = Driver(**info)
        ins.performOpen()
        return ins

    def open(self, instrument, **kw):
        if isinstance(instrument, str):
            instrument = db.query.getInstrumentByName(instrument)
        if instrument.name not in self.__instr.keys():
            self.__instr[instrument.name] = self._open_resource(
                instrument.address, instrument.driver, **kw)
        return self.__instr[instrument.name]
