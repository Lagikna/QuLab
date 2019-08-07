# -*- coding: utf-8 -*-
import numpy as np
import logging

from qulab import (BaseDriver, QInteger, QOption, QReal, QVector)

from .PG_DC_api import Voltage

log = logging.getLogger('qulab.driver.DC_driver')


class Driver(BaseDriver):
    support_models = ['PG_DC']
    quants = [
        QReal('Offset', value=0, unit='V', ch=1),
            ]

    def __init__(self, addr, **kw):
        '''
        addr: ip, e.g. '192.168.1.6'
        '''
        super().__init__(addr=addr, **kw)
        self.model = 'PG_DC'
        self.addr=addr
        self.performOpen()

    def performOpen(self):
        self.handle = Voltage(self.addr)

    def performSetValue(self, quant, value, ch=1, **kw):
        if quant.name == 'Offset':
            # ch: 1,2,3,4 -> 0,1,2,3
            #log.info(f'Set volt of Channel {ch} to {value}')
            print(f'{self.addr} : Set volt of Channel {ch} to {value}')
            self.handle.setVoltage(value,ch=ch-1)
