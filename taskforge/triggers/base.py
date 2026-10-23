from abc import ABC, abstractmethod


class BaseTrigger(ABC):
    @abstractmethod
    def to_apscheduler_trigger(self):
        pass
