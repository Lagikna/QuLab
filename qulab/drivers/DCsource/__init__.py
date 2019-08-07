import logging
from qulab import (BaseDriver, QInteger, QOption, QReal, QVector)

from .VoltageSettingCore import (CalculateDValue, SetChannelNum, SetDefaultIP,
                                 SetDValue)

log = logging.getLogger('qulab.driver.DCSource')


class Driver(BaseDriver):

    quants = [
        QReal('Offset', value=0, unit='V', ch=1),
            ]

    def __init__(self, **kw):
        super().__init__(**kw)
        ip = kw.get('addr')
        self.ip = ip
        SetDefaultIP(ip)
        SetChannelNum(0, 0)

    def setVolt(self, volt, ch=1):
        log.info(f'Set volt of Channel {ch} to {volt}')
        SetDefaultIP(self.ip)
        SetChannelNum(ch-1, 0)
        SetDValue(CalculateDValue(volt))

    def performSetValue(self, quant, value, ch=1, **kw):
        if quant.name == 'Offset':
            self.setVolt(value,ch=ch)
