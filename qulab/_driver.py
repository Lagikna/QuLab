# -*- coding: utf-8 -*-
import copy
import importlib
import logging
import os
import re
import string

import numpy as np
import quantities as pq
import visa

from .util import IEEE_488_2_BinBlock, get_unit_prefix

log = logging.getLogger('qulab.driver')
log.addHandler(logging.NullHandler())

__all__ = [
    'QReal', 'QInteger', 'QString', 'QOption', 'QBool', 'QVector', 'QList',
    'BaseDriver', 'visaDriver'
]


class Quantity:
    def __init__(self,
                 name,
                 value=None,
                 type=None,
                 unit=None,
                 ch=None,
                 get_cmd='',
                 set_cmd=''):
        self.name = name
        self.value = value
        self.type = type
        self.unit = unit
        self.ch = ch
        self.driver = None
        self.set_cmd = set_cmd
        self.get_cmd = get_cmd
        self.default = dict(value = value,
                            unit = unit,
                            ch = ch)

    def __str__(self):
        return '%s' % self.value

    def setDriver(self, driver):
        self.driver = driver

    def getValue(self, **kw):
        # if self.driver is not None and self.get_cmd is not '':
        #     cmd = self._formatGetCmd(**kw)
        #     self.value = self.driver.query(cmd)
        return self.value

    def setValue(self, value, **kw):
        self.value = value
        if self.driver is not None and self.set_cmd is not '':
            cmd = self._formatSetCmd(value, **kw)
            self.driver.write(cmd)

    def _formatGetCmd(self, **kw):
        _kw = copy.deepcopy(self.default)
        _kw.update(**kw)
        return self.get_cmd % dict(**_kw)

    def _formatSetCmd(self, value, **kw):
        _kw = copy.deepcopy(self.default)
        _kw.update(value=value,**kw)
        return self.set_cmd % dict(**_kw)


class QReal(Quantity):
    def __init__(self,
                 name,
                 value=None,
                 unit=None,
                 ch=None,
                 get_cmd='',
                 set_cmd=''):
        super(QReal, self).__init__(
            name, value, 'Real', unit, ch, get_cmd=get_cmd, set_cmd=set_cmd)

    def __str__(self):
        p, r = get_unit_prefix(self.value)
        value = self.value / r
        unit = p + self.unit
        return '%g %s' % (value, unit)

    def getValue(self, **kw):
        if self.driver is not None and self.get_cmd is not '':
            cmd = self._formatGetCmd(**kw)
            res = self.driver.query_ascii_values(cmd)
            self.value = res[0]
        return self.value


class QInteger(QReal):
    def __init__(self,
                 name,
                 value=None,
                 unit=None,
                 ch=None,
                 get_cmd='',
                 set_cmd=''):
        Quantity.__init__(
            self,
            name,
            value,
            'Integer',
            unit,
            ch,
            get_cmd=get_cmd,
            set_cmd=set_cmd)

    def getValue(self, **kw):
        super(QInteger, self).getValue(**kw)
        return int(self.value)


class QString(Quantity):
    def __init__(self, name, value=None, ch=None, get_cmd='', set_cmd=''):
        super(QString, self).__init__(
            name, value, 'String', ch=ch, get_cmd=get_cmd, set_cmd=set_cmd)

    def getValue(self, **kw):
        if self.driver is not None and self.get_cmd is not '':
            cmd = self._formatGetCmd(**kw)
            res = self.driver.query(cmd)
            self.value = res.strip("\n\"' ")
        return self.value


class QOption(QString):
    def __init__(self,
                 name,
                 value=None,
                 options=[],
                 ch=None,
                 get_cmd='',
                 set_cmd=''):
        Quantity.__init__(
            self,
            name,
            value,
            'Option',
            ch=ch,
            get_cmd=get_cmd,
            set_cmd=set_cmd)
        self.options = options
        self._opts = {}
        for k, v in self.options:
            self._opts[k] = v
            self._opts[v] = k

    def setValue(self, value, **kw):
        self.value = value
        if self.driver is not None and self.set_cmd is not '':
            options = dict(self.options)
            if value not in options.keys():
                #logger.error('%s not in %s options' % (value, self.name))
                return
            cmd = self._formatSetCmd(value, option=options[value], **kw)
            # cmd = self.set_cmd % dict(option=options[value], **kw)
            self.driver.write(cmd)

    def getValue(self, **kw):
        if self.driver is not None and self.get_cmd is not '':
            cmd = self._formatGetCmd(**kw)
            res = self.driver.query(cmd)
            res_value = res.strip("\n\"' ")
            self.value = self._opts[res_value]
        return self.value

    def getIndex(self, **kw):
        value = self.getValue(**kw)
        if value is None:
            return None

        for i, pair in enumerate(self.options):
            if pair[0] == value:
                return i
        return None

    def getCmdOption(self, **kw):
        value = self.getValue(**kw)
        if value is None:
            return None
        return dict(self.options)[value]


class QBool(QInteger):
    def __init__(self, name, value=None, ch=None, get_cmd='', set_cmd=''):
        Quantity.__init__(
            self, name, value, 'Bool', ch=ch, get_cmd=get_cmd, set_cmd=set_cmd)

    def getValue(self, **kw):
        return bool(super(QBool, self).getValue(ch=ch, **kw))


class QVector(Quantity):
    def __init__(self,
                 name,
                 value=None,
                 unit=None,
                 ch=None,
                 get_cmd='',
                 set_cmd=''):
        super(QVector, self).__init__(
            name, value, 'Vector', unit, ch, get_cmd=get_cmd, set_cmd=set_cmd)

    def getValue(self, **kw):
        if self.driver is not None and self.get_cmd is not '':
            cmd = self._formatGetCmd(**kw)
            if kw.get('binary'):
                res = self.driver.query_binary_values(cmd)
            else:
                res = self.driver.query_ascii_values(cmd)
            self.value = np.asarray(res)
        return self.value


class QList(Quantity):
    def __init__(self,
                 name,
                 value=None,
                 unit=None,
                 ch=None,
                 get_cmd='',
                 set_cmd=''):
        super(QList, self).__init__(
            name, value, 'List', unit, ch, get_cmd=get_cmd, set_cmd=set_cmd)


class BaseDriver(object):

    quants = []

    config = {}

    def __init__(self, addr=None, **kw):
        self.addr = addr
        self.handle = None
        self.model = None

        self.quantities = {}
        for quant in self.quants:
            self.quantities[quant.name] = copy.deepcopy(quant)
            self.quantities[quant.name].driver = self

    def __repr__(self):
        return 'Driver(addr=%s)' % (self.addr)

    def init(self,cfg=None):
        if cfg == None:
            cfg = self.config
        for key in cfg.keys():
            if isinstance(cfg[key],dict):
                self.setValue(key, **cfg[key])
            else:
                self.setValue(key, cfg[key])
        return self

    def performOpen(self):
        pass

    def performClose(self):
        pass

    def performSetValue(self, quant, value, **kw):
        quant.setValue(value, **kw)
    
    def performGetValue(self, quant, value, **kw):
        return quant.getValue(**kw)

    def getValue(self, name, **kw):
        if name in self.quantities:
            return self.performGetValue(self.quantities[name], **kw)
        else:
            return None

    def getIndex(self, name, **kw):
        if name in self.quantities:
            return self.quantities[name].getIndex(**kw)

    def getCmdOption(self, name, **kw):
        if name in self.quantities:
            return self.quantities[name].getCmdOption(**kw)

    def setValue(self, name, value, **kw):
        if name in self.quantities:
            self.performSetValue(self.quantities[name], value, **kw)
        return self

    def errors(self):
        """返回错误列表"""
        errs = []
        return errs

    def check_errors_and_log(self, message):
        errs = self.errors()
        for e in errs:
            log.error("%s << %s", str(self.handle), message)
            log.error("%s >> %s", str(self.handle), ("%d : %s" % e))

    def query(self, message, check_errors=False):
        if check_errors:
            self.check_errors_and_log(message)
        pass

    def write(self, message, check_errors=False):
        if check_errors:
            self.check_errors_and_log(message)
        pass

    def read(self, message, check_errors=False):
        if check_errors:
            self.check_errors_and_log(message)
        pass



class visaDriver(BaseDriver):

    error_command = 'SYST:ERR?'
    """The SCPI command to query errors."""

    support_models = []
    """the confirmed models supported by this driver"""

    quants = []

    config = {}

    def __init__(self, addr=None, visa_backends='@ni', timeout=3, **kw):
        super(visaDriver, self).__init__(addr, **kw)
        self.rm = visa.ResourceManager(visa_backends)
        self.timeout = timeout

    def __repr__(self):
        return 'visaDriver(addr=%s)' % (self.addr)

    def performOpen(self):
        self.handle = self.rm.open_resource(self.addr)
        self.handle.timeout = self.timeout * 1000
        try:
            IDN = self.handle.query("*IDN?").split(',')
            company = IDN[0].strip()
            model = IDN[1].strip()
            version = IDN[3].strip()
            self.model = model

    def performClose(self):
        self.handle.close()

    def set_timeout(self, t):
        self.timeout = t
        if self.handle is not None:
            self.handle.timeout = t * 1000
        return self

    def errors(self):
        """返回错误列表"""
        e = []
        if self.error_command == '':
            return e
        while True:
            s = self.handle.query(self.error_command)
            _ = s[:-1].split(',"')
            code = int(_[0])
            msg = _[1]
            if code == 0:
                break
            e.append((code, msg))
        return e

    def query(self, message, check_errors=False):
        if self.handle is None:
            return None
        log.debug("%s << %s", str(self.handle), message)
        try:
            res = self.handle.query(message)
        except:
            log.exception("%s << %s", str(self.handle), message)
            raise
        log.debug("%s >> %s", str(self.handle), res)
        if check_errors:
            self.check_errors_and_log(message)
        return res

    def query_ascii_values(self, message, converter='f', separator=',',
                           container=list, delay=None,
                           check_errors=False):
        if self.handle is None:
            return None
        log.debug("%s << %s", str(self.handle), message)
        try:
            res = self.handle.query_ascii_values(
                message, converter, separator, container, delay)
        except:
            log.exception("%s << %s", str(self.handle), message)
            raise
        log.debug("%s >> <%d results>", str(self.handle), len(res))
        if check_errors:
            self.check_errors_and_log(message)
        return res

    def query_binary_values(self, message, datatype='f', is_big_endian=False,
                            container=list, delay=None,
                            header_fmt='ieee', check_errors=False):
        if self.handle is None:
            return None
        log.debug("%s << %s", str(self.handle), message)
        try:
            res = self.handle.query_binary_values(message, datatype, is_big_endian,
                                               container, delay, header_fmt)
        except:
            log.exception("%s << %s", str(self.handle), message)
            raise
        log.debug("%s >> <%d results>", str(self.handle), len(res))
        if check_errors:
            self.check_errors_and_log(message)
        return res

    def write(self, message, check_errors=False):
        """Send message to the instrument."""
        if self.handle is None:
            return None
        log.debug("%s << %s", str(self.handle), message)
        try:
            ret = self.handle.write(message)
        except:
            log.exception("%s << %s", str(self.handle), message)
            raise
        if check_errors:
            self.check_errors_and_log(message)
        return self

    def write_ascii_values(self, message, values, converter='f', separator=',',
                           termination=None, encoding=None, check_errors=False):
        if self.handle is None:
            return None
        log_msg = message+('<%d values>' % len(values))
        log.debug("%s << %s", str(self.handle), log_msg)
        try:
            ret = self.handle.write_ascii_values(message, values, converter,
                                              separator, termination, encoding)
        except:
            log.exception("%s << %s", str(self.handle), log_msg)
            raise
        if check_errors:
            self.check_errors_and_log(log_msg)
        return self

    def write_binary_values(self, message, values,
                            datatype='f', is_big_endian=False,
                            termination=None, encoding=None, check_errors=False):
        if self.handle is None:
            return None
        block, header = IEEE_488_2_BinBlock(values, datatype, is_big_endian)
        log_msg = message+header+'<DATABLOCK>'
        log.debug("%s << %s", str(self.handle), log_msg)
        try:
            ret = self.handle.write_binary_values(message, values, datatype,
                                               is_big_endian, termination, encoding)
        except:
            log.exception("%s << %s", str(self.handle), log_msg)
            raise
        if check_errors:
            self.check_errors_and_log(log_msg)
        return self
